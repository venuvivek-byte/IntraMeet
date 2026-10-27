# Main server file to integrate all modules
import os
import threading
import time
from server_chat import ChatServer
from server_filesharing import FileSharingServer
from server_video import VideoServer
from server_audio import AudioServer
from server_screenshare import ScreenShareServer
from server_discovery import DiscoveryServer
from netutils import local_ipv4_addresses

def start_chat_server():
    chat_server = ChatServer()
    chat_server.start()

def start_file_server():
    file_server = FileSharingServer()
    file_server.start()

def start_video_server():
    video_server = VideoServer()
    video_server.start()

def start_audio_server():
    audio_server = AudioServer()
    audio_server.start()

def start_screenshare_server():
    screen_server = ScreenShareServer()
    screen_server.start()

def start_discovery_server():
    discovery_server = DiscoveryServer()
    discovery_server.start()

if __name__ == "__main__":
    # Keep shared_files next to this script regardless of the working directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Start servers in threads
    threading.Thread(target=start_chat_server, daemon=True).start()
    threading.Thread(target=start_file_server, daemon=True).start()
    threading.Thread(target=start_video_server, daemon=True).start()
    threading.Thread(target=start_audio_server, daemon=True).start()
    threading.Thread(target=start_screenshare_server, daemon=True).start()
    threading.Thread(target=start_discovery_server, daemon=True).start()

    time.sleep(0.5)
    print("\nIntraMeet server started. Chat, File Sharing, Video, Audio, and Screen Share servers are running.")
    print("Clients on the same Wi-Fi / hotspot can connect to any of these addresses:")
    for ip in local_ipv4_addresses():
        print(f"    {ip}")
    print("(Clients also find the server automatically via LAN broadcast.)\n")
    # Keep main thread alive without burning CPU
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Server shutting down...")
