import socket
import sys

DISCOVERY_PORT = 12351
DISCOVERY_REQUEST = b"INTRAMEET_DISCOVER"
DISCOVERY_REPLY = b"INTRAMEET_SERVER"


def disable_udp_connreset(sock):
    """On Windows, an ICMP 'port unreachable' (e.g. a client closed) makes the next
    recvfrom() on a UDP socket raise WinError 10054. Turn that behaviour off."""
    if sys.platform == 'win32' and hasattr(socket, 'SIO_UDP_CONNRESET'):
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass


def local_ipv4_addresses():
    """All IPv4 addresses of this machine. Works without internet access
    (no outbound connection to a public host is needed)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    # Fallback: ask the routing table which interface would reach a private address.
    # UDP connect() sends no packets.
    for probe in ('10.255.255.255', '192.168.255.255', '172.31.255.255'):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 1))
            ips.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    ips.discard('0.0.0.0')
    return sorted(ips, key=lambda ip: ip.startswith('127.'))
