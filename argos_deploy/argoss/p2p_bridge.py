"""src/connectivity/p2p_bridge.py — P2P сеть ARGOS"""
from __future__ import annotations
import json, math, socket, time, threading, uuid
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "NodeProfile","NodeRegistry","TaskDistributor","ArgosBridge","BROADCAST_PORT"
]
BROADCAST_PORT = 47777


class NodeProfile:
    def __init__(self) -> None:
        self.node_id  = str(uuid.uuid4())
        self.hostname = socket.gethostname()
        self._born    = time.time()

    def get_power(self) -> dict:
        cpu_free = ram_free = 50.0
        cores = 2; ram_gb = 2.0
        try:
            import psutil
            cpu_free = 100 - psutil.cpu_percent(interval=0.1)
            m = psutil.virtual_memory()
            ram_free = 100 - m.percent
            cores  = psutil.cpu_count(logical=False) or 2
            ram_gb = m.total / 1024**3
        except Exception:
            pass
        index = min(100, (cpu_free * 0.5 + ram_free * 0.5))
        return {"index": round(index, 1), "cpu_free": cpu_free, "ram_free": ram_free,
                "cpu_cores": cores, "ram_gb": round(ram_gb, 1)}

    def get_age_days(self) -> float:
        return max(0.0, (time.time() - self._born) / 86400)

    def get_authority(self) -> int:
        return int(self.get_power()["index"] * math.log(self.get_age_days() + 2))

    def to_dict(self) -> dict:
        pwr = self.get_power()
        return {"node_id": self.node_id, "hostname": self.hostname,
                "power": pwr, "authority": self.get_authority(),
                "age_days": self.get_age_days(), "last_seen": time.time()}


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._lock  = threading.Lock()

    def update(self, node_dict: dict, ip: str) -> None:
        nid = node_dict.get("node_id")
        if not nid: return
        with self._lock:
            node_dict["ip"] = ip
            node_dict["last_seen"] = time.time()
            self._nodes[nid] = node_dict

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._nodes.values())

    def count(self) -> int:
        with self._lock:
            return len(self._nodes)

    def get_master(self) -> Optional[dict]:
        nodes = self.all()
        if not nodes: return None
        return max(nodes, key=lambda n: n.get("authority", 0))


class TaskDistributor:
    def __init__(self, registry: NodeRegistry, self_profile: NodeProfile) -> None:
        self._registry = registry
        self._self     = self_profile

    def pick_node_for(self, task_type: str) -> Optional[dict]:
        nodes = self._registry.all()
        if not nodes:
            return {"node": self._self.to_dict(), "is_local": True}
        best = max(nodes, key=lambda n: n.get("authority", 0))
        return {"node": best, "is_local": best["node_id"] == self._self.node_id}

    def route_task(self, task: str) -> str:
        pick = self.pick_node_for("ai")
        if pick and not pick.get("is_local"):
            return f"🌐 Задача отправлена на ноду {pick['node']['hostname']}"
        return f"💻 Задача выполняется локально"


class ArgosBridge:
    def __init__(self, core=None) -> None:
        self._core     = core
        self._registry = NodeRegistry()
        self._profile  = NodeProfile()
        self._running  = False
        self.udp_host  = ""
        self.udp_port  = BROADCAST_PORT

    def start(self) -> str:
        self._running = True
        t = threading.Thread(target=self._udp_discovery, daemon=True)
        t.start()
        return f"🌐 P2P запущен: {self._profile.node_id[:8]}"

    def stop(self) -> None:
        self._running = False

    def network_status(self) -> str:
        nodes = self._registry.count()
        master = self._registry.get_master()
        master_name = master.get("hostname","?") if master else "нет"
        return (f"🌐 P2P сеть\n  Нод: {nodes}\n  Мастер: {master_name}\n"
                f"  Авторитет: {self._profile.get_authority()}")

    def sync_skills_from_network(self) -> str:
        return "🔄 Синхронизация навыков... (0 новых)"

    def route_query(self, query: str) -> str:
        dist = TaskDistributor(self._registry, self._profile)
        return dist.route_task(query)

    def _udp_discovery(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try: sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError: pass
            sock.bind((self.udp_host, self.udp_port))
            sock.settimeout(1.0)
            while self._running:
                try:
                    data, addr = sock.recvfrom(4096)
                    node = json.loads(data.decode())
                    self._registry.update(node, addr[0])
                except Exception:
                    pass
        except Exception:
            pass
