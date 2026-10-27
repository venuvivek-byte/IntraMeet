import socket
import threading
import struct
import time
import io
import sys

try:
    import tkinter as tk
    from PIL import Image, ImageTk
    import mss
except Exception as e:
    print("Missing dependencies for screenshare UI:", e)
    print("Install requirements: pip install mss pillow")
    raise

SERVER_HOST = 'localhost'
PRESENTER_PORT = 12349
VIEWER_PORT = 12350

CAPTURE_INTERVAL = 0.1  # seconds between frames when presenting
JPEG_QUALITY = 80  # starting quality, will be reduced if frame is too large
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY = 1.0  # seconds between reconnection attempts
MAX_FRAME_BYTES = 90000  # try to keep frames under ~90KB for reliable delivery
MIN_FRAME_WIDTH = 480

class ScreenShareClient:
    def __init__(self, server_host=SERVER_HOST, presenter_port=PRESENTER_PORT, viewer_port=VIEWER_PORT, username="User"):
        self.server_host = server_host
        self.presenter_port = presenter_port
        self.viewer_port = viewer_port
        self.username = username

        self.presenter_sock = None
        self.viewer_sock = None

        self.is_presenting = False
        self.present_thread = None

        # These will be set by the main client
        self.remote_canvas = None
        self.start_btn = None
        self.status_label = None
        # Keep latest image reference for tkinter
        self._tk_image = None
        self._tk_remote = None
        self.mss_inst = None
        self.viewer_thread = None
        self.is_presenter_view = False

        # Start viewer connection
        self.start_viewer()

    def start_viewer(self):
        if not self.viewer_thread or not self.viewer_thread.is_alive():
            self.viewer_thread = threading.Thread(target=self._start_viewer_receiver, daemon=True)
            self.viewer_thread.start()


    def toggle_present(self):
        if not self.is_presenting:
            # Start presenting
            self.is_presenting = True
            if self.start_btn:
                self.start_btn.config(text='Stop Presenting')
                self.start_btn.config(state='disabled')  # Temporarily disable while connecting
            if self.status_label:
                self.status_label.config(text='Connecting to server...')
            
                # Mark this client as presenter to avoid self-view
                self.is_presenter_view = True
            
            self.present_thread = threading.Thread(target=self._present_loop, daemon=True)
            self.present_thread.start()

            # Enable button after a short delay
            if self.start_btn:
                def enable_button():
                    if self.is_presenting:
                        self.start_btn.config(state='normal')
                        if self.status_label:
                            self.status_label.config(text='Screen sharing active - presenting...')
                    else:
                        self.start_btn.config(text='Start Presenting', state='normal')
                        if self.status_label:
                            self.status_label.config(text='Failed to connect to server')
                self.start_btn.after(800, enable_button)
        else:
            # Stop presenting
            self.is_presenting = False
            self.is_presenter_view = False
            if self.start_btn:
                self.start_btn.config(text='Start Presenting')
            if self.status_label:
                self.status_label.config(text='Screen sharing ready')
            # Send a zero-length STOP control to server if socket present
            try:
                if self.presenter_sock:
                    self.presenter_sock.sendall(struct.pack('>I', 0) + b'STOP\n')
            except Exception:
                pass
            try:
                if self.presenter_sock:
                    self.presenter_sock.close()
            except:
                pass
            self.presenter_sock = None

    def _connect_presenter(self):
        attempts = 0
        while attempts < MAX_RECONNECT_ATTEMPTS:
            try:
                s = socket.create_connection((self.server_host, self.presenter_port), timeout=5.0)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                # Keepalive tuning is not available on every OS/Python build
                for opt, val in (('TCP_KEEPIDLE', 10), ('TCP_KEEPINTVL', 3), ('TCP_KEEPCNT', 3)):
                    if hasattr(socket, opt):
                        try:
                            s.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
                        except OSError:
                            pass
                # A presenter that answers BUSY is rejected by the server
                s.settimeout(0.3)
                try:
                    if s.recv(64).startswith(b'BUSY'):
                        print('Another user is already presenting')
                        s.close()
                        return None
                except socket.timeout:
                    pass
                return s
            except Exception as e:
                print(f'Failed to connect to presenter port (attempt {attempts + 1}/{MAX_RECONNECT_ATTEMPTS}):', e)
                attempts += 1
                if attempts < MAX_RECONNECT_ATTEMPTS:
                    time.sleep(RECONNECT_DELAY)
        return None

    def _present_loop(self):
        # Connect to server presenter port
        self.presenter_sock = self._connect_presenter()
        if not self.presenter_sock:
            self.is_presenting = False
            self._ui(lambda: self.start_btn and self.start_btn.config(text='Start Presenting', state='normal'))
            self._ui(lambda: self.status_label and self.status_label.config(text='Could not present (server unreachable or someone else is presenting)'))
            return

        print('Started presenting')
        last_frame_time = 0
        retry_count = 0
        max_retries = 3

        try:
            # Initialize mss in the capturing thread
            with mss.mss() as self.mss_inst:
                monitor = self.mss_inst.monitors[0]  # Get the monitor configuration first
                
                while self.is_presenting:
                    current_time = time.time()
                    # Limit frame rate to avoid overwhelming the connection
                    if current_time - last_frame_time < CAPTURE_INTERVAL:
                        time.sleep(0.01)  # Small sleep to prevent CPU hogging
                        continue

                    # Capture full screen with error handling
                    try:
                        sct_img = self.mss_inst.grab(monitor)
                        last_frame_time = current_time
                        retry_count = 0  # Reset retry count on successful capture
                    except Exception as e:
                        print(f"Screen capture error: {e}")
                        retry_count += 1
                        if retry_count >= max_retries:
                            print("Too many capture failures, stopping presentation")
                            self.is_presenting = False
                            break
                        time.sleep(0.5)  # Wait before retry
                        continue

                    try:
                        # Convert to PIL Image
                        img = Image.frombytes('RGB', sct_img.size, sct_img.rgb)

                        # Optimize image size for network transmission
                        target_width = 1280
                        if img.width > target_width:
                            ratio = target_width / float(img.width)
                            target_height = int(float(img.height) * ratio)
                            img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

                        # Compress to JPEG with adaptive quality, then downscale if still too large
                        buf = io.BytesIO()
                        current_quality = JPEG_QUALITY
                        while current_quality >= 30:  # Don't go below quality 30
                            buf.seek(0)
                            buf.truncate()
                            img.save(buf, format='JPEG', quality=current_quality)
                            if len(buf.getvalue()) <= MAX_FRAME_BYTES:
                                break
                            current_quality -= 10

                        data = buf.getvalue()

                        # If frame still too large after reducing quality, progressively downscale image
                        downscale_attempts = 0
                        while len(data) > MAX_FRAME_BYTES and img.width > MIN_FRAME_WIDTH and downscale_attempts < 6:
                            downscale_attempts += 1
                            new_width = max(MIN_FRAME_WIDTH, int(img.width * 0.75))
                            ratio = new_width / float(img.width)
                            new_height = int(float(img.height) * ratio)
                            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            # recompress at lower quality floor
                            buf.seek(0)
                            buf.truncate()
                            img.save(buf, format='JPEG', quality=max(30, current_quality))
                            data = buf.getvalue()

                        # Final safety: if still too large, truncate payload to MAX_FRAME_BYTES (will likely corrupt image)
                        if len(data) > MAX_FRAME_BYTES:
                            print(f"Warning: frame size {len(data)} exceeds limit {MAX_FRAME_BYTES}, truncating")
                            data = data[:MAX_FRAME_BYTES]

                        # Send length-prefixed frame with timeout
                        try:
                            self.presenter_sock.settimeout(2.0)  # 2 second timeout for send
                            self.presenter_sock.sendall(struct.pack('>I', len(data)) + data)

                            # Keep track of successful sends
                            retry_count = 0
                        except (socket.timeout, ConnectionError, OSError) as e:
                            # Handle fatal socket errors (WinError 10053/10054) gracefully
                            err_no = getattr(e, 'errno', None)
                            msg = str(e)
                            print(f'Presenter send failed: {msg}')
                            # If connection was aborted by local host or reset, stop presenting
                            if err_no in (10053, 10054) or '10053' in msg or '10054' in msg:
                                print('Fatal socket error detected (connection aborted). Stopping presentation.')
                                try:
                                    self.presenter_sock.close()
                                except:
                                    pass
                                self.presenter_sock = None
                                self.is_presenting = False
                                break

                            # Non-fatal: increment retry, back off a bit
                            retry_count += 1
                            if retry_count >= max_retries:
                                print("Too many send failures, stopping presentation")
                                try:
                                    self.presenter_sock.close()
                                except:
                                    pass
                                self.presenter_sock = None
                                self.is_presenting = False
                                break
                            time.sleep(0.2)
                            continue

                    except Exception as e:
                        print(f'Image processing error: {e}')
                        retry_count += 1
                        if retry_count >= max_retries:
                            print("Too many processing failures, stopping presentation")
                            self.is_presenting = False
                            break
                        continue
        finally:
            try:
                if self.presenter_sock:
                    self.presenter_sock.close()
            except:
                pass
            self.presenter_sock = None
            self.is_presenting = False
            self._ui(lambda: self.start_btn and self.start_btn.config(text='Start Presenting', state='normal'))
            print('Stopped presenting')

    def _start_viewer_receiver(self):
        # Connect to server viewer port and receive frames
        while True:
            try:
                s = socket.create_connection((self.server_host, self.viewer_port), timeout=5.0)
                s.settimeout(None)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.viewer_sock = s
                print('Connected as viewer to server')

                # Receiving loop
                while True:
                    # Read 4-byte length
                    length_bytes = self._recv_all(s, 4)
                    if not length_bytes:
                        raise ConnectionError('Disconnected')
                    frame_len = struct.unpack('>I', length_bytes)[0]
                    if frame_len == 0:
                        # Control message: read until newline
                        ctrl = self._recv_until_newline(s)
                        if ctrl and ctrl.strip().upper() == b'STOP':
                            # Clear remote canvas or show "Presenter stopped"
                            self._display_control_message('Presenter stopped')
                        continue

                    # Read the frame
                    frame_bytes = self._recv_all(s, frame_len)
                    if not frame_bytes:
                        raise ConnectionError('Disconnected while reading frame')

                    # Convert bytes to image and display
                    try:
                        img = Image.open(io.BytesIO(frame_bytes))
                        # Keep aspect ratio and fit into canvas
                        img.thumbnail((1024, 768))
                        tkimg = ImageTk.PhotoImage(img)
                        # Need to keep reference to avoid GC
                        self._tk_remote = tkimg
                        self._ui(lambda img=tkimg: self.remote_canvas and self.remote_canvas.config(image=img, text=''))
                    except Exception as e:
                        print('Failed to decode frame:', e)

            except Exception as e:
                print('Viewer connection lost, retrying in 1s:', e)
                try:
                    if self.viewer_sock:
                        self.viewer_sock.close()
                except:
                    pass
                self.viewer_sock = None
                time.sleep(1.0)

    def _ui(self, fn):
        # Tkinter widgets must only be touched from the main thread
        widget = self.remote_canvas or self.start_btn
        try:
            if widget:
                widget.after(0, fn)
        except (RuntimeError, tk.TclError):
            pass

    def _display_control_message(self, text: str):
        # Display a simple text message in the remote area
        self._ui(lambda: self.remote_canvas and self.remote_canvas.config(text=text, image='', fg='white'))

    def _recv_all(self, sock, n):
        data = b''
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _recv_until_newline(self, sock):
        data = b''
        while True:
            ch = sock.recv(1)
            if not ch:
                return None
            data += ch
            if ch == b'\n':
                return data

if __name__ == '__main__':
    # Standalone test mode
    root = tk.Tk()
    root.title('Screen Share Test')
    
    frame = tk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True)
    
    client = ScreenShareClient()
    client.remote_canvas = tk.Label(frame)
    client.remote_canvas.pack(fill=tk.BOTH, expand=True)
    
    client.start_btn = tk.Button(frame, text='Start Presenting', command=client.toggle_present)
    client.start_btn.pack()
    
    client.status_label = tk.Label(frame, text='Screen sharing ready')
    client.status_label.pack()
    
    root.mainloop()
