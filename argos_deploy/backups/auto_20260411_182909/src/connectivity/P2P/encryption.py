import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class P2PEncryptor:
    def __init__(self):
        # Берем секрет из .env, дополняем до 32 байт для AES-256
        secret = os.getenv("ARGOS_NETWORK_SECRET", "default_secret_key_32_chars_long!!")
        self.key = secret.encode().ljust(32)[:32]
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, data: str) -> bytes:
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, data.encode(), None)
        return nonce + ciphertext

    def decrypt(self, encrypted_data: bytes) -> str:
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        return self.aesgcm.decrypt(nonce, ciphertext, None).decode()
