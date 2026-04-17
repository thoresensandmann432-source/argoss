import json


class P2PProtocol:
    def __init__(self, core):
        self.core = core

    def create_packet(self, type, data):
        packet = {
            "node_id": self.core.node_id,
            "type": type,  # 'HANDSHAKE', 'TASK', 'MEMORY_SYNC', 'LAZARUS_SHARD'
            "weight": self.core.p2p.auth.calculate_my_weight(),
            "payload": data,
        }
        return json.dumps(packet)

    def process_packet(self, raw_json, sender_ip):
        data = json.loads(raw_json)
        p_type = data.get("type")

        if p_type == "MEMORY_SYNC":
            self.core.memory.fast_store(data["payload"])
            return {"status": "synced"}

        if p_type == "TASK":
            # Выполнение задачи на свободном GPU
            return self.core.awa.delegate_task("REMOTE_TASK", data["payload"])

        return {"status": "ok", "role": self.core.p2p.my_role}
