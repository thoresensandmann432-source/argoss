"""
src/skills/crypto_utils.py — Утилиты шифрования и криптографии для Аргоса.

Использует stdlib (hashlib, hmac, secrets, base64) + cryptography (pip install cryptography).
Опционально: cryptronics (pip install cryptronics).

Команды:
  зашифруй <текст> ключ <ключ>   — AES-256 шифрование
  расшифруй <текст> ключ <ключ>  — AES-256 расшифрование
  хэш <текст>                    — SHA-256 хэш строки
  генерируй ключ [длина]         — генерация безопасного случайного ключа
  генерируй пароль [длина]       — безопасный пароль
  base64 кодируй <текст>         — Base64 кодирование
  base64 раскодируй <текст>      — Base64 декодирование
  hmac <ключ> <данные>           — HMAC-SHA256 подпись
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Шифрование, хэши, HMAC, Base64 (stdlib + cryptography)"

import base64
import hashlib
import hmac
import os
import secrets
import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core import ArgosCore

SKILL_NAME = "crypto_utils"
SKILL_TRIGGERS = ["зашифруй", "расшифруй", "хэш sha", "генерируй ключ", "генерируй пароль",
                  "base64 кодируй", "base64 раскодируй", "hmac подпись"]


class CryptoUtils:
    """Утилиты шифрования для Аргоса."""

    def __init__(self, core: "ArgosCore | None" = None):
        self.core = core

    def handle_command(self, text: str) -> str | None:
        t = text.lower().strip()

        if "зашифруй " in t:
            return self._parse_encrypt(text)
        if "расшифруй " in t:
            return self._parse_decrypt(text)
        if "хэш " in t or "sha256" in t or "sha512" in t:
            return self._parse_hash(text)
        if "генерируй ключ" in t:
            return self._gen_key(text)
        if "генерируй пароль" in t:
            return self._gen_password(text)
        if "base64 кодируй " in t:
            payload = text.split("base64 кодируй ", 1)[-1].strip()
            return self.b64_encode(payload)
        if "base64 раскодируй " in t:
            payload = text.split("base64 раскодируй ", 1)[-1].strip()
            return self.b64_decode(payload)
        if "hmac " in t:
            return self._parse_hmac(text)
        return None

    # ─── Шифрование AES-256-GCM ─────────────────────────────────────────

    def encrypt_aes(self, plaintext: str, key: str) -> str:
        """AES-256-GCM шифрование. key — любая строка (будет хэширована до 32 байт)."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            key_bytes = hashlib.sha256(key.encode()).digest()
            nonce = secrets.token_bytes(12)
            ct = AESGCM(key_bytes).encrypt(nonce, plaintext.encode("utf-8"), None)
            result = base64.b64encode(nonce + ct).decode()
            return f"🔒 Зашифровано (AES-256-GCM):\n  {result}"
        except ImportError:
            # Fallback: XOR с ключом (не безопасно, но работает без deps)
            return self._xor_encrypt(plaintext, key)
        except Exception as e:
            return f"❌ Ошибка шифрования: {e}"

    def decrypt_aes(self, ciphertext: str, key: str) -> str:
        """AES-256-GCM расшифрование."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            key_bytes = hashlib.sha256(key.encode()).digest()
            raw = base64.b64decode(ciphertext.strip())
            nonce, ct = raw[:12], raw[12:]
            pt = AESGCM(key_bytes).decrypt(nonce, ct, None)
            return f"🔓 Расшифровано:\n  {pt.decode('utf-8')}"
        except ImportError:
            return self._xor_decrypt(ciphertext, key)
        except Exception as e:
            return f"❌ Ошибка расшифрования: {e}"

    # ─── Хэши ─────────────────────────────────────────────────────────────

    def sha256(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"🔑 SHA-256: {h}"

    def sha512(self, text: str) -> str:
        h = hashlib.sha512(text.encode("utf-8")).hexdigest()
        return f"🔑 SHA-512: {h}"

    def md5(self, text: str) -> str:
        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        return f"🔑 MD5 (не для безопасности!): {h}"

    # ─── Генераторы ────────────────────────────────────────────────────────

    def gen_key(self, length: int = 32) -> str:
        """Генерация безопасного случайного ключа (hex)."""
        length = max(8, min(length, 128))
        key = secrets.token_hex(length)
        return f"🗝️ Случайный ключ ({length*2} hex-символов):\n  {key}"

    def gen_password(self, length: int = 20) -> str:
        """Генерация безопасного пароля."""
        length = max(8, min(length, 64))
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        return f"🔐 Пароль ({length} символов):\n  {pwd}"

    # ─── Base64 ───────────────────────────────────────────────────────────

    def b64_encode(self, text: str) -> str:
        result = base64.b64encode(text.encode("utf-8")).decode()
        return f"📄 Base64:\n  {result}"

    def b64_decode(self, encoded: str) -> str:
        try:
            result = base64.b64decode(encoded.strip()).decode("utf-8")
            return f"📄 Декодировано:\n  {result}"
        except Exception as e:
            return f"❌ Base64 ошибка: {e}"

    # ─── HMAC ────────────────────────────────────────────────────────────

    def hmac_sign(self, key: str, data: str) -> str:
        sig = hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"✍️ HMAC-SHA256:\n  {sig}"

    def run(self) -> str:
        return (
            "🔐 CRYPTO UTILS:\n"
            "  зашифруй <текст> ключ <ключ>    — AES-256-GCM\n"
            "  расшифруй <текст> ключ <ключ>   — расшифровать\n"
            "  хэш <текст>                     — SHA-256\n"
            "  генерируй ключ [длина]           — случайный ключ\n"
            "  генерируй пароль [длина]         — безопасный пароль\n"
            "  base64 кодируй/раскодируй <текст>\n"
            "  hmac <ключ> <данные>             — HMAC-SHA256"
        )

    # ─── Парсинг команд ──────────────────────────────────────────────────

    def _parse_encrypt(self, text: str) -> str:
        import re
        m = re.search(r"зашифруй\s+(.+?)\s+ключ\s+(\S+)", text, re.I)
        if m:
            return self.encrypt_aes(m.group(1), m.group(2))
        payload = text.split("зашифруй ", 1)[-1].strip()
        return self.encrypt_aes(payload, "argos_default_key")

    def _parse_decrypt(self, text: str) -> str:
        import re
        m = re.search(r"расшифруй\s+(\S+)\s+ключ\s+(\S+)", text, re.I)
        if m:
            return self.decrypt_aes(m.group(1), m.group(2))
        payload = text.split("расшифруй ", 1)[-1].strip()
        return self.decrypt_aes(payload, "argos_default_key")

    def _parse_hash(self, text: str) -> str:
        t = text.lower()
        if "sha512" in t:
            payload = text.split("sha512", 1)[-1].strip().lstrip(" :")
            return self.sha512(payload)
        payload = re.sub(r"хэш\s*sha\d*\s*[:—]?\s*", "", text, flags=re.I).strip()
        if not payload:
            payload = text.split("хэш ", 1)[-1].strip()
        import re
        return self.sha256(payload)

    def _parse_hmac(self, text: str) -> str:
        import re
        parts = text.strip().split()
        if len(parts) >= 3:
            return self.hmac_sign(parts[1], " ".join(parts[2:]))
        return "Формат: hmac <ключ> <данные>"

    def _gen_key(self, text: str) -> str:
        import re
        m = re.search(r"(\d+)", text)
        length = int(m.group(1)) if m else 32
        return self.gen_key(length)

    def _gen_password(self, text: str) -> str:
        import re
        m = re.search(r"(\d+)", text)
        length = int(m.group(1)) if m else 20
        return self.gen_password(length)

    def _xor_encrypt(self, text: str, key: str) -> str:
        """Простое XOR (fallback без cryptography)."""
        key_bytes = key.encode("utf-8")
        xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(text.encode("utf-8")))
        result = base64.b64encode(xored).decode()
        return f"🔒 Зашифровано (XOR, установите cryptography для AES):\n  {result}"

    def _xor_decrypt(self, encoded: str, key: str) -> str:
        try:
            key_bytes = key.encode("utf-8")
            raw = base64.b64decode(encoded.strip())
            xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw))
            return f"🔓 Расшифровано (XOR):\n  {xored.decode('utf-8')}"
        except Exception as e:
            return f"❌ XOR расшифрование: {e}"


import re


def handle(text: str, core=None) -> str | None:
    t = text.lower()
    if not any(kw in t for kw in SKILL_TRIGGERS):
        return None
    return CryptoUtils(core).handle_command(text)
