import socket
from netutils import DISCOVERY_PORT, DISCOVERY_REQUEST, DISCOVERY_REPLY, disable_udp_connreset

class DiscoveryServer:
    """Answers LAN broadcast queries so clients can find the server
    automatically (no internet / DNS needed, works on an offline hotspot)."""
    def __init__(self, host='0.0.0.0', port=DISCOVERY_PORT):
        self.host = host
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        disable_udp_connreset(self.server)
        self.server.bind((self.host, self.port))

    def start(self):
        print(f"Discovery server started on {self.host}:{self.port}")
        while True:
            try:
                data, addr = self.server.recvfrom(1024)
                if data.strip() == DISCOVERY_REQUEST:
                    self.server.sendto(DISCOVERY_REPLY, addr)
            except OSError as e:
                print(f"Discovery error: {e}")

if __name__ == "__main__":
    DiscoveryServer().start()
