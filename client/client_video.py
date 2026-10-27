import socket
import threading
import cv2
import numpy as np
import struct
import tkinter as tk
from PIL import Image, ImageTk
import time
from discovery import disable_udp_connreset

HEARTBEAT_INTERVAL = 3.0  # re-register often; a single UDP packet can be lost on Wi-Fi

class VideoClient:
    def __init__(self, host='localhost', port=12347, username="User"):
        self.host = host
        self.port = port
        self.username = username
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        disable_udp_connreset(self.client)
        self.client.bind(('', 0))  # bind before recvfrom (Windows raises WinError 10022 otherwise)
        self.cap = None
        self.running = False
        self.video_frames = {}  # username: frame_widget
        # Track whether this client is receiving remote video and/or capturing local camera
        self.receiving_started = False
        self.capturing_started = False

    def start_video(self, parent_frame):
        """Turn on local camera (like Google Meet). Always keep receiver/UI alive."""
        # Always start receiver/UI if not already running
        if not self.receiving_started:
            started = self.start_receiving(parent_frame)
            if not started:
                return False

        # Start capturing local camera if not already
        if not self.capturing_started:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                print("Cannot open webcam")
                return False
            self.capturing_started = True
            threading.Thread(target=self.capture_and_send, daemon=True).start()
        return True

    def start_receiving(self, parent_frame):
        """Start the receive thread and UI which displays remote videos.

        This allows clients who don't enable their camera to still receive and
        display other users' video streams.
        """
        if self.receiving_started:
            return True

        self.running = True

        # Register with the server and keep re-registering (heartbeat)
        threading.Thread(target=self.send_heartbeat, daemon=True).start()

        # Start receive thread
        threading.Thread(target=self.receive_video, daemon=True).start()

        # Create video display area
        self.video_frame = tk.Frame(parent_frame, bg='#2c3e50')
        self.video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create grid container for all video streams
        self.grid_frame = tk.Frame(self.video_frame, bg='#2c3e50')
        self.grid_frame.pack(fill=tk.BOTH, expand=True)

        # Dictionary to hold all video frames (including own)
        self.all_video_frames = {}  # username: frame_widget
        self.video_canvases = {}    # username: canvas_widget
        self.last_frame_time = {}   # username: timestamp for cleanup
        self.last_cleanup = 0       # timestamp for periodic cleanup

        # Initialize own video slot (will be blank until local preview updates)
        self.create_video_slot(self.username)

        self.receiving_started = True
        return True

    def send_heartbeat(self):
        username_bytes = self.username.encode('utf-8')
        data = struct.pack("Q", len(username_bytes)) + username_bytes
        while self.running:
            try:
                self.client.sendto(data, (self.host, self.port))
            except OSError as e:
                print(f"Video heartbeat error: {e}")
            time.sleep(HEARTBEAT_INTERVAL)

    def shutdown(self):
        """Stop camera and all video threads (call when the app closes)."""
        self.stop_video()
        self.running = False
        try:
            self.client.close()
        except OSError:
            pass

    def stop_video(self):
        """Turn off local camera (like Google Meet). Keep receiver/UI alive."""
        if self.capturing_started:
            self.capturing_started = False
            if self.cap:
                self.cap.release()
                self.cap = None
            # Send a stop notification to server
            try:
                username_bytes = self.username.encode('utf-8')
                stop_packet = struct.pack("Q", len(username_bytes)) + username_bytes + b"STOP_VIDEO"
                self.client.sendto(stop_packet, (self.host, self.port))
            except:
                pass
            # Set own video slot to black
            if self.username in self.video_canvases:
                canvas = self.video_canvases[self.username]
                canvas.delete("all")
                canvas.configure(bg='black')

    def capture_and_send(self):
        while self.running:
            if not self.capturing_started:
                time.sleep(0.1)
                continue
            try:
                ret, frame = self.cap.read()
                if ret:
                    frame = cv2.resize(frame, (320, 240))
                    _, encoded_frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    frame_data = encoded_frame.tobytes()
                    username_bytes = self.username.encode('utf-8')
                    data = struct.pack("Q", len(username_bytes)) + username_bytes + frame_data
                    self.client.sendto(data, (self.host, self.port))
                    self.update_local_preview(frame)
                time.sleep(0.03)
            except Exception as e:
                print(f"Capture error: {e}")
                break

    def receive_video(self):
        active_users = set([self.username])
        while self.running:
            try:
                packet, _ = self.client.recvfrom(65536)
                try:
                    username_len = struct.unpack("Q", packet[:8])[0]
                    username = packet[8:8+username_len].decode('utf-8')
                    frame_data = packet[8+username_len:]
                except:
                    continue
                # Skip if this is our own stream
                if username == self.username:
                    continue
                # Handle video stop notification
                if frame_data == b"STOP_VIDEO":
                    # Always ensure the slot exists and is cleared/black
                    def clear_user_video():
                        if username not in self.video_canvases:
                            self.create_video_slot(username)
                        canvas = self.video_canvases[username]
                        canvas.delete("all")
                        canvas.configure(bg='black')
                    self.video_frame.after(0, clear_user_video)
                    # Do NOT remove from last_frame_time; keep slot in grid
                    continue
                # Track active users and update timestamp
                active_users.add(username)
                self.last_frame_time[username] = time.time()
                # Decode frame
                frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is not None and frame.size > 0:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame)
                    imgtk = ImageTk.PhotoImage(image=img)
                    self.update_video_display(username, imgtk)
                # Periodically clean up inactive users (every 5 seconds)
                current_time = time.time()
                if current_time - self.last_cleanup > 5.0:
                    self.cleanup_inactive_users(active_users)
                    self.last_cleanup = current_time
            except Exception as e:
                if not self.running:
                    break
                print(f"Receive error: {e}")
                continue

    def update_local_preview(self, frame):
        def update_canvas():
            try:
                # Convert frame for Tkinter
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                imgtk = ImageTk.PhotoImage(image=img)

                # Update local canvas
                if self.username in self.video_canvases:
                    canvas = self.video_canvases[self.username]
                    canvas.delete("all")
                    canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
                    canvas.image = imgtk  # Keep reference
            except Exception as e:
                print(f"Local preview update error: {e}")

        # Schedule update on main thread with slight delay
        self.video_frame.after(10, update_canvas)

    def update_video_display(self, username, imgtk):
        def update_canvas():
            if username not in self.all_video_frames:
                # Create new frame for this user
                self.create_video_slot(username)

            # Update the canvas
            if username in self.video_canvases:
                canvas = self.video_canvases[username]
                canvas.delete("all")  # Clear previous image
                canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
                canvas.image = imgtk  # Keep reference

        # Schedule update on main thread with slight delay
        self.video_frame.after(10, update_canvas)

    def create_video_slot(self, username):
        """Create a new video slot in the grid layout"""
        # Add new user to the list
        if username not in self.all_video_frames:
            self.all_video_frames[username] = None
            self.video_canvases[username] = None
            self.last_frame_time[username] = time.time()

        self.rebuild_grid()

    def rebuild_grid(self):
        """Rebuild the entire grid layout"""
        # Get active users (those with recent frames)
        current_time = time.time()
        active_users = [user for user in self.all_video_frames.keys()
                       if current_time - self.last_frame_time.get(user, 0) < 10.0]  # 10 second timeout

        # Ensure self is always included
        if self.username not in active_users:
            active_users.insert(0, self.username)

        # Calculate grid layout
        num_users = len(active_users)
        if num_users == 0:
            return

        cols = min(3, max(1, num_users))  # Max 3 columns
        rows = (num_users + cols - 1) // cols

        # Clear and reconfigure grid
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        # Create frames for active users
        for i, user in enumerate(active_users):
            row = i // cols
            col = i % cols

            # Create user frame
            user_frame = tk.Frame(self.grid_frame, bg='#34495e', relief='raised', borderwidth=2)
            user_frame.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')

            # Configure grid weights
            self.grid_frame.grid_rowconfigure(row, weight=1)
            self.grid_frame.grid_columnconfigure(col, weight=1)

            # Add label
            label_text = f"{user} (You)" if user == self.username else user
            label = tk.Label(user_frame, text=label_text, bg='#34495e', fg='white', font=('Helvetica', 10, 'bold'))
            label.pack()

            # Add canvas
            canvas = tk.Canvas(user_frame, width=320, height=240, bg='black')
            canvas.pack(fill=tk.BOTH, expand=True)

            self.all_video_frames[user] = user_frame
            self.video_canvases[user] = canvas

    def cleanup_inactive_users(self, active_users):
        """Remove users who haven't sent frames recently"""
        current_time = time.time()
        to_remove = []

        for user in list(self.all_video_frames.keys()):
            if user == self.username:
                continue  # Never remove self
            if user not in active_users or current_time - self.last_frame_time.get(user, 0) > 10.0:
                to_remove.append(user)

        if to_remove:
            for user in to_remove:
                if user in self.all_video_frames:
                    del self.all_video_frames[user]
                if user in self.video_canvases:
                    del self.video_canvases[user]
                if user in self.last_frame_time:
                    del self.last_frame_time[user]
            self.rebuild_grid()

if __name__ == "__main__":
    # Test code
    root = tk.Tk()
    video_client = VideoClient()
    video_client.start_video(root)
    root.mainloop()