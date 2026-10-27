import socket
import sys
import time

DISCOVERY_PORT = 12351
DISCOVERY_REQUEST = b"INTRAMEET_DISCOVER"
DISCOVERY_REPLY = b"INTRAMEET_SERVER"


def disable_udp_connreset(sock):
    """Stop Windows from raising WinError 10054 on recvfrom() after an ICMP port-unreachable."""
    if sys.platform == 'win32' and hasattr(socket, 'SIO_UDP_CONNRESET'):
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass


def local_ipv4_addresses():
    """IPv4 addresses of this machine, found without needing internet access."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    for probe in ('10.255.255.255', '192.168.255.255', '172.31.255.255'):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 1))  # UDP connect sends nothing
            ips.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    return sorted(ip for ip in ips if not ip.startswith('127.') and ip != '0.0.0.0')


def discover_server(timeout=2.0):
    """Broadcast on every local network and return the first server IP that answers,
    or None. Windows only sends 255.255.255.255 out of one adapter, so we also send a
    subnet broadcast from each interface (works on hotspots with no internet)."""
    socks = []
    for ip in local_ipv4_addresses() + ['0.0.0.0']:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            disable_udp_connreset(s)
            s.bind((ip, 0))
            s.setblocking(False)
            targets = ['255.255.255.255']
            if ip != '0.0.0.0':
                targets.append(ip.rsplit('.', 1)[0] + '.255')  # assume /24, the hotspot/home-router norm
            for target in targets:
                try:
                    s.sendto(DISCOVERY_REQUEST, (target, DISCOVERY_PORT))
                except OSError:
                    pass
            socks.append(s)
        except OSError:
            pass

    found = None
    deadline = time.time() + timeout
    while found is None and time.time() < deadline:
        for s in socks:
            try:
                data, addr = s.recvfrom(1024)
                if data.strip() == DISCOVERY_REPLY:
                    found = addr[0]
                    break
            except (BlockingIOError, OSError):
                pass
        time.sleep(0.02)
    for s in socks:
        s.close()
    return found
