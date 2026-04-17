
from .transport import P2PTransport
from .encryption import P2PEncryptor
from .protocol import P2PProtocol
from .authority import AuthorityManager


class P2PManager:
    def init(self, core):
        self.core = core
        self.encryptor = P2PEncryptor()
        self.auth = AuthorityManager(core)
        self.protocol = P2PProtocol(core)
        self.transport = P2PTransport(self)
        self.peers = {}  # {ip: info}

    def start(self):
        self.transport.start_udp_beacon()
        # Запуск прослушивания TCP в отдельном потоке...
        print(
            f"🌐 [P2P] Глобальный мост активирован. Роль: {self.auth.get_role(self.auth.calculate_my_weight())}"
        )

    def sync_swarm(self, data_type, payload):
        """Рассылка данных по всем нодам (включая Shodan-узлы)"""
        packet = self.protocol.create_packet(data_type, payload)
        encrypted = self.encryptor.encrypt(packet)

        for ip in self.peers:
            self.transport.send_tcp(ip, encrypted)

    def connect_to_internet_node(self, ip):
        """Ручное или автоматическое (Shodan) подключение к удаленному узлу"""
        res = self.transport.send_tcp(ip, self.encryptor.encrypt("HANDSHAKE"))
        if res:
            self.peers[ip] = {"status": "active", "type": "remote"}
            print(f"🌍 [P2P] Установлена связь с интернет-узлом: {ip}")
