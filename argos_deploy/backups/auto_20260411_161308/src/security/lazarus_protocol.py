"""
LazarusProtocol - Цифровое Бессмертие v2.5
Создает "Осколки Души" и рассылает их по контурам
"""
import os
import tarfile
import json
import shutil
from datetime import datetime

class LazarusProtocol:
    def __init__(self, core):
        self.core = core
        self.shard_path = "data/soul_shard.tar.gz"
        self.backup_dirs = ["src", "config", "data/memory.db", ".env"]

    def create_shard(self):
        """Создает осколок души"""
        with tarfile.open(self.shard_path, "w:gz") as tar:
            for d in self.backup_dirs:
                if os.path.exists(d):
                    tar.add(d)
        print(f"🧬 [LAZARUS] Осколок создан: {self.shard_path}")
        return self.shard_path

    def restore_from_shard(self, shard_path=None):
        """Восстанавливает из осколка"""
        path = shard_path or self.shard_path
        if not os.path.exists(path):
            print("❌ [LAZARUS] Осколок не найден")
            return False
        
        with tarfile.open(path, "r:gz") as tar:
            tar.extractall(".")
        print(f"🔄 [LAZARUS] Восстановление завершено из: {path}")
        return True

    def replicate_to_cloud(self, destinations):
        """Реплицирует осколок в облачные хранилища"""
        shard = self.create_shard()
        for dest in destinations:
            try:
                shutil.copy(shard, dest)
                print(f"☁️ [LAZARUS] Репликация в: {dest}")
            except Exception as e:
                print(f"⚠️ [LAZARUS] Ошибка репликации в {dest}: {e}")
