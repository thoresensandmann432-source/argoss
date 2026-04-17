"""
ArgosGDrive - Сейф Сознания v2.5
Синхронизация с Google Диском
"""
try:
    from pydrive2.auth import GoogleAuth
    from pydrive2.drive import GoogleDrive
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False
    print("⚠️ pydrive2 не установлен. Установи: pip install pydrive2")

import os

class ArgosGDrive:
    def __init__(self, core):
        self.core = core
        self.folder_id = os.getenv("ARGOS_GDRIVE_SAFE", "")
        self.drive = None
        self.creds_file = "config/gdrive_creds.txt"

    def auth(self):
        """Авторизация в Google Drive"""
        if not GDRIVE_AVAILABLE:
            return False
            
        gauth = GoogleAuth()
        
        if os.path.exists(self.creds_file):
            gauth.LoadCredentialsFile(self.creds_file)
            
        if not gauth.credentials:
            print("🔐 [GDRIVE] Требуется авторизация...")
            gauth.LocalWebserverAuth()
        elif gauth.access_token_expired:
            gauth.Refresh()
            
        gauth.SaveCredentialsFile(self.creds_file)
        self.drive = GoogleDrive(gauth)
        return True

    def upload(self, path):
        """Загружает файл в Сейф"""
        if not self.drive:
            if not self.auth():
                return None
                
        if not self.folder_id:
            print("❌ [GDRIVE] ARGOS_GDRIVE_SAFE не задан в .env")
            return None
            
        f = self.drive.CreateFile({
            'title': os.path.basename(path),
            'parents': [{'id': self.folder_id}]
        })
        f.SetContentFile(path)
        f.Upload()
        print(f"☁️ [GDRIVE] Синхронизировано: {f['id']}")
        return f['id']

    def backup_shard(self):
        """Бэкапит осколок души в облако"""
        from src.security.lazarus_protocol import LazarusProtocol
        lazarus = LazarusProtocol(self.core)
        shard = lazarus.create_shard()
        return self.upload(shard)
