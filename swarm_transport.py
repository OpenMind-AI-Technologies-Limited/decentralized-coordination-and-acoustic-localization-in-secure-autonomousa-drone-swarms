"""Peer-addressed UDP delivery for authenticated swarm envelopes.

UDP source addresses are not trusted; MeshNode validates Ed25519 identity.
"""
from __future__ import annotations

import socket
import threading
from typing import Mapping, Optional


class UdpPeerTransport:
    MAX_PACKET_BYTES = 60000

    def __init__(self, node_id: int, bind: tuple[str, int],
                 peers: Optional[Mapping[int, tuple[str, int]]] = None):
        self.node_id = int(node_id)
        self._peers = {int(k): (str(v[0]), int(v[1])) for k, v in (peers or {}).items()}
        self._lock = threading.RLock()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Windows reports ICMP Port Unreachable as WSAECONNRESET on UDP recv().
        # A crashed peer must not disable message reception from healthy peers.
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            self._socket.ioctl(socket.SIO_UDP_CONNRESET, False)
        self._socket.bind(bind)
        self.address = self._socket.getsockname()
        self._closed = False

    def configure_peers(self, peers: Mapping[int, tuple[str, int]]) -> None:
        with self._lock:
            self._peers = {int(k): (str(v[0]), int(v[1])) for k, v in peers.items()}

    def send(self, packet: bytes, recipient: Optional[int] = None) -> None:
        if not isinstance(packet, bytes) or not 0 < len(packet) <= self.MAX_PACKET_BYTES:
            raise ValueError("Invalid UDP packet size")
        with self._lock:
            if self._closed:
                raise RuntimeError("Transport is closed")
            if recipient is not None and recipient not in self._peers:
                raise ValueError("Unregistered peer")
            destinations = [self._peers[recipient]] if recipient is not None else [
                address for peer, address in self._peers.items() if peer != self.node_id
            ]
            for address in destinations:
                self._socket.sendto(packet, address)

    def receive(self, timeout: float = 0.05) -> Optional[bytes]:
        with self._lock:
            if self._closed:
                return None
            sock = self._socket
        sock.settimeout(timeout)
        try:
            packet, _ = sock.recvfrom(65535)
            if not 0 < len(packet) <= self.MAX_PACKET_BYTES:
                return None
            return packet
        except (socket.timeout, BlockingIOError, ConnectionResetError):
            return None
        except OSError:
            if self._closed:
                return None
            raise

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._socket.close()
