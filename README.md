# IntraMeet

IntraMeet is a collaboration suite for a local network (LAN). It provides **group chat, video conferencing, audio conferencing, screen sharing and file sharing** without needing the internet. Everything runs over your Wi-Fi router or a **mobile/laptop hotspot, even one with no internet connection**.

Built with Python sockets (TCP + UDP) and a Tkinter GUI.

## Features

| Feature | Transport | Port(s) | Notes |
|---|---|---|---|
| Chat | TCP | 12345 | Group chat with an online-users list |
| File sharing | TCP | 12346 | Upload, list and download files stored on the server |
| Video | UDP | 12347 | Webcam frames (JPEG) relayed by the server, shown in a grid |
| Audio | UDP | 12348 | Server-side mixing that excludes your own voice (no echo), with jitter buffers |
| Screen share | TCP | 12349 / 12350 | One presenter, many viewers |
| Server discovery | UDP broadcast | 12351 | Clients find the server automatically |

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Running

1. **On the server PC**, start the server:
   ```powershell
   cd server
   python server.py
   ```
   It prints the IP addresses clients can use, for example `192.168.137.1`.

2. **First time only, on the server PC:** right-click `allow_firewall.bat` and choose **Run as administrator**.
   Windows treats a hotspot with no internet as a *Public* network and blocks incoming connections. This script opens IntraMeet's ports on all network profiles.

3. **On every client PC** (including the server PC if you want to take part):
   ```powershell
   cd client
   python client.py
   ```
   The client searches the network for the server and fills in its IP. Confirm it or type it yourself, then pick a username.
   You can also pass the IP directly: `python client.py 192.168.137.1`.

## Using a hotspot without internet

- Any device can host the hotspot: a phone, or a laptop using Windows *Mobile hotspot*. The server can run on the laptop hosting the hotspot (its IP is usually `192.168.137.1`) or on any connected laptop.
- All devices must be connected to the **same** hotspot.
- IntraMeet doesn't use DNS or any internet service. Discovery uses LAN broadcast, and you can always type the IP by hand.
- Some phone hotspots enable *client isolation* (AP isolation), which stops connected devices from talking to each other. If clients can't reach the server, turn that off or host the hotspot from a laptop.

## Project structure

```
server/   server.py launches every service; one module per feature
client/   client.py is the GUI; one module per feature; discovery.py finds the server
```
