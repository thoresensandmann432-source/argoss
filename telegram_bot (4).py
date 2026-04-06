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
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, Message
from telegram.error import InvalidToken, TelegramError
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    filters, ContextTypes,
)

HISTORY_MESSAGES_LIMIT = 10

# ── РОЛИ ──────────────────────────────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_USER  = "user"
ROLE_BOT   = "bot"
ROLE_NONE  = None

# Команды/интенты, запрещённые для роли USER
_USER_BLOCKED_PREFIXES = (
    "консоль", "терминал", "выключи систему", "убей процесс",
    "удали файл", "удали папку", "установи persistence",
    "установи автозапуск", "удали автозапуск",
    "роль доступа", "установи роль",
)


def _load_id_set(env_key: str) -> set[str]:
    """Загружает список ID из переменной окружения через запятую."""
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


class ArgosTelegram:
    def __init__(self, core, admin, flasher):
        self.core    = core
        self.admin   = admin
        self.flasher = flasher
        self.token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.app: Optional[Application] = None

        # ── Роли и авторизация ──
        self.admin_ids: set[str] = _load_id_set("ADMIN_IDS")
        self.user_ids:  set[str] = _load_id_set("USER_IDS")
        self.bot_ids:   set[str] = _load_id_set("BOT_IDS")

        # Обратная совместимость: USER_ID (одиночный) → admin
        legacy = os.getenv("USER_ID", "").strip()
        if legacy:
            self.admin_ids.add(legacy)

        # ── Голосовой ответ ──
        self.voice_reply  = os.getenv("TG_VOICE_REPLY", "off").strip().lower() in ("1", "on", "yes", "true")
        self.voice_engine = os.getenv("TG_VOICE_ENGINE", "gtts").strip().lower()
        self.voice_lang   = os.getenv("TG_VOICE_LANG",   "ru").strip()


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
        """Конвертирует MP3 в OGG opus. Пробует ffmpeg, затем pydub, затем mp3 as-is."""
        # Вариант 1: ffmpeg (лучшее качество)
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            try:
                proc = subprocess.run(
                    [ffmpeg, "-y", "-f", "mp3", "-i", "pipe:0",
                     "-c:a", "libopus", "-b:a", "64k", "-f", "ogg", "pipe:1"],
                    input=mp3_bytes, capture_output=True, timeout=15,
                )
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout
            except Exception:
                pass
        # Вариант 2: pydub (pip install pydub)
        try:
            from pydub import AudioSegment
            import io as _io
            seg = AudioSegment.from_mp3(_io.BytesIO(mp3_bytes))
            buf = _io.BytesIO()
            seg.export(buf, format="ogg", codec="libopus")
            return buf.getvalue()
        except Exception:
            pass
        # Fallback: mp3 как есть (Telegram примет как аудио-файл)
        return mp3_bytes

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
                ["ffmpeg", "-y", "-f", "wav", "-i", "pipe:0",
                 "-c:a", "libopus", "-b:a", "64k", "-f", "ogg", "pipe:1"],
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
                # Пробуем как voice (OGG opus)
                try:
                    await message.reply_voice(
                        voice=io.BytesIO(audio_bytes),
                        caption=text[:200] + ("…" if len(text) > 200 else ""),
                    )
                    return
                except Exception:
                    pass
                # Fallback: отправляем как аудио-файл
                try:
                    await message.reply_audio(
                        audio=io.BytesIO(audio_bytes),
                        filename="argos_reply.mp3",
                        title="Аргос",
                    )
                    return
                except Exception:
                    pass
        # fallback — текст
        await message.reply_text(text[:4000])

    # ── OLLAMA VISION ─────────────────────────────────────────────────────────

    # ── КЛАВИАТУРЫ ────────────────────────────────────────────────────────────

    def _admin_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("/status"),    KeyboardButton("/history"),   KeyboardButton("/help")],
                [KeyboardButton("/voice_on"),  KeyboardButton("/voice_off"), KeyboardButton("/skills")],
                [KeyboardButton("/crypto"),    KeyboardButton("/alerts"),    KeyboardButton("/apk")],
                [KeyboardButton("/smart"),     KeyboardButton("/iot"),       KeyboardButton("/memory")],
                [KeyboardButton("/providers"), KeyboardButton("/roles"),     KeyboardButton("/network")],
                [KeyboardButton("/restart"),   KeyboardButton("/update"),    KeyboardButton("/patches")],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Команда или директива...",
        )

    def _user_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("/status"), KeyboardButton("/history"), KeyboardButton("/help")],
                [KeyboardButton("/crypto"), KeyboardButton("/memory"),  KeyboardButton("/smart")],
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
        role_label = {"admin": "👑 Администратор", "user": "👤 Пользователь", "bot": "🤖 Бот"}.get(role, role)
        await update.message.reply_text(
            f"👁️ *АРГОС ОНЛАЙН*\n"
            f"Ваша роль: {role_label}\n\n"
            f"Отправь директиву текстом, голосом, фото или аудио.\n"
            f"/help — полный список команд",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        # Используем кэш sensor_bridge — не блокирует
        health  = self.core.sensors.get_full_report()
        state   = self.core.quantum.generate_state()
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
        if not self._auth(update): return await self._deny(update)
        self.core.voice_on = True
        self.voice_reply = True
        await update.message.reply_text("🔊 Голосовой модуль активирован. Аргос будет отвечать голосом.")

    async def cmd_voice_off(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        self.core.voice_on = False
        self.voice_reply = False
        await update.message.reply_text("🔇 Голосовой модуль отключён.")

    async def cmd_voice_reply_toggle(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Переключает только голосовой ОТВЕТ в Telegram (TTS → .ogg)."""
        if not self._auth(update): return await self._deny(update)
        self.voice_reply = not self.voice_reply
        state = "включён ✅" if self.voice_reply else "выключен ❌"
        engine = self.voice_engine.upper()
        await update.message.reply_text(
            f"🔊 Голосовой ответ {state}\n"
            f"Движок: {engine} | Язык: {self.voice_lang}\n"
        )

    async def cmd_roles(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Показывает текущие роли (только для admin)."""
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        admins = ", ".join(sorted(self.admin_ids)) or "не задано"
        users  = ", ".join(sorted(self.user_ids))  or "не задано"
        bots   = ", ".join(sorted(self.bot_ids))   or "не задано"
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
        if not self._auth(update): return await self._deny(update)
        try:
            from src.ai_providers import providers_status
            text = providers_status()
        except Exception as e:
            text = f"AI Providers: {e}"
        await update.message.reply_text(text[:4000])

    async def cmd_skills(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        try:
            from src.skills.evolution import ArgosEvolution
            report = ArgosEvolution().list_skills()
        except ImportError:
            if self.core.skill_loader:
                report = self.core.skill_loader.list_skills()
            else:
                report = "❌ ArgosEvolution недоступен."
        await update.message.reply_text(report[:4000])

    async def cmd_network(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        if self.core.p2p:
            await update.message.reply_text(self.core.p2p.network_status())
        else:
            await update.message.reply_text("P2P не запущен.")

    async def cmd_sync(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        await update.message.reply_text("🔄 Синхронизирую навыки...")
        if self.core.p2p:
            result = self.core.p2p.sync_skills_from_network()
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("P2P не запущен.")

    async def cmd_crypto(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        try:
            from src.skills.crypto_monitor import CryptoSentinel
            report = CryptoSentinel().report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Крипто: {e}")

    async def cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        if self.core.db:
            hist = self.core.db.format_history(HISTORY_MESSAGES_LIMIT)
            await update.message.reply_text(hist[:4000])
        else:
            await update.message.reply_text("БД не подключена.")

    async def cmd_geo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        try:
            from src.connectivity.spatial import SpatialAwareness
            report = SpatialAwareness(db=self.core.db).get_full_report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Геолокация: {e}")

    async def cmd_memory(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        if self.core.memory:
            await update.message.reply_text(self.core.memory.format_memory()[:4000])
        else:
            await update.message.reply_text("Память не активирована.")

    async def cmd_alerts(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
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
        if not self._auth(update): return await self._deny(update)
        if self.core.smart_sys:
            await update.message.reply_text(self.core.smart_sys.full_status()[:4000])
        else:
            await update.message.reply_text("Умные системы не подключены.")

    async def cmd_iot(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
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
                    document=f,
                    filename=os.path.basename(payload),
                    caption="✅ APK готов"
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


    # ── ПРЯМОЕ ВЫПОЛНЕНИЕ ФАЙЛОВЫХ КОМАНД ────────────────────────────────────
    # Обходит core.process_logic и ToolCalling полностью.
    # Вызывается ДО process_logic_async для известных команд.

    _FILE_COMMANDS = (
        "создай файл", "напиши файл",
        "прочитай файл", "открой файл",
        "удали файл", "удали папку",
        "покажи файлы", "список файлов",
        "файлы ", "добавь в файл",
        "допиши в файл", "дополни файл",
        "отредактируй файл", "измени файл",
        "скопируй файл", "переименуй файл",
        "консоль ", "терминал ",
        "список процессов",
        "статус системы", "чек-ап",
        "убей процесс",
    )

    def _try_direct_execute(self, text: str) -> str | None:
        """
        Выполняет файловые и системные команды напрямую через self.admin,
        минуя core.process_logic и ToolCalling полностью.
        Возвращает строку-ответ или None если команда не распознана.
        """
        t = text.lower().strip()
        if not any(t.startswith(cmd) or t == cmd.strip()
                   for cmd in self._FILE_COMMANDS):
            return None

        # Гарантируем admin
        adm = self.admin
        if adm is None:
            try:
                from src.admin import ArgosAdmin
                adm = ArgosAdmin()
                self.admin = adm
            except Exception as e:
                return f"❌ admin недоступен: {e}"

        try:
            # Создать файл
            if any(t.startswith(k) for k in ("создай файл", "напиши файл")):
                body = text
                for k in ("создай файл", "напиши файл"):
                    body = body.replace(k, "").replace(k.capitalize(), "")
                body = body.strip()
                parts = body.split(maxsplit=1)
                fname    = parts[0] if parts else "note.txt"
                fcontent = parts[1] if len(parts) > 1 else ""
                return adm.create_file(fname, fcontent)

            # Прочитать файл
            if any(t.startswith(k) for k in ("прочитай файл", "открой файл")):
                path = text
                for k in ("прочитай файл", "открой файл"):
                    path = path.replace(k, "").replace(k.capitalize(), "").strip()
                return adm.read_file(path.strip())

            # Список файлов
            if any(t.startswith(k) for k in ("покажи файлы", "список файлов", "файлы ")):
                path = text
                for k in ("покажи файлы", "список файлов", "файлы"):
                    path = path.replace(k, "").replace(k.capitalize(), "").strip()
                return adm.list_dir(path or ".")

            # Удалить файл
            if any(t.startswith(k) for k in ("удали файл", "удали папку")):
                path = text
                for k in ("удали файл", "удали папку"):
                    path = path.replace(k, "").replace(k.capitalize(), "").strip()
                return adm.delete_item(path.strip())

            # Добавить в файл
            if any(t.startswith(k) for k in ("добавь в файл", "допиши в файл", "дополни файл")):
                tail = text
                for k in ("добавь в файл", "допиши в файл", "дополни файл"):
                    if k in t:
                        tail = text.split(k, 1)[-1].strip()
                        break
                parts = tail.split(maxsplit=1)
                if len(parts) >= 2:
                    return adm.append_file(parts[0], parts[1])
                return "Формат: добавь в файл [путь] [текст]"

            # Скопировать
            if t.startswith("скопируй файл"):
                tail = text.replace("скопируй файл", "").strip()
                parts = tail.split(maxsplit=1)
                if len(parts) == 2:
                    return adm.copy_file(parts[0], parts[1])
                return "Формат: скопируй файл [откуда] [куда]"

            # Переименовать
            if t.startswith("переименуй файл"):
                tail = text.replace("переименуй файл", "").strip()
                parts = tail.split(maxsplit=1)
                if len(parts) == 2:
                    return adm.rename_file(parts[0], parts[1])
                return "Формат: переименуй файл [старое] [новое]"

            # Консоль
            if t.startswith("консоль ") or t.startswith("терминал "):
                cmd = text.split(None, 1)[1].strip() if len(text.split()) > 1 else ""
                if cmd:
                    return adm.run_cmd(cmd, user="telegram")
                return "Формат: консоль [команда]"

            # Список процессов
            if t.startswith("список процессов"):
                return adm.list_processes()

            # Статус системы
            if any(t.startswith(k) for k in ("статус системы", "чек-ап")):
                return adm.get_stats()

            # Убить процесс
            if t.startswith("убей процесс"):
                name = text.replace("убей процесс", "").strip()
                return adm.kill_process(name) if name else "Укажи имя процесса"

        except Exception as e:
            return f"❌ Ошибка выполнения: {e}"

        return None


    async def handle_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """
        Принимает .py файлы от admin, применяет как патч к кодовой базе.

        Безопасность:
          - Только ADMIN_IDS могут отправлять патчи
          - Синтаксическая проверка перед применением
          - Автоматическая очистка __pycache__ (Windows-совместимо)
          - Резервная копия оригинала перед перезаписью
          - Отчёт о применении
        """
        if not self._is_admin(update):
            await self._deny(update, "Патчи только для администратора.")
            return

        doc = update.message.document if update.message else None
        if not doc:
            return

        fname = doc.file_name or ""
        # Telegram добавляет " (N)" к дублирующимся именам: "core (14).py" → "core.py"
        import re as _re
        fname = _re.sub(r' \(\d+\)(?=\.)', '', fname)
        # Принимаем только .py файлы
        if not fname.endswith(".py"):
            await update.message.reply_text(
                f"❌ Только .py файлы. Получен: `{fname}`",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text(f"📥 Получен патч `{fname}`. Применяю...", parse_mode="Markdown")

        import os, shutil, sys, importlib, tempfile, ast
        from pathlib import Path

        temp_path = None
        try:
            # 1. Скачиваем патч во временный файл
            tg_file = await ctx.bot.get_file(doc.file_id)
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False,
                                             mode='wb') as tmp:
                temp_path = tmp.name
            await tg_file.download_to_drive(custom_path=temp_path)

            # 2. Читаем содержимое
            with open(temp_path, 'r', encoding='utf-8') as f:
                patch_code = f.read()

            # 3. Синтаксическая проверка
            try:
                ast.parse(patch_code)
            except SyntaxError as se:
                await update.message.reply_text(
                    f"❌ Синтаксическая ошибка в патче:\n`{se}`",
                    parse_mode="Markdown"
                )
                return

            # 4. Определяем куда сохранять
            # Имя файла → путь в проекте
            # patch_core.py          → core.py
            # patch_src_agent.py     → src/agent.py
            # src_connectivity_foo.py → src/connectivity/foo.py
            target_path = self._resolve_patch_target(fname)

            if target_path is None:
                # Файл не является патчем — сохраняем как есть рядом с main.py
                target_path = fname.replace("patch_", "")

            target = Path(target_path)

            # 5. Резервная копия если файл существует
            backup_path = None
            if target.exists():
                backup_path = str(target) + ".bak"
                shutil.copy2(str(target), backup_path)

            # 6. Создаём папку если нужно (Windows-совместимо)
            target.parent.mkdir(parents=True, exist_ok=True)

            # 7. Записываем патч
            with open(str(target), 'w', encoding='utf-8') as f:
                f.write(patch_code)

            # 8. Очищаем __pycache__ (Windows: удаляем .pyc для этого файла)
            cache_cleared = self._clear_pyc_cache(target)

            # 9. Горячая перезагрузка модуля если возможно
            hot_reload_msg = self._hot_reload_module(target_path)

            # 10. Отчёт
            lines = [
                f"✅ Патч `{fname}` применён!",
                f"📄 Файл: `{target_path}`",
                f"📦 Размер: {target.stat().st_size} байт",
                f"🗑 Кеш: {cache_cleared}",
            ]
            if backup_path:
                lines.append(f"💾 Резервная копия: `{backup_path}`")
            if hot_reload_msg:
                lines.append(f"🔄 {hot_reload_msg}")
            lines.append("\n⚡ Изменения вступят в силу при следующем запросе.")

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка применения патча: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _resolve_patch_target(self, fname: str) -> str | None:
        """
        Определяет путь назначения по имени файла патча.

        Правила именования:
          patch_core.py            → core.py
          patch_admin.py           → src/admin.py  (если есть в src/)
          patch_src_agent.py       → src/agent.py
          patch_src_skills_foo.py  → src/skills/foo.py
          tool_calling.py          → src/tool_calling.py  (без prefix)
          agent.py                 → src/agent.py
          core.py                  → core.py
        """
        import os
        from pathlib import Path

        # Убираем prefix "patch_"
        name = fname
        if name.startswith("patch_"):
            name = name[6:]  # убрать "patch_"

        # Если имя содержит подчёркивания как разделители путей
        # src_connectivity_foo.py → src/connectivity/foo.py
        if "_" in name and not name.startswith("_"):
            parts = name.replace(".py", "").split("_")
            # Пробуем интерпретировать как путь
            for i in range(len(parts), 0, -1):
                candidate_dir = os.path.join(*parts[:i])
                candidate_file = "_".join(parts[i:]) + ".py"
                candidate = os.path.join(candidate_dir, candidate_file)
                if os.path.exists(candidate):
                    return candidate

        # Прямые совпадения
        known_locations = {
            "core.py":          "core.py",
            "admin.py":         "src/admin.py",
            "agent.py":         "src/agent.py",
            "tool_calling.py":  "src/tool_calling.py",
            "telegram_bot.py":  "src/connectivity/telegram_bot.py",
            "system_health.py": "src/connectivity/system_health.py",
            "orangepi_bridge.py": "src/connectivity/orangepi_bridge.py",
            "argos_logger.py":  "src/argos_logger.py",
            "argos_model.py":   "src/argos_model.py",
            "neural_swarm.py":  "src/neural_swarm.py",
            "sensor_bridge.py": "src/connectivity/sensor_bridge.py",
            "p2p_bridge.py":    "src/connectivity/p2p_bridge.py",
            "ollama_trainer.py": "src/ollama_trainer.py",
        }
        if name in known_locations:
            return known_locations[name]

        # Ищем файл в src/ рекурсивно
        for root, _, files in os.walk("src"):
            if name in files:
                return os.path.join(root, name)

        # Файл не найден — сохраняем рядом с main.py
        return name

    def _clear_pyc_cache(self, target_path) -> str:
        """Удаляет .pyc кеш для файла. Windows-совместимо."""
        import os, glob
        from pathlib import Path

        target = Path(target_path)
        cleared = 0

        # Папка __pycache__ рядом с файлом
        cache_dir = target.parent / "__pycache__"
        if cache_dir.exists():
            stem = target.stem
            for pyc in cache_dir.glob(f"{stem}.*.pyc"):
                try:
                    pyc.unlink()
                    cleared += 1
                except Exception:
                    pass
            # Если папка пуста — удаляем
            try:
                if not any(cache_dir.iterdir()):
                    cache_dir.rmdir()
            except Exception:
                pass

        # Также проверяем корневой __pycache__
        root_cache = Path("__pycache__")
        if root_cache.exists():
            for pyc in root_cache.glob(f"{target.stem}.*.pyc"):
                try:
                    pyc.unlink()
                    cleared += 1
                except Exception:
                    pass

        return f"очищено {cleared} .pyc файлов"

    def _hot_reload_module(self, path: str) -> str:
        """Пытается горячо перезагрузить модуль без перезапуска."""
        import sys, importlib
        from pathlib import Path

        # Конвертируем путь в имя модуля
        # src/agent.py → src.agent
        # core.py → core (не модуль — пропускаем)
        path_obj = Path(path)
        if path_obj.parts[0] == "src":
            module_name = ".".join(path_obj.with_suffix("").parts)
        else:
            return ""  # корневые файлы не перезагружаем горячо

        if module_name in sys.modules:
            try:
                mod = sys.modules[module_name]
                importlib.reload(mod)
                return f"Модуль `{module_name}` перезагружен"
            except Exception as e:
                return f"Горячая перезагрузка не удалась: {e}"

        return ""

    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            await self._deny(update, "Доступ запрещён. Попытка входа зафиксирована.")
            return

        user_text = update.message.text or ""
        if not user_text.strip():
            return

        # Убираем префикс "Имя:" если сообщение переслано или скопировано с именем
        import re as _re
        user_text = _re.sub(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9_]{0,30}:\s*", "", user_text).strip()
        if not user_text:
            return

        # Проверка блокировок для USER
        if role == ROLE_USER and self._check_user_blocked(user_text):
            await self._deny(update, "Эта команда доступна только администратору.")
            return

        # ── Прямое выполнение файловых/системных команд ─────────────────
        # Обходит core.process_logic и ToolCalling полностью
        direct_answer = self._try_direct_execute(user_text)
        if direct_answer is not None:
            await update.message.reply_text(
                f"👁️ *ARGOS* `[Direct]`\n\n{direct_answer[:4000]}",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text("⚙️ Обрабатываю...")

        result = await self.core.process_logic_async(user_text, self.admin, self.flasher)
        answer = result["answer"]
        state  = result["state"]

        full_text = f"👁️ *ARGOS* `[{state}]`\n\n{answer}"

        if self.voice_reply and role in (ROLE_ADMIN, ROLE_USER):
            await self._reply_with_voice(update.message, answer[:500])
            # Текст тоже отправляем (краткий)
            if len(answer) > 50:
                await update.message.reply_text(full_text[:4000], parse_mode="Markdown")
        else:
            await update.message.reply_text(full_text[:4000], parse_mode="Markdown")

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

            import re as _re
            text = _re.sub(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9_]{0,30}:\s*", "", text).strip()
            await update.message.reply_text(f"📝 Распознано: *{text}*", parse_mode="Markdown")

            if role == ROLE_USER and self._check_user_blocked(text):
                return await self._deny(update, "Эта команда доступна только администратору.")

            result = await self.core.process_logic_async(text, self.admin, self.flasher)
            answer = result["answer"]
            state  = result["state"]

            if self.voice_reply:
                await self._reply_with_voice(update.message, answer[:500])
                if len(answer) > 50:
                    await update.message.reply_text(
                        f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}",
                        parse_mode="Markdown"
                    )
            else:
                await update.message.reply_text(
                    f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}",
                    parse_mode="Markdown"
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
                result_text = "❌ Vision модуль не инициализирован. Установи: pip install google-genai Pillow"

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
            state  = result["state"]

            if self.voice_reply:
                await self._reply_with_voice(update.message, answer[:500])
            await update.message.reply_text(
                f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка аудио: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass




    async def cmd_patch_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Показывает список .bak файлов (резервных копий патчей)."""
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        import os
        from pathlib import Path
        backups = list(Path(".").rglob("*.bak"))[:20]
        if not backups:
            await update.message.reply_text("📋 Резервных копий патчей нет.")
            return
        lines = ["📋 Резервные копии (*.bak):"]
        for b in backups:
            size = b.stat().st_size
            lines.append(f"  💾 `{b}` ({size} байт)")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


    async def cmd_restart(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Перезапускает Аргос (Windows: taskkill + start)."""
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        
        await update.message.reply_text("🔄 Перезапускаю Аргос...")
        
        import sys, os, subprocess
        
        try:
            if sys.platform == "win32":
                # Windows: запускаем новый процесс и завершаем текущий
                python = sys.executable
                script = os.path.join(os.getcwd(), "main.py")
                subprocess.Popen(
                    [python, script, "--no-gui"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    cwd=os.getcwd()
                )
                await update.message.reply_text("✅ Новый процесс запущен. Завершаю текущий...")
                os._exit(0)
            else:
                # Linux/macOS
                os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            await update.message.reply_text(f"❌ Перезапуск не удался: {e}")

    async def cmd_update_self(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """git pull + очистка кеша + перезапуск."""
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        
        await update.message.reply_text("🔄 Обновляю Аргос...")
        result = await asyncio.to_thread(
            self.core.process, "обнови себя"
        )
        answer = result.get("answer", str(result)) if isinstance(result, dict) else str(result)
        await update.message.reply_text(answer[:4000])

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

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.app = Application.builder().token(self.token).build()

        # Команды
        cmds = [
            ("start",        self.cmd_start),
            ("status",       self.cmd_status),
            ("voice_on",     self.cmd_voice_on),
            ("voice_off",    self.cmd_voice_off),
            ("voicereply",   self.cmd_voice_reply_toggle),
            ("roles",        self.cmd_roles),
            ("providers",    self.cmd_providers),
            ("skills",       self.cmd_skills),
            ("help",         self.cmd_help),
            ("network",      self.cmd_network),
            ("sync",         self.cmd_sync),
            ("crypto",       self.cmd_crypto),
            ("history",      self.cmd_history),
            ("geo",          self.cmd_geo),
            ("memory",       self.cmd_memory),
            ("alerts",       self.cmd_alerts),
            ("replicate",    self.cmd_replicate),
            ("smart",        self.cmd_smart),
            ("iot",          self.cmd_iot),
            ("apk",          self.cmd_apk),
            ("patches",       self.cmd_patch_status),
            ("restart",       self.cmd_restart),
            ("update",        self.cmd_update_self),

        ]
        for name, handler in cmds:
            self.app.add_handler(CommandHandler(name, handler))

        # Медиа обработчики
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.app.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        # Preflight
        try:
            loop.run_until_complete(self.app.bot.get_me())
        except InvalidToken:
            print("[TG-BRIDGE]: Токен отклонён сервером.")
            return
        except TelegramError as e:
            print(f"[TG-BRIDGE]: Preflight error: {e}")
            return
        except Exception as e:
            print(f"[TG-BRIDGE]: Unexpected preflight error: {e}")
            return

        admins_str = ", ".join(sorted(self.admin_ids))
        bots_str   = ", ".join(sorted(self.bot_ids)) or "нет"
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
