"""
telegram_bot.py — Аргос Telegram Bridge v2.1

Возможности:
  • Роли: ADMIN (полный доступ) / USER (базовый доступ) / BOT (авторизованные боты)
  • Авторизация ботов: список BOT_IDS в .env — боты могут писать и получать ответы
  • Голосовой ответ: TTS → .ogg файл обратно пользователю
  • Ollama Vision: анализ фото через LLaVA если Gemini недоступен
  • Аудио/Голос/Фото/APK — полная поддержка медиа

Переменные окружения:
  TELEGRAM_BOT_TOKEN   — токен бота
  ADMIN_IDS            — ID администраторов через запятую (полный доступ)
  USER_IDS             — ID обычных пользователей (базовый доступ, через запятую)
  BOT_IDS              — ID авторизованных ботов (через запятую, могут писать как user)
  TG_VOICE_REPLY       — on/off — отвечать голосом (default: off)
  TG_VOICE_ENGINE      — gtts / pyttsx3 (default: gtts)
  TG_VOICE_LANG        — язык для gTTS (default: ru)
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import socket
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, Message
from telegram.error import InvalidToken, TelegramError
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

HISTORY_MESSAGES_LIMIT = 10

# ── РОЛИ ──────────────────────────────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_BOT = "bot"
ROLE_NONE = None

# Команды/интенты, запрещённые для роли USER
_USER_BLOCKED_PREFIXES = (
    "консоль",
    "терминал",
    "выключи систему",
    "убей процесс",
    "удали файл",
    "удали папку",
    "установи persistence",
    "установи автозапуск",
    "удали автозапуск",
    "роль доступа",
    "установи роль",
)


def _load_id_set(env_key: str) -> set[str]:
    """Загружает список ID из переменной окружения через запятую."""
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


class ArgosTelegram:
    def __init__(self, core, admin, flasher):
        self.core = core
        self.admin = admin
        self.flasher = flasher
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.app: Optional[Application] = None

        # ── Роли и авторизация ──
        self.admin_ids: set[str] = _load_id_set("ADMIN_IDS")
        self.user_ids: set[str] = _load_id_set("USER_IDS")
        self.bot_ids: set[str] = _load_id_set("BOT_IDS")

        # Обратная совместимость: USER_ID (одиночный) → admin
        legacy = os.getenv("USER_ID", "").strip()
        if legacy:
            self.admin_ids.add(legacy)

        # ── Голосовой ответ ──
        self.voice_reply = os.getenv("TG_VOICE_REPLY", "off").strip().lower() in (
            "1",
            "on",
            "yes",
            "true",
        )
        self.voice_engine = os.getenv("TG_VOICE_ENGINE", "gtts").strip().lower()
        self.voice_lang = os.getenv("TG_VOICE_LANG", "ru").strip()
        self._poll_lock_socket: Optional[socket.socket] = None

    # ── АВТОРИЗАЦИЯ ───────────────────────────────────────────────────────────

    def _get_role(self, update: Update) -> str | None:
        """Определяет роль отправителя. Возвращает ROLE_* или None."""
        user = update.effective_user
        if user is None:
            return ROLE_NONE
        uid = str(user.id)
        if uid in self.admin_ids:
            return ROLE_ADMIN
        if uid in self.user_ids:
            return ROLE_USER
        if uid in self.bot_ids or user.is_bot:
            # Бот авторизован только если его ID в BOT_IDS
            return ROLE_BOT if uid in self.bot_ids else ROLE_NONE
        return ROLE_NONE

    def _auth(self, update: Update) -> bool:
        """True если отправитель имеет хоть какую-то роль."""
        return self._get_role(update) is not ROLE_NONE

    def _is_admin(self, update: Update) -> bool:
        return self._get_role(update) == ROLE_ADMIN

    def _check_user_blocked(self, text: str) -> bool:
        """True если команда запрещена для роли USER."""
        t = text.lower().strip()
        return any(t.startswith(p) for p in _USER_BLOCKED_PREFIXES)

    async def _deny(self, update: Update, reason: str = "Доступ запрещён."):
        if update.message:
            await update.message.reply_text(f"⛔ {reason}")

    # ── ГОЛОСОВОЙ ОТВЕТ ───────────────────────────────────────────────────────

    def _tts_to_ogg(self, text: str) -> Optional[bytes]:
        """Генерирует .ogg (opus) из текста. Возвращает байты или None."""
        clean = text[:500]  # Telegram voice limit
        try:
            if self.voice_engine == "gtts":
                return self._tts_gtts(clean)
            return self._tts_pyttsx3(clean)
        except Exception:
            return None

    def _tts_gtts(self, text: str) -> Optional[bytes]:
        try:
            from gtts import gTTS

            buf = io.BytesIO()
            gTTS(text=text, lang=self.voice_lang, slow=False).write_to_fp(buf)
            mp3_bytes = buf.getvalue()
            # Конвертация MP3 → OGG (opus) через ffmpeg если доступен
            return self._mp3_to_ogg(mp3_bytes)
        except ImportError:
            return None

    def _mp3_to_ogg(self, mp3_bytes: bytes) -> bytes:
        """Конвертирует MP3 в OGG opus через ffmpeg. Если нет ffmpeg — возвращает mp3."""
        try:
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "mp3",
                    "-i",
                    "pipe:0",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "64k",
                    "-f",
                    "ogg",
                    "pipe:1",
                ],
                input=mp3_bytes,
                capture_output=True,
                timeout=15,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return mp3_bytes  # fallback: отправим mp3 как аудио

    def _tts_pyttsx3(self, text: str) -> Optional[bytes]:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                if "russian" in v.name.lower() or "ru" in v.id.lower():
                    engine.setProperty("voice", v.id)
                    break
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name
            engine.save_to_file(text, wav_path)
            engine.runAndWait()
            with open(wav_path, "rb") as f:
                wav_bytes = f.read()
            os.remove(wav_path)
            return self._wav_to_ogg(wav_bytes)
        except Exception:
            return None

    def _wav_to_ogg(self, wav_bytes: bytes) -> bytes:
        try:
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "wav",
                    "-i",
                    "pipe:0",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "64k",
                    "-f",
                    "ogg",
                    "pipe:1",
                ],
                input=wav_bytes,
                capture_output=True,
                timeout=15,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return wav_bytes

    async def _reply_with_voice(self, message: Message, text: str):
        """Отправляет голосовой ответ если включён voice_reply, иначе текст."""
        if self.voice_reply:
            audio_bytes = await asyncio.to_thread(self._tts_to_ogg, text)
            if audio_bytes:
                try:
                    await message.reply_voice(
                        voice=io.BytesIO(audio_bytes),
                        caption=text[:200] + ("…" if len(text) > 200 else ""),
                    )
                    return
                except Exception:
                    pass
        # fallback — текст
        await message.reply_text(text[:4000])

    async def _safe_reply_text(self, message: Message, text: str, markdown: bool = True):
        payload = (text or "")[:4000]
        if markdown:
            try:
                await message.reply_text(payload, parse_mode="Markdown")
                return
            except Exception:
                pass
        await message.reply_text(payload, parse_mode=None)

    def _acquire_poll_lock(self) -> tuple[bool, str]:
        host = os.getenv("ARGOS_TG_LOCK_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = int(os.getenv("ARGOS_TG_LOCK_PORT", "58443") or "58443")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            sock.listen(1)
            self._poll_lock_socket = sock
            return True, f"{host}:{port}"
        except OSError:
            try:
                sock.close()
            except Exception:
                pass
            return False, f"{host}:{port}"

    def _release_poll_lock(self):
        sock = self._poll_lock_socket
        self._poll_lock_socket = None
        if sock is None:
            return
        try:
            sock.close()
        except Exception:
            pass

    async def _handle_telegram_error(self, update, context):
        error = getattr(context, "error", None)
        text = str(error or "")
        if "terminated by other getUpdates request" in text or "Conflict:" in text:
            if getattr(self, "_conflict_notified", False):
                return
            self._conflict_notified = True
            print("[TG-BRIDGE]: Конфликт polling — другой экземпляр бота уже использует getUpdates.")
            try:
                updater = getattr(context.application, "updater", None)
                if updater is not None:
                    await updater.stop()
            except Exception:
                pass
            try:
                await context.application.stop()
            except Exception:
                pass
            return
        # WinError 10054 / ConnectionResetError — шум Windows asyncio ProactorEventLoop, игнорируем
        if "10054" in text or "ConnectionResetError" in text or "WinError" in text:
            return
        print(f"[TG-BRIDGE]: Error handler caught: {text}")

    # ── OLLAMA VISION ─────────────────────────────────────────────────────────

    # ── КЛАВИАТУРЫ ────────────────────────────────────────────────────────────

    def _admin_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("/status"), KeyboardButton("/history"), KeyboardButton("/help")],
                [
                    KeyboardButton("/voice_on"),
                    KeyboardButton("/voice_off"),
                    KeyboardButton("/skills"),
                ],
                [KeyboardButton("/crypto"), KeyboardButton("/alerts"), KeyboardButton("/apk")],
                [KeyboardButton("/smart"), KeyboardButton("/iot"), KeyboardButton("/memory")],
                [
                    KeyboardButton("/providers"),
                    KeyboardButton("/roles"),
                    KeyboardButton("/network"),
                ],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Команда или директива...",
        )

    def _user_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("/status"), KeyboardButton("/history"), KeyboardButton("/help")],
                [KeyboardButton("/crypto"), KeyboardButton("/memory"), KeyboardButton("/smart")],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Команда или вопрос...",
        )

    # ── КОМАНДЫ ───────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            await self._deny(update, "Нет доступа. Обратитесь к администратору.")
            return
        keyboard = self._admin_keyboard() if role == ROLE_ADMIN else self._user_keyboard()
        role_label = {"admin": "👑 Администратор", "user": "👤 Пользователь", "bot": "🤖 Бот"}.get(
            role, role
        )
        await update.message.reply_text(
            f"👁️ *АРГОС ОНЛАЙН*\n"
            f"Ваша роль: {role_label}\n\n"
            f"Отправь директиву текстом, голосом, фото или аудио.\n"
            f"/help — полный список команд",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        # Используем кэш sensor_bridge — не блокирует
        health = self.core.sensors.get_full_report()
        state = self.core.quantum.generate_state()
        ai_mode = self.core.ai_mode_label()
        p2p_str = ""
        if self.core.p2p:
            try:
                net = self.core.p2p.network_status()
                p2p_str = f"\n🌐 P2P: {net[:80]}"
            except Exception:
                pass
        msg = (
            f"📊 *СИСТЕМНЫЙ ДОКЛАД*\n\n"
            f"{health}"
            f"{p2p_str}\n\n"
            f"⚛️ Квантовое состояние: `{state['name']}`\n"
            f"🤖 AI режим: `{ai_mode}`"
        )
        await update.message.reply_text(msg[:4000], parse_mode="Markdown")

    async def cmd_voice_on(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        self.core.voice_on = True
        self.voice_reply = True
        await update.message.reply_text(
            "🔊 Голосовой модуль активирован. Аргос будет отвечать голосом."
        )

    async def cmd_voice_off(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        self.core.voice_on = False
        self.voice_reply = False
        await update.message.reply_text("🔇 Голосовой модуль отключён.")

    async def cmd_voice_reply_toggle(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Переключает только голосовой ОТВЕТ в Telegram (TTS → .ogg)."""
        if not self._auth(update):
            return await self._deny(update)
        self.voice_reply = not self.voice_reply
        state = "включён ✅" if self.voice_reply else "выключен ❌"
        engine = self.voice_engine.upper()
        await update.message.reply_text(
            f"🔊 Голосовой ответ {state}\n" f"Движок: {engine} | Язык: {self.voice_lang}\n"
        )

    async def cmd_roles(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Показывает текущие роли (только для admin)."""
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        admins = ", ".join(sorted(self.admin_ids)) or "не задано"
        users = ", ".join(sorted(self.user_ids)) or "не задано"
        bots = ", ".join(sorted(self.bot_ids)) or "не задано"
        voice_st = "✅ вкл" if self.voice_reply else "❌ выкл"
        await update.message.reply_text(
            f"🔑 *РОЛИ И ДОСТУП*\n\n"
            f"👑 Admins: `{admins}`\n"
            f"👤 Users:  `{users}`\n"
            f"🤖 Bots:   `{bots}`\n\n"
            f"🔊 Голосовой ответ: {voice_st}\n"
            f"Настройка через .env:\n"
            f"  ADMIN\\_IDS=id1,id2\n"
            f"  USER\\_IDS=id3,id4\n"
            f"  BOT\\_IDS=botid1,botid2",
            parse_mode="Markdown",
        )

    async def cmd_providers(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        try:
            from src.ai_providers import providers_status

            text = providers_status()
        except Exception as e:
            text = f"AI Providers: {e}"
        await update.message.reply_text(text[:4000])

    async def cmd_skills(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        # Всегда берём актуальный runtime-лоадер ядра (manifest + flat skills).
        if self.core.skill_loader:
            report = self.core.skill_loader.list_skills()
        else:
            try:
                from src.skills.evolution import ArgosEvolution

                report = ArgosEvolution().list_skills()
            except ImportError:
                report = "❌ SkillLoader недоступен."
        await update.message.reply_text(report[:4000])

    async def cmd_network(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        if self.core.p2p:
            await update.message.reply_text(self.core.p2p.network_status())
        else:
            await update.message.reply_text("P2P не запущен.")

    async def cmd_sync(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        await update.message.reply_text("🔄 Синхронизирую навыки...")
        if self.core.p2p:
            result = self.core.p2p.sync_skills_from_network()
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("P2P не запущен.")

    async def cmd_crypto(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        try:
            from src.skills.crypto_monitor import CryptoSentinel

            report = CryptoSentinel().report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Крипто: {e}")

    async def cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        if self.core.db:
            hist = self.core.db.format_history(HISTORY_MESSAGES_LIMIT)
            await update.message.reply_text(hist[:4000])
        else:
            await update.message.reply_text("БД не подключена.")

    async def cmd_geo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        try:
            from src.connectivity.spatial import SpatialAwareness

            report = SpatialAwareness(db=self.core.db).get_full_report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Геолокация: {e}")

    async def cmd_memory(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        # MemPalace status (новая 4-слойная память)
        try:
            from src.mempalace_bridge import status as mp_status
            mp_info = mp_status()
        except Exception:
            mp_info = ""
        # Старая память ARGOS
        old_mem = ""
        if self.core.memory:
            try:
                old_mem = "\n\n📋 *ARGOS Legacy Memory:*\n" + self.core.memory.format_memory()[:2000]
            except Exception:
                pass
        reply = (mp_info or "🧠 MemPalace: не инициализирован") + old_mem
        await update.message.reply_text(reply[:4000], parse_mode="Markdown")

    async def cmd_alerts(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        if self.core.alerts:
            await update.message.reply_text(self.core.alerts.status())
        else:
            await update.message.reply_text("Система алертов не активирована.")

    async def cmd_replicate(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        await update.message.reply_text("📦 Создаю реплику системы...")
        try:
            result = self.core.replicator.create_replica()
            await update.message.reply_text(result)
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

    async def cmd_smart(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        if self.core.smart_sys:
            await update.message.reply_text(self.core.smart_sys.full_status()[:4000])
        else:
            await update.message.reply_text("Умные системы не подключены.")

    async def cmd_iot(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        if self.core.iot_bridge:
            await update.message.reply_text(self.core.iot_bridge.status()[:4000])
        else:
            await update.message.reply_text("IoT Bridge не подключен.")

    async def cmd_apk(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        await update.message.reply_text("📦 Запускаю сборку APK...")
        ok, payload = await asyncio.to_thread(self._build_apk_sync)
        if not ok:
            await update.message.reply_text(f"❌ {payload}")
            return
        try:
            with open(payload, "rb") as f:
                await update.message.reply_document(
                    document=f, filename=os.path.basename(payload), caption="✅ APK готов"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Не удалось отправить APK: {e}")

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            return await self._deny(update)
        if role == ROLE_ADMIN:
            text = self._help_admin()
        else:
            text = self._help_user()
        await update.message.reply_text(text, parse_mode="Markdown")

    def _help_admin(self) -> str:
        return (
            "👁️ *АРГОС — АДМИНИСТРАТОР*\n\n"
            "*Система:*\n"
            "• `/status` — мониторинг ЦП/ОЗУ/диска\n"
            "• `/roles` — роли и авторизация\n"
            "• `/providers` — статус AI-провайдеров\n"
            "• `/alerts` — алерты системы\n"
            "• `/network` — P2P сеть\n"
            "• `/replicate` — создать копию\n"
            "• `/apk` — сборка APK\n\n"
            "*Управление файлами:*\n"
            "• `покажи файлы [путь]`\n"
            "• `прочитай файл [путь]`\n"
            "• `создай файл [имя] [текст]`\n"
            "• `удали файл [путь]`\n"
            "• `консоль [команда]`\n\n"
            "*IoT / Smart:*\n"
            "• `/smart` — умные системы\n"
            "• `/iot` — IoT устройства\n\n"
            "*AI модели:*\n"
            "• `режим ии [gemini/ollama/groq/deepseek]`\n"
            "• `модель обучить` / `модель статус`\n"
            "• `модель квантовый статус`\n"
            "• `статус провайдеров`\n\n"
            "*Голос и медиа:*\n"
            "• `/voice_on` / `/voice_off` — TTS\n"
            "• `/voicereply` — голосовой ответ в Telegram\n"
            "• Голосовое сообщение → распознаётся и выполняется\n"
            "• Фото → анализ через Vision AI (Gemini или Ollama LLaVA)\n"
            "• Аудиофайл → расшифровка через Whisper\n\n"
            "*Память:*\n"
            "• `/memory` — долгосрочная память\n"
            "• `/history` — история диалога\n"
            "• `запомни [ключ]: [значение]`\n\n"
            "*Прочее:*\n"
            "• `/crypto` — BTC/ETH курсы\n"
            "• `/skills` — список навыков\n"
            "• `помощь` — полный список команд ядра"
        )

    def _help_user(self) -> str:
        return (
            "👁️ *АРГОС — ПОЛЬЗОВАТЕЛЬ*\n\n"
            "• `/status` — состояние системы\n"
            "• `/crypto` — курсы криптовалют\n"
            "• `/memory` — ваши записи\n"
            "• `/smart` — умные системы\n"
            "• `/history` — история диалога\n\n"
            "*Голос и медиа:*\n"
            "• Голосовое сообщение → выполняется как команда\n"
            "• Фото → анализ изображения\n"
            "• Аудио → расшифровка текста\n\n"
            "*Запросы к ИИ:*\n"
            "• Просто напиши любой вопрос или команду\n"
            "• `запомни [что-то]` — сохранить в память\n"
            "• `расскажи про [тема]` — поиск + ответ"
        )

    # ── ОСНОВНЫЕ ОБРАБОТЧИКИ ──────────────────────────────────────────────────

    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            await self._deny(update, "Доступ запрещён. Попытка входа зафиксирована.")
            return

        user_text = update.message.text or ""
        if not user_text.strip():
            return

        # Проверка блокировок для USER
        if role == ROLE_USER and self._check_user_blocked(user_text):
            await self._deny(update, "Эта команда доступна только администратору.")
            return

        await update.message.reply_text("⚙️ Обрабатываю...")

        try:
            result = await asyncio.wait_for(
                self.core.process_logic_async(user_text, self.admin, self.flasher),
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            await update.message.reply_text(
                "⏱️ Превышено время ожидания (90с). "
                "Система занята — попробуй позже или уточни запрос."
            )
            return
        except Exception as _e:
            await update.message.reply_text(f"❌ Ошибка обработки: {_e}")
            return
        answer = result["answer"]
        state = result["state"]

        full_text = f"👁️ *ARGOS* `[{state}]`\n\n{answer}"

        if self.voice_reply and role in (ROLE_ADMIN, ROLE_USER):
            await self._reply_with_voice(update.message, answer[:500])
            # Текст тоже отправляем (краткий)
            if len(answer) > 50:
                await self._safe_reply_text(update.message, full_text, markdown=True)
        else:
            await self._safe_reply_text(update.message, full_text, markdown=True)

    async def handle_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            return await self._deny(update, "Доступ запрещён.")

        voice = update.message.voice if update.message else None
        if not voice:
            return await update.message.reply_text("❌ Голосовое не обнаружено.")

        await update.message.reply_text("🎙 Распознаю голос...")

        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(voice.file_id)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                temp_path = tmp.name
            await tg_file.download_to_drive(custom_path=temp_path)

            text = await asyncio.to_thread(self.core.transcribe_audio_path, temp_path)
            if not text:
                await update.message.reply_text("🤷 Не удалось распознать. Попробуй ещё раз.")
                return

            await update.message.reply_text(f"📝 Распознано: *{text}*", parse_mode="Markdown")

            if role == ROLE_USER and self._check_user_blocked(text):
                return await self._deny(update, "Эта команда доступна только администратору.")

            result = await self.core.process_logic_async(text, self.admin, self.flasher)
            answer = result["answer"]
            state = result["state"]

            if self.voice_reply:
                await self._reply_with_voice(update.message, answer[:500])
                if len(answer) > 50:
                    await update.message.reply_text(
                        f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}", parse_mode=None
                    )
            else:
                await self._safe_reply_text(
                    update.message,
                    f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}",
                    markdown=True,
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка голосового: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    async def handle_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            return await self._deny(update, "Доступ запрещён.")

        photo = update.message.photo[-1] if update.message.photo else None
        if not photo:
            return await update.message.reply_text("❌ Изображение не обнаружено.")

        caption = update.message.caption or "Подробно опиши что изображено."
        await update.message.reply_text("🖼 Анализирую изображение...")

        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(photo.file_id)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                temp_path = tmp.name
            await tg_file.download_to_drive(custom_path=temp_path)

            if self.core.vision:
                result_text = await asyncio.to_thread(
                    self.core.vision.analyze_image, temp_path, caption
                )
            else:
                result_text = (
                    "❌ Vision модуль не инициализирован. Установи: pip install google-genai Pillow"
                )

            if self.voice_reply and result_text:
                await self._reply_with_voice(update.message, result_text[:500])
            await update.message.reply_text(result_text[:4000])

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка анализа: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    async def handle_audio(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            return await self._deny(update, "Доступ запрещён.")

        audio = update.message.audio if update.message else None
        if not audio:
            return await update.message.reply_text("❌ Аудиофайл не обнаружен.")

        await update.message.reply_text("🎵 Расшифровываю аудио...")

        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(audio.file_id)
            suffix = os.path.splitext(audio.file_name)[1] if audio.file_name else ".mp3"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                temp_path = tmp.name
            await tg_file.download_to_drive(custom_path=temp_path)

            text = await asyncio.to_thread(self.core.transcribe_audio_path, temp_path)
            if not text:
                await update.message.reply_text("🤷 Не удалось расшифровать аудио.")
                return

            await update.message.reply_text(f"📝 Распознано: *{text}*", parse_mode="Markdown")

            if role == ROLE_USER and self._check_user_blocked(text):
                return await self._deny(update, "Эта команда доступна только администратору.")

            result = await self.core.process_logic_async(text, self.admin, self.flasher)
            answer = result["answer"]
            state = result["state"]

            if self.voice_reply:
                await self._reply_with_voice(update.message, answer[:500])
            await self._safe_reply_text(
                update.message,
                f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}",
                markdown=True,
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка аудио: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    # ── APK утилиты ───────────────────────────────────────────────────────────

    def _find_apk_artifact(self) -> Optional[str]:
        candidates = []
        for pattern in ["bin/*.apk", "dist/**/*.apk", "build/**/*.apk"]:
            candidates.extend(Path(".").glob(pattern))
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(candidates[0])

    def _build_apk_sync(self) -> tuple[bool, str]:
        cmd = os.getenv("ARGOS_APK_BUILD_CMD", "").strip()
        if not cmd:
            return False, "ARGOS_APK_BUILD_CMD не задан."
        try:
            subprocess.run(shlex.split(cmd), check=True)
        except subprocess.CalledProcessError as e:
            return False, f"Сборка завершилась с ошибкой: {e}"
        except Exception as e:
            return False, f"Ошибка запуска: {e}"
        apk = self._find_apk_artifact()
        if not apk:
            return False, "APK не найден после сборки."
        return True, apk

    # ── ВАЛИДАЦИЯ ─────────────────────────────────────────────────────────────

    def _is_placeholder_token(self, token: str) -> bool:
        return (token or "").strip().lower() in {"", "your_token_here", "none", "null", "changeme"}

    def _looks_like_token(self, token: str) -> bool:
        t = (token or "").strip()
        if ":" not in t:
            return False
        bot_id, secret = t.split(":", 1)
        return bot_id.isdigit() and len(secret) >= 30

    def can_start(self) -> tuple[bool, str]:
        if self._is_placeholder_token(self.token):
            return False, "TELEGRAM_BOT_TOKEN не задан"
        if not self._looks_like_token(self.token):
            return False, "Формат TELEGRAM_BOT_TOKEN некорректен"
        if not self.admin_ids:
            return False, "ADMIN_IDS не задан (минимум один ID администратора)"
        return True, "ok"

    # ── ЗАПУСК ────────────────────────────────────────────────────────────────

    def run(self):
        can_start, reason = self.can_start()
        if not can_start:
            print(f"[TG-BRIDGE]: Telegram-мост отключён: {reason}.")
            return

        self._conflict_notified = False
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.app = Application.builder().token(self.token).build()
        self.app.add_error_handler(self._handle_telegram_error)

        # Команды
        cmds = [
            ("start", self.cmd_start),
            ("status", self.cmd_status),
            ("voice_on", self.cmd_voice_on),
            ("voice_off", self.cmd_voice_off),
            ("voicereply", self.cmd_voice_reply_toggle),
            ("roles", self.cmd_roles),
            ("providers", self.cmd_providers),
            ("skills", self.cmd_skills),
            ("help", self.cmd_help),
            ("network", self.cmd_network),
            ("sync", self.cmd_sync),
            ("crypto", self.cmd_crypto),
            ("history", self.cmd_history),
            ("geo", self.cmd_geo),
            ("memory", self.cmd_memory),
            ("alerts", self.cmd_alerts),
            ("replicate", self.cmd_replicate),
            ("smart", self.cmd_smart),
            ("iot", self.cmd_iot),
            ("apk", self.cmd_apk),
        ]
        for name, handler in cmds:
            self.app.add_handler(CommandHandler(name, handler))

        # Медиа обработчики
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.app.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Preflight
        try:
            loop.run_until_complete(self.app.bot.get_me())
            loop.run_until_complete(self.app.bot.delete_webhook(drop_pending_updates=True))
            loop.run_until_complete(
                self.app.bot.get_updates(
                    offset=0,
                    timeout=0,
                    allowed_updates=[],
                )
            )
        except InvalidToken:
            print("[TG-BRIDGE]: Токен отклонён сервером.")
            return
        except TelegramError as e:
            text = str(e or "")
            if "terminated by other getUpdates request" in text or "Conflict:" in text:
                print("[TG-BRIDGE]: Telegram polling уже занят другим клиентом. Этот экземпляр не будет запущен.")
                return
            print(f"[TG-BRIDGE]: Preflight error: {e}")
            return
        except Exception as e:
            print(f"[TG-BRIDGE]: Unexpected preflight error: {e}")
            return

        admins_str = ", ".join(sorted(self.admin_ids))
        bots_str = ", ".join(sorted(self.bot_ids)) or "нет"
        print(f"[TG-BRIDGE]: ✅ Мост активен")
        print(f"[TG-BRIDGE]:   Admins: {admins_str}")
        print(f"[TG-BRIDGE]:   Users:  {len(self.user_ids)} ID")
        print(f"[TG-BRIDGE]:   Bots:   {bots_str}")
        print(f"[TG-BRIDGE]:   VoiceReply: {self.voice_reply} ({self.voice_engine})")

        try:
            loop.run_until_complete(
                self.app.run_polling(
                    close_loop=False,
                    drop_pending_updates=True,
                    stop_signals=None,
                )
            )
        except InvalidToken:
            print("[TG-BRIDGE]: Токен отклонён.")
        except TelegramError as e:
            print(f"[TG-BRIDGE]: Telegram error: {e}")
        except Exception as e:
            print(f"[TG-BRIDGE]: Неожиданная ошибка: {e}")
