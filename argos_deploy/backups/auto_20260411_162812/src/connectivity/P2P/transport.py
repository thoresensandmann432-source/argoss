"""
src/connectivity/P2P/transport.py — P2P транспорт (TCP/UDP)
"""
import socket
import threading
from src.argos_logger import get_logger

log = get_logger("argos.p2p.transport")


class P2PTransport:
    def __init__(self, manager):
        self.manager = manager
        self.port = 5001

    def send_tcp(self, ip: str, data: bytes) -> bool:
        try:
            with socket.create_connection((ip, self.port), timeout=5) as sock:
                sock.sendall(data)
            return True
        except Exception as e:
            log.warning(f"TCP send error {ip}: {e}")
            return False

    def start_listener(self, callback):
        def _listen():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("", self.port))
                srv.listen(10)
                while True:
                    try:
                        conn, addr = srv.accept()
                        with conn:
                            data = conn.recv(65536)
                            if data and callback:
                                callback(addr[0], data)
                    except Exception:
                        pass
        t = threading.Thread(target=_listen, daemon=True)
        t.start()
        return t
