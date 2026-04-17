"""
src/skills/smtp_mailer.py — SMTP Email отправитель для Аргоса.

Использует smtplib (stdlib) + поддержку TLS/SSL.
Настройки из .env:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

Команды:
  отправь письмо на <email> тема <тема> текст <текст>
  smtp статус
  smtp тест
  email тест на <email>
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Отправка email через SMTP с TLS/SSL"

import os
import smtplib
import email.mime.text
import email.mime.multipart
import threading
from datetime import datetime
from typing import TYPE_CHECKING
import re

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

if TYPE_CHECKING:
    from src.core import ArgosCore

SKILL_NAME = "smtp_mailer"
SKILL_TRIGGERS = [
    "отправь письмо",
    "письмо на",
    "smtp статус",
    "smtp тест",
    "email отправь",
    "email тест",
]


class SMTPMailer:
    """SMTP-клиент для отправки email через Аргос."""

    def __init__(self, core: "ArgosCore | None" = None):
        self.core = core
        self._lock = threading.Lock()
        self._sent_count = 0
        self._last_error: str = ""
        self.provider = (os.getenv("SMTP_PROVIDER", "gmail") or "gmail").strip().lower()
        # Загружаем настройки
        self.host = self._read_env("SMTP_HOST", "ARGOS_EMAIL_SMTP_HOST") or self._default_host()
        self.port = self._read_int_env("SMTP_PORT", "ARGOS_EMAIL_SMTP_PORT", default=self._default_port())
        self.user = self._read_env("SMTP_USER", "ARGOS_EMAIL_USERNAME")
        self.password = self._read_env("SMTP_PASSWORD", "ARGOS_EMAIL_PASSWORD")
        self.from_addr = self._read_env("SMTP_FROM", "ARGOS_EMAIL_FROM") or self.user
        self.use_tls = self._read_bool_env("SMTP_TLS", default=self._default_tls())
        self.use_ssl = self._read_bool_env("SMTP_SSL", default=self._default_ssl())

    def _read_env(self, *keys: str) -> str:
        for key in keys:
            value = (os.getenv(key, "") or "").strip()
            if value:
                return value
        return ""

    def _read_bool_env(self, key: str, default: bool) -> bool:
        value = (os.getenv(key, "") or "").strip().lower()
        if not value:
            return default
        return value in {"1", "true", "on", "yes", "да"}

    def _read_int_env(self, *keys: str, default: int) -> int:
        for key in keys:
            value = (os.getenv(key, "") or "").strip()
            if not value:
                continue
            try:
                return int(value)
            except ValueError:
                continue
        return int(default)

    def _default_host(self) -> str:
        return {
            "gmail": "smtp.gmail.com",
            "outlook": "smtp.office365.com",
            "yandex": "smtp.yandex.ru",
        }.get(self.provider, "smtp.gmail.com")

    def _default_port(self) -> int:
        return 587

    def _default_tls(self) -> bool:
        return True

    def _default_ssl(self) -> bool:
        return False

    # ─── Публичный API ───────────────────────────────────────────────────

    def handle_command(self, text: str) -> str | None:
        t = text.lower().strip()
        if "smtp статус" in t:
            return self.status()
        if "smtp тест" in t:
            return self.test_connection()
        if "email тест" in t:
            return self._parse_and_send_test_email(text)
        if "отправь письмо" in t or "email отправь" in t:
            return self._parse_and_send(text)
        return None

    def send(self, to: str, subject: str, body: str, html: bool = False) -> str:
        """Отправить email."""
        if not self.user or not self.password:
            return ("❌ SMTP: не настроены учётные данные.\n"
                    "Добавьте в .env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD")

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr or self.user
        msg["To"] = to
        msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
        msg["X-Mailer"] = "ArgosOS/2.1"

        mime_type = "html" if html else "plain"
        msg.attach(email.mime.text.MIMEText(body, mime_type, "utf-8"))

        try:
            with self._lock:
                if self.use_ssl:
                    server = smtplib.SMTP_SSL(self.host, self.port, timeout=15)
                else:
                    server = smtplib.SMTP(self.host, self.port, timeout=15)
                    if self.use_tls:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()

                server.login(self.user, self.password)
                server.sendmail(self.from_addr or self.user, [to], msg.as_string())
                server.quit()
                self._sent_count += 1
                self._last_error = ""
            return f"✅ Письмо отправлено на {to}\n  Тема: {subject}"
        except smtplib.SMTPAuthenticationError:
            self._last_error = "ошибка аутентификации"
            return ("❌ SMTP: ошибка аутентификации.\n"
                    "Проверьте SMTP_USER и SMTP_PASSWORD в .env")
        except smtplib.SMTPRecipientsRefused:
            self._last_error = f"адрес {to} отклонён"
            return f"❌ SMTP: адрес {to} отклонён сервером."
        except Exception as e:
            self._last_error = str(e)
            return f"❌ SMTP ошибка: {e}"

    def test_connection(self) -> str:
        """Проверить подключение к SMTP серверу."""
        if not self.user or not self.password:
            return "❌ SMTP: учётные данные не настроены в .env"
        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=10)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=10)
                if self.use_tls:
                    server.ehlo()
                    server.starttls()
            server.login(self.user, self.password)
            server.quit()
            return f"✅ SMTP подключение успешно: {self.host}:{self.port} ({self.user})"
        except Exception as e:
            return f"❌ SMTP тест провалился: {e}"

    def status(self) -> str:
        return (
            f"📧 SMTP MAILER:\n"
            f"  Провайдер: {self.provider}\n"
            f"  Сервер: {self.host}:{self.port}\n"
            f"  Пользователь: {self.user or '(не задан)'}\n"
            f"  TLS: {'да' if self.use_tls else 'нет'} | SSL: {'да' if self.use_ssl else 'нет'}\n"
            f"  Отправлено сессии: {self._sent_count}\n"
            f"  Последняя ошибка: {self._last_error or 'нет'}"
        )

    def run(self) -> str:
        return self.status()

    def _parse_and_send(self, text: str) -> str:
        """Парсинг команды: отправь письмо на <email> тема <тема> текст <текст>"""
        t = text
        to_m = re.search(r"(?:на|to)\s+([\w.+\-]+@[\w.\-]+)", t, re.I)
        subject_m = re.search(r"тема\s+(.+?)(?:\s+текст|\s+body|$)", t, re.I)
        body_m = re.search(r"(?:текст|body)\s+(.+)$", t, re.I | re.S)

        if not to_m:
            return "❌ Укажите адрес: отправь письмо на <email> тема <тема> текст <текст>"
        to = to_m.group(1)
        subject = subject_m.group(1).strip() if subject_m else "Сообщение от Аргоса"
        body = body_m.group(1).strip() if body_m else "Письмо отправлено автоматически системой Аргос."
        return self.send(to, subject, body)

    def _parse_and_send_test_email(self, text: str) -> str:
        """Безопасный тест отправки письма на явно указанный адрес."""
        to_m = re.search(r"(?:на|to)\s+([\w.+\-]+@[\w.\-]+)", text, re.I)
        if not to_m:
            return "❌ Укажите адрес: email тест на <email>"

        to = to_m.group(1).strip()
        subject = "ARGOS SMTP test"
        body = (
            "Это тестовое письмо от ARGOS.\n\n"
            f"Провайдер: {self.provider}\n"
            f"SMTP: {self.host}:{self.port}\n"
            f"Отправитель: {self.from_addr or self.user or '(не задан)'}\n"
            f"Время: {datetime.now().isoformat(timespec='seconds')}\n"
        )
        return self.send(to, subject, body)