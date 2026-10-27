import socket
import os
import json
from tkinter import filedialog, messagebox

NOT_FOUND = 2**64 - 1
CONNECT_TIMEOUT = 5.0
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')

def recv_all(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data

class FileSharingClient:
    def __init__(self, host='localhost', port=12346, shared_dir=DEFAULT_DOWNLOAD_DIR):
        self.host = host
        self.port = port
        self.shared_dir = shared_dir
        if not os.path.exists(shared_dir):
            os.makedirs(shared_dir)

    def _connect(self, command):
        client = socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT)
        client.settimeout(30.0)
        command_bytes = command.encode('utf-8')
        client.sendall(len(command_bytes).to_bytes(4, 'big') + command_bytes)
        return client

    def upload_file(self, username):
        filepath = filedialog.askopenfilename()
        if filepath:
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)

            try:
                client = self._connect('UPLOAD')
                metadata = {'filename': filename, 'size': filesize, 'uploader': username}
                metadata_bytes = json.dumps(metadata).encode('utf-8')
                # Send metadata length first, then metadata
                client.sendall(len(metadata_bytes).to_bytes(4, 'big') + metadata_bytes)

                with open(filepath, 'rb') as f:
                    while True:
                        data = f.read(65536)
                        if not data:
                            break
                        client.sendall(data)

                # Wait for server confirmation
                response = client.recv(1024).decode('utf-8')
                client.close()

                if response == 'SUCCESS':
                    messagebox.showinfo("Success", f"File {filename} uploaded successfully")
                    return True
                else:
                    messagebox.showerror("Upload Failed", f"Server rejected upload of {filename}")
                    return False
            except Exception as e:
                messagebox.showerror("Upload Failed", f"Failed to upload {filename}: {str(e)}")
                return False
        return False

    def list_files(self):
        try:
            client = self._connect('LIST')
            length_data = recv_all(client, 4)
            payload = recv_all(client, int.from_bytes(length_data, 'big')) if length_data else None
            client.close()
            return json.loads(payload.decode('utf-8')) if payload else []
        except Exception as e:
            print(f"Error listing files: {e}")
            return []

    def download_file(self, filename, progress_callback=None):
        try:
            client = self._connect('DOWNLOAD')
            filename_bytes = filename.encode('utf-8')
            client.sendall(len(filename_bytes).to_bytes(4, 'big') + filename_bytes)

            size_data = recv_all(client, 8)
            if not size_data or int.from_bytes(size_data, 'big') == NOT_FOUND:
                client.close()
                messagebox.showerror("Error", "File not found")
                return False

            filesize = int.from_bytes(size_data, 'big')
            filepath = os.path.join(self.shared_dir, os.path.basename(filename))
            received = 0

            with open(filepath, 'wb') as f:
                while received < filesize:
                    data = client.recv(min(65536, filesize - received))
                    if not data:
                        break
                    f.write(data)
                    received += len(data)
                    if progress_callback:
                        progress_callback(received / filesize * 100)
            client.close()
            if received < filesize:
                messagebox.showerror("Download Failed", f"Connection lost while downloading {filename}")
                return False
            messagebox.showinfo("Success", f"File {filename} downloaded to\n{filepath}")
            return True
        except Exception as e:
            messagebox.showerror("Download Failed", f"Failed to download {filename}: {e}")
            return False
