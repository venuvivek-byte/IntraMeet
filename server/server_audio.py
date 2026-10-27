import socket
import threading
import struct
import time
import numpy as np
from netutils import disable_udp_connreset

class AudioServer:
    def __init__(self, host='0.0.0.0', port=12348):
        self.host = host
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        disable_udp_connreset(self.server)
        self.server.bind((self.host, self.port))

        # Client tracking
        self.clients = {}  # addr -> username
        self.last_seen = {}  # username -> last_seen_time

        # --- JITTER BUFFER LOGIC ---
        self.client_buffers = {}  # username -> {seq_num: audio_data}
        self.client_last_chunk = {}  # username -> last_good_audio_chunk
        self.SERVER_BUFFER_MAX = 10
        # ---

        self.running = True
        self.seq_counter = 0  # monotonic sequence counter for SERVER_MIX packets

        # Audio settings
        self.CHUNK = 512
        self.FORMAT = 16  # bits
        self.CHANNELS = 1
        self.RATE = 16000
        self.SILENCE = b'\x00' * (self.CHUNK * (self.FORMAT // 8))
        self.MAX_VOLUME = 0.95

        print(f"Audio server (v6 - Heartbeat) started on {self.host}:{self.port}")

    def start(self):
        threading.Thread(target=self.receive_packets, daemon=True).start()
        threading.Thread(target=self.mix_and_broadcast, daemon=True).start()
        threading.Thread(target=self.cleanup_clients, daemon=True).start()

    def cleanup_clients(self):
        """Periodically removes clients that haven't sent a packet in a while."""
        while self.running:
            time.sleep(5.0)
            timeout = 15.0 # Increased timeout to 15 seconds
            current_time = time.time()
            try:
                timed_out_users = [
                    username for username, last_time in list(self.last_seen.items())
                    if current_time - last_time > timeout
                ]
                
                for username in timed_out_users:
                    print(f"Client {username} timed out. Removing.")
                    addr_to_remove = None
                    for addr, user in list(self.clients.items()):
                        if user == username:
                            addr_to_remove = addr
                            break
                    if addr_to_remove:
                        del self.clients[addr_to_remove]
                    
                    if username in self.last_seen: del self.last_seen[username]
                    if username in self.client_buffers: del self.client_buffers[username]
                    if username in self.client_last_chunk: del self.client_last_chunk[username]

            except Exception as e:
                print(f"Cleanup error: {e}")

    def receive_packets(self):
        """
        Listens for ALL packets (Audio, Heartbeat)
        """
        while self.running:
            try:
                data, addr = self.server.recvfrom(4096)

                # All packets must have at least seq (4) + username_len (8)
                if len(data) < 12:
                    continue

                seq_num = struct.unpack("I", data[:4])[0]
                username_len = struct.unpack("Q", data[4:12])[0]
                
                # Check for packet type based on length
                # Note: 12 is the length of the header (seq + username_len)
                
                if len(data) == 12 + username_len:
                    # --- THIS IS A HEARTBEAT PACKET ---
                    username = data[12:12+username_len].decode('utf-8')
                    
                    # Register client / update last seen time
                    self.clients[addr] = username
                    self.last_seen[username] = time.time()
                    
                    # print(f"Received HEARTBEAT from {username}") # Uncomment for debug

                elif len(data) == 12 + username_len + len(self.SILENCE):
                    # --- THIS IS AN AUDIO PACKET ---
                    username = data[12:12+username_len].decode('utf-8')
                    audio_data = data[12+username_len:]

                    # Register client / update last seen time
                    self.clients[addr] = username
                    self.last_seen[username] = time.time()

                    # Store audio in buffer
                    if username not in self.client_buffers:
                        self.client_buffers[username] = {}
                        print(f"New audio stream for {username}")
                    
                    self.client_buffers[username][seq_num] = audio_data

                else:
                    # Malformed packet
                    # print("Received malformed packet")
                    continue
                
            except Exception as e:
                # print(f"Receive error: {e}")
                pass

    def mix_and_broadcast(self):
        """
        --- ECHO CANCELLATION LOGIC ---
        Loops through each client, creates a custom mix *for* them
        that *excludes* their own audio, and sends it only to them.
        """
        while self.running:
            try:
                loop_start_time = time.time()
                
                if not self.clients:
                    time.sleep(0.01)
                    continue

                # --- Get audio chunks from clients that are TALKING ---
                source_chunks = {}
                for source_username, source_buffer in list(self.client_buffers.items()):
                    chunk = None
                    if not source_buffer: # Buffer exists but is empty
                        chunk = self.client_last_chunk.get(source_username, self.SILENCE)
                    
                    # --- Lag Management ---
                    while len(source_buffer) > self.SERVER_BUFFER_MAX:
                        oldest_seq = min(source_buffer.keys())
                        source_buffer.pop(oldest_seq)

                    # --- Get Packet for Mixing ---
                    if len(source_buffer) > 0:
                        oldest_seq = min(source_buffer.keys())
                        chunk = source_buffer.pop(oldest_seq, self.SILENCE)
                        self.client_last_chunk[source_username] = chunk
                    else:
                        # --- Packet Loss Concealment (PLC) ---
                        chunk = self.client_last_chunk.get(source_username, self.SILENCE)
                    
                    source_chunks[source_username] = chunk

                # --- Loop through each *recipient* (ALL clients, talking or muted) ---
                for recipient_addr, recipient_username in list(self.clients.items()):
                    audio_to_mix = []
                    
                    # Loop through all *source* chunks we just prepared
                    for source_username, chunk_data in source_chunks.items():
                        
                        # --- THIS IS THE ECHO CANCELLATION ---
                        if source_username == recipient_username:
                            continue # Don't send a user their own audio
                        # ---
                        audio_to_mix.append(chunk_data)
                    
                    # --- Mixing Stage (for this specific recipient) ---
                    if audio_to_mix:
                        audio_arrays = [
                            np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                            for chunk in audio_to_mix
                        ]
                        mixed_float = np.sum(np.array(audio_arrays), axis=0)
                        
                        max_val = np.max(np.abs(mixed_float))
                        if max_val > self.MAX_VOLUME:
                            mixed_float *= (self.MAX_VOLUME / max_val)

                        mixed = (mixed_float * 32767).astype(np.int16)
                        mixed_audio = mixed.tobytes()
                    else:
                        mixed_audio = self.SILENCE # No one else is talking

                    # --- Broadcast Stage (to this specific recipient) ---
                    # Use monotonic seq counter for ordering on clients
                    seq_num = self.seq_counter
                    seq_bytes = struct.pack("I", seq_num)
                    # increment counter
                    self.seq_counter = (self.seq_counter + 1) & 0xFFFFFFFF
                    sender_name = "SERVER_MIX".encode('utf-8')
                    sender_len = struct.pack("Q", len(sender_name))
                    packet = seq_bytes + sender_len + sender_name + mixed_audio

                    try:
                        self.server.sendto(packet, recipient_addr)
                    except Exception:
                        pass # Ignore send errors

                # --- Loop Timing ---
                processing_time = time.time() - loop_start_time
                sleep_time = (float(self.CHUNK) / float(self.RATE)) - processing_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as e:
                print(f"Audio mixing error: {e}")
                time.sleep(0.01)

if __name__ == "__main__":
    server = AudioServer()
    server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Server shutting down...")
        server.running = False

