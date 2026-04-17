import socket
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Dict, Any


class P2PNetworkSkill:
    """
    Навык для проверки доступности узлов P2P‑сети Argos.

    Использует стандартные библиотеки + requests + bs4.
    """

    def __init__(self, nodes: List[Tuple[str, int]] = None):
        """
        Инициализация навыка.

        :param nodes: Список кортежей (IP, порт) узлов сети.
                      Если не указан, используется пример из задания.
        """
        if nodes is None:
            self.nodes = [
                ("192.168.1.10", 5000),
                ("192.168.1.11", 5000),
                ("192.168.1.12", 5000),
            ]
        else:
            self.nodes = nodes
        self.results: Dict[Tuple[str, int], Dict[str, Any]] = {}

    def _get_local_ip(self) -> str:
        """
        Определяет внешний IP-адрес текущего хоста.
        """
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            return local_ip
        except Exception:
            return "0.0.0.0"

    def _check_node(self, ip: str, port: int) -> Dict[str, Any]:
        """
        Проверяет один узел сети.

        Делает GET‑запрос к http://{ip}:{port}/status.
        Ожидает HTML‑страницу, из которой извлекает статус через bs4.
        """
        url = f"http://{ip}:{port}/status"
        try:
            resp = requests.get(url, timeout=3)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            status_tag = soup.find("div", {"id": "status"})
            status = status_tag.get_text(strip=True) if status_tag else "UNKNOWN"
            return {"online": True, "status": status, "code": resp.status_code}
        except requests.RequestException as e:
            return {"online": False, "error": str(e), "code": None}

    def scan(self) -> None:
        """
        Сканирует все узлы, заполняет self.results.
        """
        self.results.clear()
        for ip, port in self.nodes:
            self.results[(ip, port)] = self._check_node(ip, port)

    def report(self) -> str:
        """
        Формирует человекочитаемый отчёт о состоянии сети.
        """
        lines = [
            f"Локальный IP: {self._get_local_ip()}",
            "Результаты сканирования узлов:",
        ]
        for (ip, port), info in self.results.items():
            if info.get("online"):
                lines.append(f"  • {ip}:{port} → ONLINE (status: {info.get('status')})")
            else:
                err = info.get("error", "неизвестная ошибка")
                lines.append(f"  • {ip}:{port} → OFFLINE ({err})")
        return "\n".join(lines)

    def get_node_status(self, ip: str, port: int) -> Dict[str, Any]:
        """
        Возвращает сохранённый результат проверки конкретного узла.
        При отсутствии результата выполняет проверку «на лету».
        """
        key = (ip, port)
        if key not in self.results:
            self.results[key] = self._check_node(ip, port)
        return self.results[key]