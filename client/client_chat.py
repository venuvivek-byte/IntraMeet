import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, simpledialog

class ChatClient:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = None

        # GUI setup
        self.root = tk.Tk()
        self.root.title("LAN Chat")
        self.root.geometry("500x400")

        self.chat_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, state='disabled')
        self.chat_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.message_entry = tk.Entry(self.root)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=10)
        self.message_entry.bind("<Return>", self.send_message)

        self.send_button = tk.Button(self.root, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT, padx=10, pady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def connect(self):
        try:
            self.client.connect((self.host, self.port))
            self.username = simpledialog.askstring("Username", "Enter your username:")
            if self.username:
                self.client.send(self.username.encode('utf-8'))
                threading.Thread(target=self.receive_messages).start()
                self.root.mainloop()
            else:
                self.client.close()
        except Exception as e:
            print(f"Connection failed: {e}")

    def send_message(self, event=None):
        message = self.message_entry.get()
        if message:
            self.client.sendall((message + '\n').encode('utf-8'))
            self.message_entry.delete(0, tk.END)

    def receive_messages(self):
        while True:
            try:
                message = self.client.recv(4096).decode('utf-8').strip()
                if message:
                    self.chat_area.config(state='normal')
                    self.chat_area.insert(tk.END, message + '\n')
                    self.chat_area.config(state='disabled')
                    self.chat_area.yview(tk.END)
            except:
                break

    def on_closing(self):
        self.client.close()
        self.root.destroy()

if __name__ == "__main__":
    import sys
    client = ChatClient(host=sys.argv[1] if len(sys.argv) > 1 else 'localhost')
    client.connect()