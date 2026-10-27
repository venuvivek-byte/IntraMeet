# Main client file to integrate all modules
import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog, filedialog, messagebox
import socket
import sys
import threading
from discovery import discover_server
from client_filesharing import FileSharingClient
from client_video import VideoClient
from client_audio import AudioClient
from client_screenshare import ScreenShareClient

class MainClient:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("IntraMeet - LAN Collaboration")
        self.root.geometry("1000x700")
        self.root.configure(bg='#2c3e50')  # Dark background

        # Set theme
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background='#34495e', borderwidth=0)
        style.configure('TNotebook.Tab', background='#34495e', foreground='white', padding=[10, 5])
        style.map('TNotebook.Tab', background=[('selected', '#3498db')])
        style.configure('TFrame', background='#2c3e50')
        style.configure('TLabel', background='#2c3e50', foreground='white', font=('Helvetica', 10))
        style.configure('TButton', background='#3498db', foreground='white', font=('Helvetica', 10, 'bold'))

        # Header
        header = tk.Frame(self.root, bg='#34495e', height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="IntraMeet", bg='#34495e', fg='white', font=('Helvetica', 16, 'bold')).pack(pady=10)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Chat tab
        self.chat_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.chat_frame, text="💬 Chat")

        self.chat_area = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, state='disabled', bg='#ecf0f1', fg='#2c3e50', font=('Helvetica', 10))
        self.chat_area.pack(pady=10, padx=10, side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.user_listbox = tk.Listbox(self.chat_frame, bg='#ecf0f1', fg='#2c3e50', font=('Helvetica', 10))
        self.user_listbox.pack(pady=10, padx=(0, 10), side=tk.RIGHT, fill=tk.Y)

        input_frame = tk.Frame(self.chat_frame, bg='#2c3e50')
        input_frame.pack(fill=tk.X, padx=10, pady=10)
        self.message_entry = tk.Entry(input_frame, bg='#ecf0f1', fg='#2c3e50', font=('Helvetica', 10))
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.message_entry.bind("<Return>", self.send_message)
        self.send_button = tk.Button(input_frame, text="Send", bg='#3498db', fg='white', font=('Helvetica', 10, 'bold'), command=self.send_message)
        self.send_button.pack(side=tk.RIGHT, padx=(10, 0))

        # Video Conferencing tab
        self.video_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.video_frame, text="📹 Video")

        # Video controls
        control_frame = tk.Frame(self.video_frame, bg='#2c3e50')
        control_frame.pack(pady=10)
        self.start_video_btn = tk.Button(control_frame, text="Start Video", bg='#3498db', fg='white', font=('Helvetica', 10, 'bold'), command=self.start_video)
        self.start_video_btn.pack(side=tk.LEFT, padx=5)
        self.stop_video_btn = tk.Button(control_frame, text="Stop Video", bg='#e74c3c', fg='white', font=('Helvetica', 10, 'bold'), command=self.stop_video, state='disabled')
        self.stop_video_btn.pack(side=tk.LEFT, padx=5)

        # Video display area
        self.video_display_frame = tk.Frame(self.video_frame, bg='#2c3e50')
        self.video_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Video client
        self.video_client = None

        # Audio Conferencing tab
        self.audio_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.audio_frame, text="🎤 Audio")

        # Audio controls
        control_frame = tk.Frame(self.audio_frame, bg='#2c3e50')
        control_frame.pack(pady=10)
        self.start_audio_btn = tk.Button(control_frame, text="Mike On", bg='#3498db', fg='white', font=('Helvetica', 10, 'bold'), command=self.start_audio)
        self.start_audio_btn.pack(side=tk.LEFT, padx=5)
        # Mike Off button is present but disabled until Mike On is pressed
        self.stop_audio_btn = tk.Button(control_frame, text="Mike Off", bg='#e74c3c', fg='white', font=('Helvetica', 10, 'bold'), command=self.stop_audio, state='disabled')
        self.stop_audio_btn.pack(side=tk.LEFT, padx=5)

        # Audio status
        self.audio_status = tk.Label(self.audio_frame, text="Audio conferencing ready", bg='#2c3e50', fg='white', font=('Helvetica', 10))
        self.audio_status.pack(pady=10)

        # Audio client
        self.audio_client = None

        # Screen Sharing tab
        self.screen_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.screen_frame, text="🖥️ Screen Share")
        
        # Screen share control frame
        screen_control_frame = tk.Frame(self.screen_frame, bg='#2c3e50')
        screen_control_frame.pack(pady=10)
        
        self.start_screen_btn = tk.Button(screen_control_frame, text="Start Presenting", 
                                        bg='#3498db', fg='white', 
                                        font=('Helvetica', 10, 'bold'), 
                                        command=self.toggle_screen_share)
        self.start_screen_btn.pack(side=tk.LEFT, padx=5)
        
        # Screen share status
        self.screen_status = tk.Label(self.screen_frame, text="Screen sharing ready", 
                                    bg='#2c3e50', fg='white', 
                                    font=('Helvetica', 10))
        self.screen_status.pack(pady=10)
        
        # Remote screen display area
        self.remote_screen_frame = tk.Frame(self.screen_frame, bg='#2c3e50')
        self.remote_screen_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.remote_screen_label = tk.Label(self.remote_screen_frame, bg='#34495e')
        self.remote_screen_label.pack(fill=tk.BOTH, expand=True)
        
        # Screen sharing client
        self.screen_client = None

        # File Sharing tab
        self.file_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.file_frame, text="📁 File Share")

        # File sharing components
        self.file_client = FileSharingClient()

        button_frame = tk.Frame(self.file_frame, bg='#2c3e50')
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Upload File", bg='#3498db', fg='white', font=('Helvetica', 10, 'bold'), command=self.upload_file).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Refresh List", bg='#3498db', fg='white', font=('Helvetica', 10, 'bold'), command=self.refresh_file_list).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Download Selected", bg='#27ae60', fg='white', font=('Helvetica', 10, 'bold'), command=self.download_selected).pack(side=tk.LEFT, padx=5)

        self.file_listbox = tk.Listbox(self.file_frame, bg='#ecf0f1', fg='#2c3e50', font=('Helvetica', 10))
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.file_listbox.bind('<Double-1>', self.download_file)

        self.progress = ttk.Progressbar(self.file_frame, orient="horizontal", mode="determinate", style="green.Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X, padx=10, pady=(0,10))

        # Style for green progress bar
        style = ttk.Style()
        style.configure("green.Horizontal.TProgressbar", background='green')

        # Connection
        self.client = None
        self.server_host = None
        self.username = None
        self.receive_thread = None

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Auto-refresh file list every 5 seconds
        self.refresh_timer = None

    def choose_server(self):
        """Find the server on the LAN (works on an offline hotspot) and let the
        user confirm or type its IP. Returns a connected chat socket or None."""
        guess = sys.argv[1] if len(sys.argv) > 1 else discover_server() or ''
        while True:
            host = simpledialog.askstring(
                "Server",
                "Server IP address (shown in the server window):" +
                ("" if guess else "\n\nNo server found automatically on this network."),
                initialvalue=guess, parent=self.root)
            if not host:
                return None
            host = host.strip()
            try:
                sock = socket.create_connection((host, 12345), timeout=5.0)
                sock.settimeout(None)
                self.server_host = host
                return sock
            except OSError as e:
                messagebox.showerror(
                    "Connection failed",
                    f"Could not reach the server at {host}:12345\n\n{e}\n\n"
                    "Check that both devices are on the same Wi-Fi/hotspot, the server is running, "
                    "and the server PC's firewall allows IntraMeet (run allow_firewall.bat as admin).",
                    parent=self.root)
                guess = host

    def connect(self):
        try:
            self.root.withdraw()
            self.client = self.choose_server()
            if not self.client:
                self.root.destroy()
                return
            self.file_client.host = self.server_host
            while True:
                self.username = simpledialog.askstring("Username", "Enter your username:", parent=self.root)
                if self.username:
                    self.username = self.username.strip().replace(',', ' ')
                    self.client.sendall(self.username.encode('utf-8'))
                    response = self.client.recv(1024).decode('utf-8')
                    if response == 'USERNAME_OK':
                        break
                    else:
                        messagebox.showerror("Error", "Username already taken. Please choose another one.")
                else:
                    self.client.close()
                    self.root.destroy()
                    return

            self.root.title(f"IntraMeet - {self.username} @ {self.server_host}")
            self.root.deiconify()
            self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
            self.receive_thread.start()
            self.start_auto_refresh()
            # Initialize screen share client as a viewer (so all clients receive presenter frames)
            try:
                self.screen_client = ScreenShareClient(server_host=self.server_host, username=self.username)
                # Wire UI elements
                self.screen_client.remote_canvas = self.remote_screen_label
                self.screen_client.start_btn = self.start_screen_btn
                self.screen_client.status_label = self.screen_status
            except Exception as e:
                print(f"Failed to initialize screen share client: {e}")
            # Initialize video client in receiving mode so users who don't start
            # their camera still receive and see other participants' video.
            try:
                self.video_client = VideoClient(host=self.server_host, username=self.username)
                # Start receiving remote video immediately (no local capture yet)
                self.video_client.start_receiving(self.video_display_frame)
            except Exception as e:
                print(f"Failed to initialize video receiving: {e}")
            self.root.mainloop()

        except Exception as e:
            print(f"Connection failed: {e}")
            messagebox.showerror("IntraMeet", f"Connection failed: {e}")

    def send_message(self, event=None):
        message = self.message_entry.get().replace('\n', ' ')
        if message:
            try:
                self.client.sendall((message + '\n').encode('utf-8'))
            except OSError:
                messagebox.showerror("Chat", "Lost connection to the server.")
                return
            self.show_chat_line(f"you: {message}")
            self.message_entry.delete(0, tk.END)

    def show_chat_line(self, line):
        self.chat_area.config(state='normal')
        self.chat_area.insert(tk.END, line + '\n')
        self.chat_area.config(state='disabled')
        self.chat_area.yview(tk.END)

    def update_user_list(self, users):
        self.user_listbox.delete(0, tk.END)
        for user in users:
            self.user_listbox.insert(tk.END, user)

    def handle_chat_message(self, message):
        if message.startswith('USERLIST:'):
            users = [u for u in message[len('USERLIST:'):].split(',') if u]
            self.root.after(0, self.update_user_list, users)
        elif message:
            # Skip displaying own messages as they are already shown locally
            if message.startswith(f"{self.username}: "):
                return
            self.root.after(0, self.show_chat_line, message)

    def receive_messages(self):
        # Server messages are newline-delimited; TCP may merge or split them
        buffer = ''
        while True:
            try:
                data = self.client.recv(4096)
            except OSError:
                break
            if not data:
                break
            buffer += data.decode('utf-8', errors='replace')
            while '\n' in buffer:
                message, buffer = buffer.split('\n', 1)
                try:
                    self.handle_chat_message(message)
                except (RuntimeError, tk.TclError):
                    return  # window closed
        try:
            self.root.after(0, self.show_chat_line, "*** Disconnected from server ***")
        except (RuntimeError, tk.TclError):
            pass

    def upload_file(self):
        if self.username:
            if self.file_client.upload_file(self.username):
                self.refresh_file_list()

    def refresh_file_list(self):
        self.file_listbox.delete(0, tk.END)
        files = self.file_client.list_files()
        for file in files:
            self.file_listbox.insert(tk.END, file)

    def download_selected(self):
        selection = self.file_listbox.curselection()
        if selection:
            filename = self.file_listbox.get(selection[0])
            self.progress['value'] = 0
            if self.file_client.download_file(filename, self.update_progress):
                self.progress['value'] = 100

    def download_file(self, event):
        # Double-click download
        self.download_selected()

    def update_progress(self, percent):
        self.progress['value'] = percent
        self.root.update_idletasks()

    def start_auto_refresh(self):
        self.refresh_file_list()
        self.refresh_timer = self.root.after(5000, self.start_auto_refresh)  # Refresh every 5 seconds

    def start_video(self):
        if self.username:
            # If video client was already created at connect time, reuse it
            if not self.video_client:
                self.video_client = VideoClient(host=self.server_host, username=self.username)
            if self.video_client.start_video(self.video_display_frame):
                self.start_video_btn.config(state='disabled')
                self.stop_video_btn.config(state='normal')

    def stop_video(self):
        if self.video_client:
            self.video_client.stop_video()  # Only stop sending local video
        self.start_video_btn.config(state='normal')
        self.stop_video_btn.config(state='disabled')
        # Do NOT destroy the video grid or VideoClient; keep receiving others' video

    def start_audio(self):
        if self.username:
            if not self.audio_client:
                self.audio_client = AudioClient(host=self.server_host, username=self.username)
            if self.audio_client.start_audio():
                self.start_audio_btn.config(state='disabled')
                self.stop_audio_btn.config(state='normal')
                self.audio_status.config(text="Audio conferencing active - speaking...")

    def stop_audio(self):
        if self.audio_client:
            self.audio_client.stop_audio()
            # Don't set audio_client to None - keep it alive for receiving
            # Just turn off mike
        self.start_audio_btn.config(state='normal')
        self.stop_audio_btn.config(state='disabled')
        self.audio_status.config(text="Audio conferencing active - listening only")

    def toggle_screen_share(self):
        # Toggle presenting state on the existing screen client
        if self.screen_client:
            # If not currently presenting, start
            if not self.screen_client.is_presenting:
                self.screen_client.toggle_present()
                self.start_screen_btn.config(text="Stop Presenting")
                self.screen_status.config(text="Screen sharing active - presenting...")
            else:
                # Stop presenting
                self.screen_client.toggle_present()
                self.start_screen_btn.config(text="Start Presenting")
                self.screen_status.config(text="Screen sharing ready")
                # Clear the display
                self.remote_screen_label.config(image='')

    def on_closing(self):
        if self.refresh_timer:
            self.root.after_cancel(self.refresh_timer)
        if self.video_client:
            self.video_client.shutdown()
        if self.audio_client:
            self.audio_client.shutdown()  # This will stop all audio threads
        if self.screen_client and self.screen_client.is_presenting:
            self.screen_client.toggle_present()  # This will stop screen sharing
        if self.client:
            self.client.close()
        self.root.destroy()

if __name__ == "__main__":
    client = MainClient()
    client.connect()