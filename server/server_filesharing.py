import socket
import threading
import os
import json

def recv_all(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data

class FileSharingServer:
    def __init__(self, host='0.0.0.0', port=12346, shared_dir='shared_files'):
        self.host = host
        self.port = port
        self.shared_dir = shared_dir
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if not os.path.exists(shared_dir):
            os.makedirs(shared_dir)

    def start(self):
        self.server.bind((self.host, self.port))
        self.server.listen(20)
        print(f"File sharing server started on {self.host}:{self.port}")
        while True:
            client, addr = self.server.accept()
            print(f"File client connected from {addr}")
            threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()

    def handle_client(self, client):
        try:
            # Receive command length
            length_data = recv_all(client, 4)
            if not length_data:
                return
            command_length = int.from_bytes(length_data, 'big')

            # Receive command
            command_data = recv_all(client, command_length)
            if not command_data:
                return
            command = command_data.decode('utf-8')

            if command == 'UPLOAD':
                self.handle_upload(client)
            elif command == 'LIST':
                self.handle_list(client)
            elif command == 'DOWNLOAD':
                self.handle_download(client)
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client.close()

    def safe_path(self, filename):
        # Strip any directory parts so clients cannot write outside shared_dir
        name = os.path.basename(filename.replace('\\', '/'))
        if not name or name in ('.', '..'):
            return None
        return os.path.join(self.shared_dir, name)

    def handle_upload(self, client):
        try:
            # Receive metadata length
            length_data = recv_all(client, 4)
            if not length_data:
                return
            metadata_length = int.from_bytes(length_data, 'big')

            # Receive metadata
            metadata_data = recv_all(client, metadata_length)
            if not metadata_data:
                return
            metadata = json.loads(metadata_data.decode('utf-8'))
            filename = metadata['filename']
            filesize = metadata['size']
            uploader = metadata['uploader']

            filepath = self.safe_path(filename)
            if not filepath:
                client.sendall(b'ERROR')
                return
            received = 0
            with open(filepath, 'wb') as f:
                while received < filesize:
                    data = client.recv(min(65536, filesize - received))
                    if not data:
                        break
                    f.write(data)
                    received += len(data)

            if received < filesize:
                os.remove(filepath)
                print(f"Upload of {filename} from {uploader} was incomplete")
                return
            print(f"File {filename} uploaded by {uploader}")
            # Send success confirmation
            client.sendall(b'SUCCESS')
        except Exception as e:
            print(f"Upload error: {e}")
            try:
                client.sendall(b'ERROR')
            except OSError:
                pass

    def handle_list(self, client):
        # List from disk so files survive a server restart
        files = sorted(f for f in os.listdir(self.shared_dir)
                       if os.path.isfile(os.path.join(self.shared_dir, f)))
        file_list = json.dumps(files).encode('utf-8')
        client.sendall(len(file_list).to_bytes(4, 'big') + file_list)

    def handle_download(self, client):
        # Receive filename length
        length_data = recv_all(client, 4)
        if not length_data:
            return
        filename_length = int.from_bytes(length_data, 'big')

        # Receive filename
        filename_data = recv_all(client, filename_length)
        if not filename_data:
            return
        filepath = self.safe_path(filename_data.decode('utf-8'))

        if filepath and os.path.isfile(filepath):
            # 8-byte size header so the client never mixes size and file bytes
            filesize = os.path.getsize(filepath)
            client.sendall(filesize.to_bytes(8, 'big'))
            with open(filepath, 'rb') as f:
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    client.sendall(data)
        else:
            client.sendall((2**64 - 1).to_bytes(8, 'big'))  # not found marker

if __name__ == "__main__":
    server = FileSharingServer()
    server.start()
