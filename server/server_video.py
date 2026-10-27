import socket
import threading
import struct
import time
from netutils import disable_udp_connreset

# Packet format: [8-byte username_len][username][payload]
#   empty payload      -> registration / heartbeat
#   b"STOP_VIDEO"      -> sender turned camera off
#   anything else      -> one JPEG frame
CLIENT_TIMEOUT = 15.0  # seconds without any packet before a client is dropped

class VideoServer:
    def __init__(self, host='0.0.0.0', port=12347):
        self.host = host
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        disable_udp_connreset(self.server)
        self.server.bind((self.host, self.port))
        self.clients = {}    # client_addr: username
        self.last_seen = {}  # client_addr: timestamp
        self.lock = threading.Lock()

        print(f"Video server started on {self.host}:{self.port}")

    def start(self):
        threading.Thread(target=self.receive_video, daemon=True).start()
        threading.Thread(target=self.cleanup_clients, daemon=True).start()

    def receive_video(self):
        while True:
            try:
                packet, addr = self.server.recvfrom(65536)
            except OSError as e:
                print(f"Video receive error: {e}")
                continue
            if len(packet) < 8:
                continue
            username_len = struct.unpack("Q", packet[:8])[0]
            if username_len > 256 or len(packet) < 8 + username_len:
                continue
            try:
                username = packet[8:8+username_len].decode('utf-8')
            except UnicodeDecodeError:
                continue

            with self.lock:
                if addr not in self.clients:
                    print(f"Video client {username} connected from {addr}")
                self.clients[addr] = username
                self.last_seen[addr] = time.time()
                recipients = [a for a in self.clients if a != addr]

            if len(packet) == 8 + username_len:
                continue  # heartbeat only

            # Relay the frame (or STOP_VIDEO) as-is to everyone else
            for client_addr in recipients:
                try:
                    self.server.sendto(packet, client_addr)
                except OSError as e:
                    print(f"Send error to {client_addr}: {e}")

    def cleanup_clients(self):
        while True:
            time.sleep(5.0)
            now = time.time()
            with self.lock:
                for addr in [a for a, t in self.last_seen.items() if now - t > CLIENT_TIMEOUT]:
                    print(f"Video client {self.clients.get(addr)} at {addr} timed out")
                    self.clients.pop(addr, None)
                    self.last_seen.pop(addr, None)

if __name__ == "__main__":
    server = VideoServer()
    server.start()
    while True:
        time.sleep(1)
