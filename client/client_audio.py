import socket
import threading
import pyaudio
import struct
import time
import random
import string
from discovery import disable_udp_connreset

class AudioClient:
    def __init__(self, host='localhost', port=12348, username="User"):
        self.host = host
        self.port = port
        
        # --- FIX FOR ECHO ---
        rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        self.username = f"{username}_{rand_suffix}"
        self.username_bytes = self.username.encode('utf-8')
        print(f"Audio client initialized as: {self.username}")
        # ---

        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        self.client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        disable_udp_connreset(self.client)
        self.client.bind(('', 0))  # Let OS pick a free port

        self.audio = pyaudio.PyAudio()
        
        # --- "MIKE ON/OFF" LOGIC ---
        self.app_running = True # Controls all threads
        self.sending_audio = False # Controls the audio sending (Mike On/Off)
        # ---
        
        # Audio settings
        self.CHUNK = 512
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        
        # Client jitter buffer settings
        self.CLIENT_BUFFER_SIZE = 8
        self.MIN_BUFFER_START = 6
        self.PLAYBACK_INTERVAL = float(self.CHUNK) / float(self.RATE)
        
        self._jitter_lock = threading.Lock()
        self._playback_last_chunk = None
        self._playback_started = False
        self.DEBUG_AUDIO = False

        # --- ALWAYS ON ---
        # Start the receive (hearing) thread IMMEDIATELY
        print("Starting receive_audio thread (Listening)...")
        threading.Thread(target=self.receive_audio, daemon=True).start()
        # Start the heartbeat thread IMMEDIATELY
        print("Starting heartbeat thread (to stay in call)...")
        threading.Thread(target=self.send_heartbeat, daemon=True).start()
        # ---
        
    def start_audio(self):
        """
        --- "MIKE ON" LOGIC ---
        Starts ONLY the send (talking) thread.
        """
        if self.sending_audio:
            print("Mike is already on.")
            return False
        
        print("--- MIKE ON --- (Starting send_audio thread)")
        self.sending_audio = True
        threading.Thread(target=self.send_audio, daemon=True).start()
        return True

    def stop_audio(self):
        """
        --- "MIKE OFF" LOGIC ---
        Stops ONLY the send (talking) thread.
        Heartbeat and Receive continue.
        """
        if not self.sending_audio:
            print("Mike is already off.")
            return

        print("--- MIKE OFF --- (Stopping send_audio thread)")
        self.sending_audio = False

    def shutdown(self):
        """
        Stops all audio activity.
        Call this when your main application is closing.
        """
        print("Shutting down all audio threads...")
        self.app_running = False
        self.sending_audio = False
        try:
            self.client.close()
        except:
            pass
    
    def send_heartbeat(self):
        """
        Sends a tiny packet every 5 seconds to tell the
        server we are still here and want to receive audio.
        """
        while self.app_running:
            try:
                # Create packet: [seq][username_len][username]
                seq_bytes = struct.pack("I", 0) # Seq num doesn't matter for heartbeat
                username_len_bytes = struct.pack("Q", len(self.username_bytes))
                packet = seq_bytes + username_len_bytes + self.username_bytes

                self.client.sendto(packet, (self.host, self.port))
            
            except Exception as e:
                if self.app_running:
                    print(f"Heartbeat error: {e}")
            
            time.sleep(5.0) # Send heartbeat every 5 seconds

    def send_audio(self):
        """
        Captures audio from mic and sends to server.
        Loops as long as sending_audio is True.
        """
        try:
            stream = self.audio.open(format=self.FORMAT, channels=self.CHANNELS,
                                   rate=self.RATE, input=True, frames_per_buffer=self.CHUNK,
                                   input_device_index=None)
        except Exception as e:
            print(f"MIC FAILED: {e}. Cannot turn on mike.")
            self.sending_audio = False # Ensure we don't try again
            return # Exit this thread.

        sequence_number = 0
        print("Mic input stream opened. Sending audio...")

        try:
            # --- LOOP IS NOW CONTROLLED BY "Mike On/Off" FLAG ---
            while self.sending_audio and self.app_running:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                    
                    # Create packet: [seq][username_len][username][audio_data]
                    seq_bytes = struct.pack("I", sequence_number)
                    username_len_bytes = struct.pack("Q", len(self.username_bytes))
                    packet = seq_bytes + username_len_bytes + self.username_bytes + data

                    self.client.sendto(packet, (self.host, self.port))
                    sequence_number = (sequence_number + 1) & 0xFFFFFFFF
                
                except Exception as e:
                    if self.sending_audio and self.app_running:
                        print(f"Audio send error: {e}")
                    break
        finally:
            print("Send audio loop stopping...")
            try:
                stream.stop_stream()
                stream.close()
            except:
                pass

    def receive_audio(self):
        """
        Receives mixed audio from server and buffers it for playback.
        Runs as long as app_running is True.
        """
        try:
            stream = self.audio.open(format=self.FORMAT, channels=self.CHANNELS,
                                   rate=self.RATE, output=True, frames_per_buffer=self.CHUNK,
                                   output_device_index=None)
        except Exception as e:
            print(f"Audio output not available: {e}")
            self.app_running = False # Stop everything
            return

        buffer_map = {}
        expected_chunk_size = self.CHUNK * 2
        print("Audio output stream opened. Waiting for server mix...")

        def playback_loop():
            """Plays audio from the buffer_map at a steady, scheduled pace."""
            silence = b'\x00' * expected_chunk_size
            interval = self.PLAYBACK_INTERVAL
            next_play_time = time.perf_counter() + interval

            while self.app_running:
                chunk = None
                with self._jitter_lock:
                    # Wait until we have enough buffered chunks to start
                    if not self._playback_started:
                        if len(buffer_map) >= self.MIN_BUFFER_START:
                            print(f"Audio playback starting with {len(buffer_map)} buffered chunks")
                            self._playback_started = True
                        else:
                            time.sleep(0.005)
                            continue

                    if buffer_map:
                        oldest_seq = min(buffer_map.keys())
                        chunk = buffer_map.pop(oldest_seq, None)
                        if not chunk or len(chunk) != expected_chunk_size:
                            chunk = None

                    # Trim excessive buffering
                    while len(buffer_map) > self.CLIENT_BUFFER_SIZE:
                        try:
                            oldest = min(buffer_map.keys())
                            del buffer_map[oldest]
                        except Exception:
                            break

                # Sleep until scheduled play time to keep steady playback
                now = time.perf_counter()
                to_wait = next_play_time - now
                if to_wait > 0:
                    time.sleep(to_wait)

                try:
                    if chunk:
                        stream.write(chunk, exception_on_underflow=False)
                    else:
                        # Play silence for missing packets to avoid repeated artifacts
                        stream.write(silence, exception_on_underflow=False)
                except Exception:
                    # Ignore underflow/other write issues during runtime
                    pass

                next_play_time += interval

            print("Playback loop stopping...")
            try:
                stream.stop_stream()
                stream.close()
            except:
                pass

        threading.Thread(target=playback_loop, daemon=True).start()

        try:
            # --- LOOP IS NOW CONTROLLED BY THE MAIN FLAG ---
            while self.app_running:
                try:
                    self.client.settimeout(0.1)
                    data, _ = self.client.recvfrom(8192)

                    if len(data) < 12: continue

                    seq_num = struct.unpack("I", data[:4])[0]
                    username_len = struct.unpack("Q", data[4:12])[0]
                    
                    # Check for SERVER_MIX packet
                    # 12 is header len, username_len is username
                    if len(data) > 12 + username_len:
                        username = data[12:12+username_len].decode('utf-8')
                        audio_data = data[12+username_len:]

                        if username == "SERVER_MIX":
                            with self._jitter_lock:
                                if len(audio_data) == expected_chunk_size:
                                    buffer_map[seq_num] = audio_data
                                
                                while len(buffer_map) > self.CLIENT_BUFFER_SIZE * 10:
                                    oldest = min(buffer_map.keys())
                                    del buffer_map[oldest]

                except socket.timeout:
                    continue # This is normal
                except Exception as e:
                    if self.app_running:
                        print(f"Audio receive error: {e}")
                    break
        finally:
            print("Receive loop stopping...")
            self.app_running = False # Ensure playback loop also stops


if __name__ == "__main__":
    username = input("Enter username: ")
    # Pass the username to the constructor
    audio_client = AudioClient(username=username)
    
    print("Audio client is ON (Listening). Press 's' to turn Mike ON/OFF, 'q' to quit.")
    
    is_mike_on = False
    
    try:
        while True:
            key = input()
            if key == 's':
                if not is_mike_on:
                    audio_client.start_audio()
                    is_mike_on = True
                    print("--- MIKE IS ON (Talking) ---")
                else:
                    audio_client.stop_audio()
                    is_mike_on = False
                    print("--- MIKE IS OFF (Muted) ---")
            elif key == 'q':
                break
    except KeyboardInterrupt:
        pass
    finally:
        audio_client.shutdown()
        print("Audio stopped.")

