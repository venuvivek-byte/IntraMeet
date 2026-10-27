Screen Share Module

Overview
- Presenter: one client at a time can present their screen. The presenter captures the screen, compresses frames to JPEG, and streams them to the server over TCP (presenter port 12349).
- Viewers: all other clients connect to the server's viewer port (12350) and receive the presenter's JPEG frames, displayed in a Tkinter window.

Files added
- `server/server_screenshare.py`: TCP server accepting a single presenter and multiple viewers; relays frames from presenter to viewers.
- `client/client_screenshare.py`: Tkinter client that can act as presenter or viewer. Presenter captures screen with `mss` and sends JPEG frames; viewer receives frames and displays them.
- `requirements.txt`: mss and Pillow.

Usage
1. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

2. Start the server screenshare service (server folder):

```powershell
python server_screenshare.py
```

3. Start a client (client folder):

```powershell
python client_screenshare.py
```

- Use the "Start Presenting" / "Stop Presenting" button to become the presenter (only one presenter allowed).
- Other clients will automatically connect as viewers and show the presenter's frames.

Notes and next steps
- Current implementation captures the entire screen. Adding window selection is possible by enumerating windows and using window bounding boxes.
- Bandwidth and latency adjustments: tune `CAPTURE_INTERVAL`, `JPEG_QUALITY`, and optionally resize rules in `client_screenshare.py`.
- Authentication/authorization is not included.
- This uses TCP to preserve frame integrity; if you need low-latency lossy transport consider UDP with loss-tolerant framing.
