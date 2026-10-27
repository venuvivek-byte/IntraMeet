import socket
import threading
import struct
import time

# Simple TCP-based screen sharing server
# Presenter connects to PRESENTER_PORT and streams frames (4-byte length + jpeg bytes)
# Viewers connect to VIEWER_PORT and receive frames forwarded from presenter

PRESENTER_PORT = 12349
VIEWER_PORT = 12350
HOST = '0.0.0.0'

class ScreenShareServer:
    def __init__(self, host=HOST, presenter_port=PRESENTER_PORT, viewer_port=VIEWER_PORT):
        self.host = host
        self.presenter_port = presenter_port
        self.viewer_port = viewer_port

        self.presenter_conn = None  # (conn, addr)
        self.presenter_lock = threading.Lock()

        self.viewer_conns = []  # list of (conn, addr)
        self.viewer_lock = threading.Lock()

        self.running = True

        # TCP sockets
        self.presenter_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.presenter_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.presenter_sock.bind((self.host, self.presenter_port))
        self.presenter_sock.listen(1)

        self.viewer_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.viewer_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.viewer_sock.bind((self.host, self.viewer_port))
        self.viewer_sock.listen(5)

        print(f"ScreenShareServer: presenter port={self.presenter_port}, viewer port={self.viewer_port}")

    def start(self):
        # Dead viewers are detected by the heartbeat in _handle_viewer
        threading.Thread(target=self._accept_presenter_loop, daemon=True).start()
        threading.Thread(target=self._accept_viewer_loop, daemon=True).start()

    def _accept_presenter_loop(self):
        while self.running:
            try:
                conn, addr = self.presenter_sock.accept()
                print(f"Presenter connection attempt from {addr}")

                with self.presenter_lock:
                    if self.presenter_conn is not None:
                        # Reject additional presenter
                        try:
                            conn.sendall(b"BUSY:ANOTHER_PRESENTER_ACTIVE\n")
                        except:
                            pass
                        conn.close()
                        print(f"Rejected additional presenter from {addr}")
                    else:
                        conn.settimeout(5.0)  # Set timeout to detect disconnections
                        self.presenter_conn = (conn, addr)
                        print(f"Presenter connected from {addr}")
                        threading.Thread(target=self._handle_presenter, args=(conn, addr), daemon=True).start()

            except Exception as e:
                print(f"Presenter accept error: {e}")
                time.sleep(0.1)

    def _accept_viewer_loop(self):
        while self.running:
            try:
                conn, addr = self.viewer_sock.accept()
                print(f"Viewer connected from {addr}")
                with self.viewer_lock:
                    self.viewer_conns.append((conn, addr))
                threading.Thread(target=self._handle_viewer, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"Viewer accept error: {e}")
                time.sleep(0.1)

    def _handle_presenter(self, conn, addr):
        # Presenter stream loop: read 4-byte length then JPEG payload
        try:
            conn.settimeout(5.0)
            while self.running:
                # Read exactly 4 bytes for length
                length_bytes = self._recv_all(conn, 4)
                if not length_bytes:
                    break
                frame_len = struct.unpack('>I', length_bytes)[0]
                if frame_len == 0:
                    # control frame: STOP
                    print("Presenter sent STOP control")
                    self._broadcast_control(b"STOP")
                    continue

                # Read frame bytes
                frame_bytes = self._recv_all(conn, frame_len)
                if not frame_bytes:
                    break

                # Forward to all viewers: send 4-byte length + bytes
                self._broadcast_frame(frame_bytes)

        except Exception as e:
            print(f"Presenter connection error {addr}: {e}")
        finally:
            print(f"Presenter disconnected {addr}")
            with self.presenter_lock:
                try:
                    conn.close()
                except:
                    pass
                self.presenter_conn = None
                # Notify viewers that presenter stopped
                self._broadcast_control(b"STOP")

    def _handle_viewer(self, conn, addr):
        # For now, viewers only receive frames. If they disconnect, remove them.
        try:
            conn.settimeout(10.0)  # Generous send timeout for slow Wi-Fi / hotspot links
            while self.running:
                with self.viewer_lock:
                    if not any(c is conn for c, _ in self.viewer_conns):
                        break  # removed by a failed broadcast
                    try:
                        # Heartbeat, sent under the lock so it never interleaves with a frame
                        conn.sendall(struct.pack('>I', 0) + b'PING\n')
                    except OSError:
                        break
                time.sleep(2.0)
        except Exception as e:
            print(f"Viewer error {addr}: {e}")
        finally:
            print(f"Viewer disconnected {addr}")
            with self.viewer_lock:
                self.viewer_conns = [(c,a) for (c,a) in self.viewer_conns if c is not conn]
            try:
                conn.close()
            except:
                pass

    def _broadcast_frame(self, frame_bytes: bytes):
        # send to all viewers; remove faulty conns
        with self.viewer_lock:
            remove = []
            broadcast_count = 0
            for conn, addr in list(self.viewer_conns):
                try:
                    conn.sendall(struct.pack('>I', len(frame_bytes)) + frame_bytes)
                    broadcast_count += 1
                except Exception as e:
                    # Don't print connection closed errors as they're normal when clients disconnect
                    if not isinstance(e, (ConnectionResetError, ConnectionAbortedError)):
                        print(f"Error sending frame to {addr}: {e}")
                    try:
                        conn.close()
                    except:
                        pass
                    remove.append((conn, addr))
            
            # Remove disconnected viewers
            for item in remove:
                if item in self.viewer_conns:  # Check if still exists
                    self.viewer_conns.remove(item)
                    print(f"Removed disconnected viewer {item[1]}")

    def _broadcast_control(self, msg: bytes):
        # Send small control messages (prefix length 0) as: length=0 then ASCII msg + newline
        # Viewers will interpret control messages
        with self.viewer_lock:
            remove = []
            for conn, addr in list(self.viewer_conns):
                try:
                    # We'll send a zero length and then the control payload framed as length-prefixed small message
                    # For simplicity, send a 4-byte zero then the control msg terminated by newline
                    conn.sendall(struct.pack('>I', 0) + msg + b'\n')
                except Exception as e:
                    # Don't print connection closed errors as they're normal when clients disconnect
                    if not isinstance(e, (ConnectionResetError, ConnectionAbortedError)):
                        print(f"Error sending control to {addr}: {e}")
                    try:
                        conn.close()
                    except:
                        pass
                    remove.append((conn, addr))
            
            # Remove disconnected viewers
            for item in remove:
                if item in self.viewer_conns:  # Check if still exists
                    self.viewer_conns.remove(item)
                    print(f"Removed disconnected viewer {item[1]}")

    def _recv_all(self, conn, n):
        data = b''
        while len(data) < n:
            chunk = None
            try:
                chunk = conn.recv(n - len(data))
            except socket.timeout:
                return None
            if not chunk:
                return None
            data += chunk
        return data

    def stop(self):
        self.running = False
        try:
            self.presenter_sock.close()
        except:
            pass
        try:
            self.viewer_sock.close()
        except:
            pass
        with self.viewer_lock:
            for conn, _ in self.viewer_conns:
                try:
                    conn.close()
                except:
                    pass
        with self.presenter_lock:
            if self.presenter_conn:
                try:
                    self.presenter_conn[0].close()
                except:
                    pass

if __name__ == '__main__':
    server = ScreenShareServer()
    server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('Shutting down screenshare server...')
        server.stop()
