import socket
import threading

class ChatServer:
    def __init__(self, host='0.0.0.0', port=12345):
        self.host = host
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = []
        self.usernames = []
        self.lock = threading.Lock()

    def start(self):
        self.server.bind((self.host, self.port))
        self.server.listen(20)
        print(f"Chat server started on {self.host}:{self.port}")
        while True:
            client, addr = self.server.accept()
            print(f"Connection from {addr}")
            threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()

    def handle_client(self, client):
        username = None
        try:
            while True:
                username = client.recv(1024).decode('utf-8').strip()
                if not username:
                    client.close()
                    return
                with self.lock:
                    taken = username in self.usernames
                    if not taken:
                        self.clients.append(client)
                        self.usernames.append(username)
                if taken:
                    client.send('USERNAME_TAKEN'.encode('utf-8'))
                else:
                    client.send('USERNAME_OK'.encode('utf-8'))
                    self.broadcast(f"{username} joined the chat")
                    self.broadcast_userlist()
                    break
            # Messages are newline-delimited because TCP may merge or split sends
            buffer = ''
            while True:
                data = client.recv(4096)
                if not data:
                    break
                buffer += data.decode('utf-8', errors='replace')
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if message:
                        self.broadcast(f"{username}: {message}")
        except (OSError, UnicodeDecodeError):
            pass
        finally:
            with self.lock:
                left = client in self.clients
                if left:
                    index = self.clients.index(client)
                    self.clients.pop(index)
                    username = self.usernames.pop(index)
            if left:
                self.broadcast(f"{username} left the chat")
                self.broadcast_userlist()
            client.close()

    def broadcast_userlist(self):
        with self.lock:
            users = ','.join(self.usernames)
        self.broadcast(f"USERLIST:{users}")

    def broadcast(self, message):
        data = (message + '\n').encode('utf-8')
        with self.lock:
            clients = list(self.clients)
        for client in clients:
            try:
                client.sendall(data)
            except OSError:
                pass  # handle_client cleans up when its recv fails

if __name__ == "__main__":
    server = ChatServer()
    server.start()
