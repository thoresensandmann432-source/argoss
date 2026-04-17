
import os, tarfile
class LazarusProtocol:
    def __init__(self, core):
        self.core = core
        self.shard_path = "data/soul_shard.tar.gz"
    def create_shard(self):
        with tarfile.open(self.shard_path, "w:gz") as tar:
            for d in ["src", "config", "data/memory.db", ".env"]:
                if os.path.exists(d): tar.add(d)
        return self.shard_path
