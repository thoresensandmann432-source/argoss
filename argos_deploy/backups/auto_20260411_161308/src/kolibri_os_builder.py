"""
src/kolibri_os_builder.py — ARGOS OS на основе КолибриОС
═════════════════════════════════════════════════════════════════
КолибриОС (KolibriOS) — сверхлёгкая ОС на ассемблере:
  • Размер: ~3 МБ, загрузка за 1-2 сек
  • Архитектура: x86 / x86_64
  • Python 3.x порт встроен
  • Поддержка GRUB2 chainloading / USB boot / ISO
  • Сайт: http://kolibrios.org

Модуль предоставляет:
  1. KolibriOSBuilder  — сборка гибридного ISO с КолибриОС + ARGOS
  2. MultiPlatformInstaller — установщик образов на PC/Android/Mac
  3. ArgosKolibriProfile — stripped-down профиль ARGOS для КолибриОС

Команды ARGOS:
  создай образ колибри           → KolibriOSBuilder.build()
  создай мультиплатформенный образ → MultiPlatformInstaller.build_all()
  образ для [pc|android|mac]     → MultiPlatformInstaller.build_for(target)
  колибри статус                 → KolibriOSBuilder.status()
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional

from src.argos_logger import get_logger

log = get_logger("argos.kolibri")

ARGOS_VERSION = "2.1.3"
KOLIBRI_VERSION = "0.7.7.0"

# ── Официальные источники КолибриОС ──────────────────────────────────────────
KOLIBRI_DOWNLOAD_URLS = {
    "iso":    "https://builds.kolibrios.org/eng/latest/latest.iso",
    "img":    "https://builds.kolibrios.org/eng/latest/latest.img",
    "github": "https://github.com/KolibriOS/kolibriOS",
    "mirror": "http://ftp.kolibrios.org/users/Serge/new/kernel/",
}

# ── Профили ARGOS для разных платформ ────────────────────────────────────────
ARGOS_PROFILES = {
    "kolibri": {
        "label":       "КолибриОС (x86, ультралёгкий)",
        "min_ram_mb":  32,
        "arch":        ["x86", "x86_64"],
        "features":    ["core", "scheduler", "memory", "telegram_bot"],
        "no_features": ["iot_hub", "firmware_builder", "device_scanner",
                        "p2p_network", "wake_word", "dashboard"],
        "launcher":    "argos_kolibri.py",
        "py_version":  "3.x (KolibriOS port)",
        "note":        "Базовый ИИ ассистент. Без тяжёлых зависимостей.",
    },
    "pc_full": {
        "label":       "PC/ноутбук (x86_64, полный)",
        "min_ram_mb":  512,
        "arch":        ["x86_64"],
        "features":    ["all"],
        "no_features": [],
        "launcher":    "launch.sh",
        "py_version":  "3.10+",
    },
    "android": {
        "label":       "Android APK (arm64-v8a)",
        "min_ram_mb":  512,
        "arch":        ["arm64-v8a"],
        "features":    ["core", "telegram_bot", "scheduler", "iot_hub"],
        "no_features": ["firmware_builder", "p2p_network", "wake_word"],
        "launcher":    "main_kivy.py",
        "py_version":  "Buildozer / Kivy",
    },
    "mac": {
        "label":       "macOS .app (arm64/x86_64)",
        "min_ram_mb":  512,
        "arch":        ["arm64", "x86_64"],
        "features":    ["all"],
        "no_features": [],
        "launcher":    "ARGOS.app",
        "py_version":  "3.11+",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# KOLIBRI OS BUILDER
# ══════════════════════════════════════════════════════════════════════════════

class KolibriOSBuilder:
    """
    Собирает гибридный образ ARGOS OS на базе КолибриОС.

    Структура образа:
      /KOLIBRI/   — ядро КолибриОС (kernel.mnt, bootloader)
      /ARGOS/     — ARGOS Python код (stripped профиль)
      /BOOT/      — GRUB2 мультизагрузочное меню
      /AUTORUN/   — автозапуск ARGOS при старте КолибриОС

    Режим 1 — Hybrid ISO:
      GRUB2 меню → КолибриОС (встроена) или Linux (if available)
      После загрузки КолибриОС автоматически запускает ARGOS Python

    Режим 2 — Chainload:
      Существующий GRUB2 добавляет пункт "ARGOS on KolibriOS"
      Грузит kernel.mnt из /KOLIBRI/

    Режим 3 — USB portable:
      Флешка = КолибриОС + ARGOS, работает на любом x86 ПК без установки
    """

    def __init__(self, output_dir: str = "releases",
                 kolibri_iso_path: str = None) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.kolibri_iso = kolibri_iso_path
        self.root = Path(".").resolve()

    # ── Проверка инструментов ─────────────────────────────────────────────
    def check_tools(self) -> dict:
        tools = {
            "grub-mkrescue":   bool(shutil.which("grub-mkrescue") or shutil.which("grub2-mkrescue")),
            "xorriso":         bool(shutil.which("xorriso")),
            "mkisofs":         bool(shutil.which("mkisofs") or shutil.which("genisoimage")),
            "dd":              bool(shutil.which("dd")),
            "7z":              bool(shutil.which("7z")),
            "wget":            bool(shutil.which("wget") or shutil.which("curl")),
            "kolibri_iso":     bool(self.kolibri_iso and Path(self.kolibri_iso).exists()),
        }
        tools["can_iso"]  = tools["grub-mkrescue"] or tools["xorriso"] or tools["mkisofs"]
        tools["can_usb"]  = tools["dd"]
        return tools

    def status(self) -> str:
        tools = self.check_tools()
        lines = [
            "🐦 ARGOS on КолибриОС — статус:",
            f"  Версия ARGOS:   {ARGOS_VERSION}",
            f"  Версия Колибри: {KOLIBRI_VERSION}",
            "",
            "  Инструменты сборки:",
        ]
        for k, v in tools.items():
            if k.startswith("can_"):
                continue
            icon = "✅" if v else "○"
            lines.append(f"    {icon} {k}")
        lines.extend([
            "",
            f"  Может создать ISO: {'✅' if tools['can_iso'] else '❌'}",
            f"  Может записать USB: {'✅' if tools['can_usb'] else '❌'}",
            "",
            "  Загрузить КолибриОС ISO:",
            f"    {KOLIBRI_DOWNLOAD_URLS['iso']}",
            "",
            "  Команды:",
            "    создай образ колибри            — ZIP-образ для USB",
            "    создай iso колибри              — загрузочный ISO",
            "    мультиплатформенный образ       — PC + Android + Mac",
        ])
        return "\n".join(lines)

    # ── GRUB2 конфиг с КолибриОС ─────────────────────────────────────────
    def _grub_cfg_kolibri(self, version: str = ARGOS_VERSION) -> str:
        return f"""# GRUB2 — ARGOS OS v{version} + КолибриОС
# Собрано ARGOS Smart Flasher

set timeout=10
set default=0

insmod all_video
insmod gfxterm
terminal_output gfxterm

# ── ARGOS on КолибриОС ─────────────────────────────
menuentry 'ARGOS OS v{version} (КолибриОС, рекомендуется)' {{
    set root=(hd0,msdos1)
    # Загружаем КолибриОС kernel.mnt
    multiboot /KOLIBRI/kernel.mnt /KOLIBRI/kernel.mnt
    module   /KOLIBRI/kolibri.img
    boot
}}

# ── Альтернатива: КолибриОС напрямую ───────────────
menuentry 'КолибриОС {KOLIBRI_VERSION} (чистая)' {{
    set root=(hd0,msdos1)
    multiboot /KOLIBRI/kernel.mnt /KOLIBRI/kernel.mnt
    module   /KOLIBRI/kolibri.img
    boot
}}

# ── Fallback: запуск ARGOS на Linux (если доступен) ─
menuentry 'ARGOS OS v{version} (Linux mode)' {{
    set root=(hd0,msdos1)
    linux   /boot/vmlinuz root=/dev/sda1 quiet splash argos_autostart=1
    initrd  /boot/initrd.img
}}

# ── Системные утилиты ──────────────────────────────
menuentry 'Memtest86+' {{
    linux16 /boot/memtest
}}

menuentry 'Выключить компьютер' {{
    halt
}}
"""

    # ── Autorun скрипт ARGOS для КолибриОС ───────────────────────────────
    def _autorun_kolibri(self, version: str = ARGOS_VERSION) -> str:
        """KolibriOS autorun.bat — запускает ARGOS Python после загрузки."""
        return f"""; ARGOS OS v{version} autorun for KolibriOS
; Размещается в /KOLIBRI/ или в корне флешки как AUTORUN.BAT

; Запуск Python (KolibriOS порт)
run /sys/python3/python3.exe /ARGOS/argos_kolibri.py

; Если Python не запустился — показать статус
; run /sys/notepad /ARGOS/README.txt
"""

    # ── README для КолибриОС ─────────────────────────────────────────────
    def _readme_kolibri(self, version: str = ARGOS_VERSION) -> str:
        return f"""=== ARGOS OS v{version} on КолибриОС ===

ЗАПУСК:
  1. Загрузи образ с USB или DVD
  2. В меню GRUB выбери "ARGOS OS (КолибриОС)"
  3. После загрузки КолибриОС запустится ARGOS автоматически

ЕСЛИ ARGOS НЕ ЗАПУСТИЛСЯ:
  В КолибриОС открой файловый менеджер → /ARGOS/argos_kolibri.py
  Кликни правой кнопкой → "Открыть с помощью Python"

TELEGRAM BOT:
  Укажи TELEGRAM_BOT_TOKEN в файле /ARGOS/.env

ТРЕБОВАНИЯ:
  ОЗУ: минимум 32 МБ (рекомендуется 64+ МБ)
  CPU: x86 / x86_64
  Нет интернета: ARGOS работает локально без сети

ЗАГРУЗКА КОЛИБРИОС:
  {KOLIBRI_DOWNLOAD_URLS['iso']}

ПОДДЕРЖКА:
  КолибриОС: {KOLIBRI_DOWNLOAD_URLS['github']}
  ARGOS:     https://github.com/argos-os/argos
"""

    # ── Stripped ARGOS launcher для КолибриОС ─────────────────────────────
    def _argos_kolibri_launcher(self, version: str = ARGOS_VERSION) -> str:
        """
        Минимальный лаунчер ARGOS для KolibriOS Python.
        KolibriOS Python не поддерживает asyncio/serial/psutil.
        """
        return f'''#!/usr/bin/env python3
"""
ARGOS OS v{version} — KolibriOS edition
Stripped launcher for KolibriOS Python environment.
"""

import os
import sys
import json

ARGOS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ARGOS_DIR)

print("=" * 50)
print(f"  ARGOS OS v{version} on КолибриОС")
print("=" * 50)
print()

# ── Загружаем .env если есть ──────────────────────────
env_path = os.path.join(ARGOS_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

# ── Пробуем загрузить ARGOS Core ──────────────────────
try:
    from src.core import ArgosCore
    print("[ARGOS] Загрузка ядра...")
    core = ArgosCore(
        skip_optional=True,   # пропустить тяжёлые модули
        no_serial=True,       # нет USB serial в КолибриОС
        no_gpio=True,         # нет GPIO
        no_audio=True,        # нет аудио в базовом КолибриОС
    )
    print("[ARGOS] Ядро загружено!")
except ImportError as e:
    print(f"[ARGOS] Полное ядро недоступно: {{e}}")
    print("[ARGOS] Запуск в автономном режиме...")
    core = None

# ── Простой REPL если нет ядра ─────────────────────────
def simple_repl():
    """Простой диалоговый интерфейс для КолибриОС."""
    print()
    print("ARGOS готов. Введи запрос или 'выход':")
    print()
    while True:
        try:
            user_input = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() in ("выход", "exit", "quit"):
            break
        if core:
            try:
                result = core.process(user_input)
                answer = result.get("answer", "") if isinstance(result, dict) else str(result)
                print(f"ARGOS: {{answer}}")
            except Exception as ex:
                print(f"[Ошибка]: {{ex}}")
        else:
            # Автономные ответы без ядра
            _t = user_input.lower()
            if "статус" in _t or "версия" in _t:
                print(f"ARGOS: Версия {version} | Платформа: КолибриОС | Режим: автономный")
            elif "помощь" in _t or "help" in _t:
                print("ARGOS: Доступные команды: статус, версия, выход")
            else:
                print(f"ARGOS: [автономный режим] Получено: {{user_input}}")
        print()

if __name__ == "__main__":
    simple_repl()
'''

    # ── Сборка ZIP-образа для USB/CD ─────────────────────────────────────
    def build_zip(self, version: str = ARGOS_VERSION,
                  include_grub: bool = True) -> str:
        """
        Собирает ZIP-образ ARGOS on КолибриОС.

        Структура:
          argos-kolibri-v{version}/
            ARGOS/                    — stripped ARGOS Python код
              argos_kolibri.py        — лаунчер для КолибриОС Python
              src/core.py ...         — основные модули
              .env.example
            KOLIBRI/                  — инструкции + заглушки
              README_KOLIBRI.txt      — инструкция по получению КолибриОС
              autorun.bat             — автозапуск ARGOS
            BOOT/
              grub.cfg                — GRUB2 с меню КолибриОС
              README_BOOT.txt
            UNIVERSAL/                — режим без КолибриОС (просто Python)
              launch.sh
              launch.bat
        """
        stamp = int(time.time())
        out_name = f"argos-kolibri-v{version}.zip"
        out_path = self.output_dir / out_name
        prefix   = f"argos-kolibri-v{version}"

        # Файлы, которые включаем в stripped профиль
        _kolibri_exclude = {
            "__pycache__", ".git", "venv", ".venv", "node_modules",
            ".buildozer", "build", "builds", "dist", "bin",
            "releases", "logs", ".pytest_cache", ".mypy_cache",
        }
        _kolibri_exclude_files = {".env", "master.key"}

        file_count = 0
        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                root = self.root

                # ── ARGOS/  — исходный код ──────────────────────────────
                for item in sorted(root.rglob("*")):
                    if not item.is_file():
                        continue
                    rel = item.relative_to(root)
                    parts = rel.parts
                    # Пропускаем исключённые директории
                    if any(p in _kolibri_exclude for p in parts):
                        continue
                    if parts[-1] in _kolibri_exclude_files:
                        continue
                    if parts[-1].startswith(".") and parts[-1] not in {".env.example", ".gitignore"}:
                        continue
                    if rel.suffix.lower() in {".pyc", ".pyo", ".db", ".log", ".tmp", ".exe", ".dll"}:
                        continue
                    zf.write(item, f"{prefix}/ARGOS/{rel.as_posix()}")
                    file_count += 1

                # ── Лаунчер КолибриОС ──────────────────────────────────
                zf.writestr(
                    f"{prefix}/ARGOS/argos_kolibri.py",
                    self._argos_kolibri_launcher(version)
                )

                # ── KOLIBRI/  — заглушки и инструкции ──────────────────
                zf.writestr(
                    f"{prefix}/KOLIBRI/README_KOLIBRI.txt",
                    self._readme_kolibri(version)
                )
                zf.writestr(
                    f"{prefix}/KOLIBRI/autorun.bat",
                    self._autorun_kolibri(version)
                )
                # Инструкция как получить kernel.mnt
                zf.writestr(
                    f"{prefix}/KOLIBRI/GET_KOLIBRI.txt",
                    (
                        "Чтобы получить КолибриОС kernel.mnt:\n\n"
                        f"1. Скачай ISO: {KOLIBRI_DOWNLOAD_URLS['iso']}\n"
                        "2. Смонтируй ISO или распакуй\n"
                        "3. Скопируй kernel.mnt и kolibri.img в эту папку (/KOLIBRI/)\n"
                        "4. Запиши весь образ на USB через Rufus или dd\n\n"
                        "Без kernel.mnt ARGOS работает в Linux/Windows режиме.\n"
                    )
                )

                # ── BOOT/ ────────────────────────────────────────────────
                if include_grub:
                    zf.writestr(
                        f"{prefix}/BOOT/grub.cfg",
                        self._grub_cfg_kolibri(version)
                    )
                zf.writestr(
                    f"{prefix}/BOOT/README_BOOT.txt",
                    self._readme_kolibri(version)
                )

                # ── UNIVERSAL/ — запуск без КолибриОС (стандартный режим) ─
                zf.writestr(
                    f"{prefix}/UNIVERSAL/launch.sh",
                    "#!/usr/bin/env bash\n"
                    'cd "$(dirname "$0")/../ARGOS"\n'
                    "if [ ! -d venv ]; then python3 -m venv venv; fi\n"
                    "source venv/bin/activate\n"
                    "pip install -q -r requirements.txt\n"
                    "python main.py\n"
                )
                zf.writestr(
                    f"{prefix}/UNIVERSAL/launch.bat",
                    "@echo off\n"
                    'cd /d "%~dp0..\\ARGOS"\n'
                    "if not exist venv python -m venv venv\n"
                    "call venv\\Scripts\\activate.bat\n"
                    "pip install -q -r requirements.txt\n"
                    "python main.py\n"
                )

                # ── device_profile.json ──────────────────────────────────
                profile = ARGOS_PROFILES["kolibri"]
                zf.writestr(
                    f"{prefix}/device_profile.json",
                    json.dumps({
                        "argos_version": version,
                        "kolibri_version": KOLIBRI_VERSION,
                        "profile": "kolibri",
                        "label": profile["label"],
                        "features": profile["features"],
                        "no_features": profile["no_features"],
                        "built_at": stamp,
                        "platforms": ["x86", "x86_64"],
                    }, indent=2, ensure_ascii=False)
                )

            size_mb = out_path.stat().st_size / 1024 / 1024
            log.info("Kolibri образ создан: %s (%.1f МБ)", out_name, size_mb)
            return (
                f"✅ ARGOS on КолибриОС образ создан:\n"
                f"  📦 {out_path}  ({size_mb:.1f} МБ, {file_count} исх. файлов)\n\n"
                f"🐦 Состав образа:\n"
                f"  /ARGOS/     — ARGOS Python код (stripped профиль)\n"
                f"  /KOLIBRI/   — инструкции по получению КолибриОС\n"
                f"  /BOOT/      — GRUB2 конфиг с меню КолибриОС\n"
                f"  /UNIVERSAL/ — запуск без КолибриОС (Linux/Windows/Mac)\n\n"
                f"🚀 Следующий шаг:\n"
                f"  1. Скачай КолибриОС: {KOLIBRI_DOWNLOAD_URLS['iso']}\n"
                f"  2. Распакуй kernel.mnt в /KOLIBRI/\n"
                f"  3. Запиши на USB: Rufus (Windows) или dd (Linux)\n"
                f"  4. Загрузись с USB → меню GRUB → ARGOS on КолибриОС\n\n"
                f"  Или без КолибриОС: распакуй → launch.sh / launch.bat"
            )
        except Exception as e:
            log.error("KolibriOSBuilder.build_zip: %s", e)
            return f"❌ Ошибка сборки КолибриОС образа: {e}"

    # ── ISO-образ (если есть grub-mkrescue) ──────────────────────────────
    def build_iso(self, version: str = ARGOS_VERSION) -> str:
        """Создаёт загрузочный ISO с GRUB2 + КолибриОС + ARGOS."""
        tools = self.check_tools()
        if not tools["can_iso"]:
            return (
                "⚠️ ISO-инструменты не найдены. Создаю ZIP вместо ISO...\n" +
                self.build_zip(version)
            )
        mkrescue = shutil.which("grub-mkrescue") or shutil.which("grub2-mkrescue")
        xorriso  = shutil.which("xorriso")

        out_path = self.output_dir / f"argos-kolibri-v{version}.iso"
        log.info("Сборка ISO КолибриОС + ARGOS...")

        with tempfile.TemporaryDirectory() as td:
            iso_root  = Path(td) / "iso"
            boot_dir  = iso_root / "boot" / "grub"
            argos_dir = iso_root / "ARGOS"
            kol_dir   = iso_root / "KOLIBRI"

            for d in [boot_dir, argos_dir, kol_dir]:
                d.mkdir(parents=True, exist_ok=True)

            # Копируем ARGOS в /ARGOS/
            _exc = {"__pycache__", ".git", "venv", ".venv", "build", "builds",
                    "releases", "logs", "node_modules", ".buildozer"}
            for item in self.root.rglob("*"):
                if not item.is_file():
                    continue
                rel = item.relative_to(self.root)
                if any(p in _exc for p in rel.parts):
                    continue
                dst = argos_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)

            # Лаунчер КолибриОС
            (argos_dir / "argos_kolibri.py").write_text(
                self._argos_kolibri_launcher(version), encoding="utf-8"
            )

            # GRUB конфиг
            (boot_dir / "grub.cfg").write_text(
                self._grub_cfg_kolibri(version), encoding="utf-8"
            )

            # KolibriOS файлы (если переданы)
            if self.kolibri_iso and Path(self.kolibri_iso).exists():
                # Пробуем смонтировать/распаковать
                try:
                    r = subprocess.run(
                        ["7z", "e", self.kolibri_iso, "-o", str(kol_dir),
                         "kernel.mnt", "kolibri.img", "-y"],
                        capture_output=True, text=True, timeout=60
                    )
                    if r.returncode == 0:
                        log.info("КолибриОС файлы извлечены из ISO")
                except Exception as e:
                    log.warning("Не удалось извлечь КолибриОС: %s", e)
            else:
                (kol_dir / "README.txt").write_text(
                    self._readme_kolibri(version), encoding="utf-8"
                )

            # Собираем ISO
            if mkrescue:
                try:
                    r = subprocess.run(
                        [mkrescue, "-o", str(out_path), str(iso_root)],
                        capture_output=True, text=True, timeout=300
                    )
                    if r.returncode == 0:
                        size_mb = out_path.stat().st_size / 1024 / 1024
                        return (
                            f"✅ ARGOS on КолибриОС ISO создан:\n"
                            f"  💿 {out_path}  ({size_mb:.1f} МБ)\n\n"
                            f"  Запись на USB (Linux):\n"
                            f"    sudo dd if={out_path} of=/dev/sdX bs=4M status=progress\n\n"
                            f"  Запись на USB (Windows): Rufus → rufus.ie\n\n"
                            f"  ⚠️ kernel.mnt не включён — скачай КолибриОС отдельно:\n"
                            f"    {KOLIBRI_DOWNLOAD_URLS['iso']}"
                            if not (self.kolibri_iso) else ""
                        )
                    return f"❌ grub-mkrescue: {r.stderr[:400]}"
                except Exception as e:
                    return f"❌ grub-mkrescue: {e}"

            if xorriso:
                try:
                    r = subprocess.run(
                        [xorriso, "-as", "mkisofs", "-R", "-J",
                         "-o", str(out_path), str(iso_root)],
                        capture_output=True, text=True, timeout=300
                    )
                    if r.returncode == 0:
                        size_mb = out_path.stat().st_size / 1024 / 1024
                        return f"✅ ISO (xorriso): {out_path} ({size_mb:.1f} МБ)"
                    return f"❌ xorriso: {r.stderr[:400]}"
                except Exception as e:
                    return f"❌ xorriso: {e}"

        return "❌ Не удалось создать ISO"


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-PLATFORM INSTALLER
# ══════════════════════════════════════════════════════════════════════════════

class MultiPlatformInstaller:
    """
    Собирает ARGOS OS образы для всех целевых платформ.

    Поддерживаемые платформы и методы:
    ┌─────────────┬──────────────────────────────────────────┬──────────┐
    │ Платформа   │ Метод установки                          │ Файл     │
    ├─────────────┼──────────────────────────────────────────┼──────────┤
    │ PC (x86_64) │ KolibriOS ISO → USB → загрузка с USB     │ .iso     │
    │ PC (x86_64) │ ZIP → распакуй → launch.sh / launch.bat  │ .zip     │
    │ Android     │ APK → установи → запусти                 │ .apk     │
    │ Android     │ ADB sideload / Termux                    │ .zip     │
    │ macOS       │ .app → Applications → Launch             │ .zip     │
    │ macOS       │ brew install / pip + main.py             │ .zip     │
    └─────────────┴──────────────────────────────────────────┴──────────┘

    Ограничения:
    - KolibriOS работает только на x86/x86_64 (не ARM, не Android, не Mac)
    - Android APK требует buildozer + JDK (может занять 30-60 мин)
    - macOS .app требует PyInstaller + macOS для подписи
    """

    def __init__(self, output_dir: str = "releases") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._kolibri = KolibriOSBuilder(output_dir)

    def check_platform_tools(self) -> dict:
        """Проверяет доступность инструментов для каждой платформы."""
        return {
            "pc_iso": {
                "available": bool(
                    shutil.which("grub-mkrescue") or
                    shutil.which("grub2-mkrescue") or
                    shutil.which("xorriso")
                ),
                "method": "grub-mkrescue / xorriso",
                "install": "sudo apt install grub2-common xorriso",
            },
            "pc_zip": {
                "available": True,
                "method": "Python zipfile (встроен)",
                "install": "—",
            },
            "android_apk": {
                "available": bool(shutil.which("buildozer")),
                "method": "Buildozer + Kivy",
                "install": "pip install buildozer cython --break-system-packages",
            },
            "android_zip": {
                "available": True,
                "method": "ZIP для Termux",
                "install": "—",
            },
            "mac_zip": {
                "available": True,
                "method": "ZIP + launch.sh",
                "install": "—",
            },
            "mac_app": {
                "available": bool(shutil.which("pyinstaller")),
                "method": "PyInstaller .app",
                "install": "pip install pyinstaller --break-system-packages",
            },
        }

    def status_report(self) -> str:
        """Отчёт о готовности сборки для каждой платформы."""
        tools = self.check_platform_tools()
        lines = [
            "🌍 ARGOS Multi-Platform Installer — статус:",
            "",
            f"  Версия ARGOS: {ARGOS_VERSION}",
            "",
            "  ┌─────────────────┬──────────┬──────────────────────────────────┐",
            "  │ Платформа       │ Готово   │ Метод / Установка                │",
            "  ├─────────────────┼──────────┼──────────────────────────────────┤",
        ]
        rows = [
            ("PC ISO (КолибриОС)", "pc_iso"),
            ("PC ZIP (любой)    ", "pc_zip"),
            ("Android APK       ", "android_apk"),
            ("Android ZIP/Termux", "android_zip"),
            ("macOS ZIP         ", "mac_zip"),
            ("macOS .app        ", "mac_app"),
        ]
        for label, key in rows:
            t = tools[key]
            icon = "✅" if t["available"] else "○ "
            method = t["method"][:30]
            lines.append(f"  │ {label} │ {icon}      │ {method:32s} │")
        lines.extend([
            "  └─────────────────┴──────────┴──────────────────────────────────┘",
            "",
            "  Команды:",
            "    создай образ для pc               — ZIP для PC/ноутбука",
            "    создай образ для android          — ZIP + APK инструкция",
            "    создай образ для mac              — ZIP для macOS",
            "    мультиплатформенный образ         — все платформы сразу",
            "    создай образ колибри              — КолибриОС + ARGOS",
            "",
            "  ⚡ КолибриОС только для x86/x86_64:",
            f"    Скачай: {KOLIBRI_DOWNLOAD_URLS['iso']}",
        ])
        return "\n".join(lines)

    # ── Сборка для конкретной платформы ──────────────────────────────────
    def build_for(self, target: str, version: str = ARGOS_VERSION) -> str:
        """Собирает образ для целевой платформы."""
        t = target.lower().strip()

        if t in ("pc", "x86", "x86_64", "linux", "windows", "колибри", "kolibri"):
            return self._build_pc(version, kolibri=(t in ("колибри", "kolibri")))
        elif t in ("android", "apk", "андроид"):
            return self._build_android(version)
        elif t in ("mac", "macos", "darwin", "мак", "макос"):
            return self._build_mac(version)
        else:
            return (
                f"❌ Неизвестная платформа: '{target}'\n"
                "  Доступны: pc | android | mac | колибри"
            )

    def build_all(self, version: str = ARGOS_VERSION) -> str:
        """Собирает образы для всех платформ."""
        results = []
        log.info("MultiPlatformInstaller: сборка для всех платформ...")

        for target in ("pc", "android", "mac"):
            log.info("Сборка для: %s", target)
            r = self.build_for(target, version)
            results.append(f"{'─'*50}\n{r}")

        return "\n".join(results)

    def _build_pc(self, version: str, kolibri: bool = False) -> str:
        """Образ для PC: КолибриОС ZIP + опционально ISO."""
        # Всегда создаём ZIP (надёжнее)
        zip_result = self._kolibri.build_zip(version)

        # Пробуем ISO если есть инструменты
        tools = self._kolibri.check_tools()
        iso_result = ""
        if tools["can_iso"] and kolibri:
            iso_result = "\n\n" + self._kolibri.build_iso(version)

        return (
            f"🖥️  PC образ (x86_64 + КолибриОС):\n\n"
            f"{zip_result}{iso_result}"
        )

    def _build_android(self, version: str) -> str:
        """Образ для Android: ZIP для Termux + инструкция по APK."""
        # ZIP для Termux (всегда доступно)
        out_name = f"argos-v{version}-android.zip"
        out_path = self.output_dir / out_name
        prefix   = f"argos-v{version}"

        _exc = {"__pycache__", ".git", "venv", ".venv", "build", "builds",
                "releases", "dist", ".buildozer", "node_modules", "logs"}
        file_count = 0

        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                root = Path(".").resolve()
                for item in sorted(root.rglob("*")):
                    if not item.is_file():
                        continue
                    rel = item.relative_to(root)
                    if any(p in _exc for p in rel.parts):
                        continue
                    if rel.suffix.lower() in {".pyc", ".pyo", ".exe", ".dll", ".so"}:
                        continue
                    zf.write(item, f"{prefix}/{rel.as_posix()}")
                    file_count += 1

                # Termux launch script
                zf.writestr(f"{prefix}/launch_termux.sh",
                    "#!/data/data/com.termux/files/usr/bin/bash\n"
                    "# Запуск ARGOS в Termux на Android\n\n"
                    "pkg update -y\n"
                    "pkg install python python-pip -y\n"
                    f"cd ~/storage/downloads/{prefix}\n"
                    "pip install -r requirements.txt\n"
                    "python main.py\n"
                )
                zf.writestr(f"{prefix}/INSTALL_ANDROID.txt",
                    f"=== ARGOS OS v{version} — Android ===\n\n"
                    "МЕТОД 1: Termux (рекомендуется, не требует root):\n"
                    "  1. Установи Termux из F-Droid: https://f-droid.org\n"
                    "  2. Скопируй этот ZIP в Downloads на телефоне\n"
                    "  3. В Termux:\n"
                    f"     cd ~/storage/downloads && unzip {out_name}\n"
                    "     bash launch_termux.sh\n\n"
                    "МЕТОД 2: APK (Kivy, требует сборки на ПК):\n"
                    "  1. На ПК с Linux: pip install buildozer\n"
                    "  2. cd <путь к ARGOS>\n"
                    "  3. buildozer android debug\n"
                    "  4. Установи bin/*.apk на телефон\n\n"
                    "МЕТОД 3: ADB sideload (требует кастомного recovery):\n"
                    "  adb sideload argos-android-recovery.zip\n"
                )

            size_mb = out_path.stat().st_size / 1024 / 1024
            buildozer_status = "✅ доступен" if shutil.which("buildozer") else "○ не установлен (pip install buildozer)"

            return (
                f"📱 Android образ:\n"
                f"  📦 {out_path}  ({size_mb:.1f} МБ, {file_count} файлов)\n\n"
                f"  Termux (рекомендуется, без root):\n"
                f"    1. Скопируй ZIP на телефон → Downloads\n"
                f"    2. В Termux: unzip {out_name} && bash launch_termux.sh\n\n"
                f"  APK сборка: buildozer {buildozer_status}\n"
                f"    buildozer android debug  (займёт 30-60 мин)\n\n"
                f"  Подробности: {out_path}/INSTALL_ANDROID.txt"
            )
        except Exception as e:
            return f"❌ Android образ: {e}"

    def _build_mac(self, version: str) -> str:
        """Образ для macOS: ZIP + launch.sh + инструкция по .app."""
        out_name = f"argos-v{version}-macos.zip"
        out_path = self.output_dir / out_name
        prefix   = f"argos-v{version}"

        _exc = {"__pycache__", ".git", "venv", ".venv", "build", "builds",
                "releases", "dist", ".buildozer", "node_modules", "logs"}
        file_count = 0

        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                root = Path(".").resolve()
                for item in sorted(root.rglob("*")):
                    if not item.is_file():
                        continue
                    rel = item.relative_to(root)
                    if any(p in _exc for p in rel.parts):
                        continue
                    if rel.suffix.lower() in {".pyc", ".pyo", ".exe", ".dll"}:
                        continue
                    zf.write(item, f"{prefix}/{rel.as_posix()}")
                    file_count += 1

                zf.writestr(f"{prefix}/launch.sh",
                    "#!/usr/bin/env bash\n"
                    "# ARGOS OS — macOS launcher\n"
                    'cd "$(dirname "$0")"\n'
                    "if ! command -v python3 &>/dev/null; then\n"
                    "  echo 'Python3 не найден. Установи: brew install python3'\n"
                    "  exit 1\n"
                    "fi\n"
                    "if [ ! -d venv ]; then python3 -m venv venv; fi\n"
                    "source venv/bin/activate\n"
                    "pip install -q -r requirements.txt\n"
                    "python main.py\n"
                )
                zf.writestr(f"{prefix}/INSTALL_MAC.txt",
                    f"=== ARGOS OS v{version} — macOS ===\n\n"
                    "МЕТОД 1: ZIP (рекомендуется):\n"
                    f"  1. Распакуй {out_name}\n"
                    f"  2. cd {prefix}\n"
                    "  3. bash launch.sh\n\n"
                    "МЕТОД 2: .app через PyInstaller:\n"
                    "  pip install pyinstaller\n"
                    "  pyinstaller --windowed --onedir --name ARGOS main.py\n"
                    "  Скопируй dist/ARGOS.app в /Applications\n\n"
                    "МЕТОД 3: Homebrew + pip:\n"
                    "  brew install python3\n"
                    "  pip3 install -r requirements.txt\n"
                    "  python3 main.py\n\n"
                    "Требования: macOS 11+ (Big Sur), Python 3.10+, ARM или x86_64\n"
                )

            size_mb = out_path.stat().st_size / 1024 / 1024
            pyinstaller_status = "✅ доступен" if shutil.which("pyinstaller") else "○ pip install pyinstaller"

            return (
                f"🍎 macOS образ:\n"
                f"  📦 {out_path}  ({size_mb:.1f} МБ, {file_count} файлов)\n\n"
                f"  Запуск: распакуй ZIP → bash launch.sh\n\n"
                f"  .app сборка: PyInstaller {pyinstaller_status}\n"
                f"    pyinstaller --windowed --name ARGOS main.py\n\n"
                f"  Подробности: {out_path}/INSTALL_MAC.txt"
            )
        except Exception as e:
            return f"❌ macOS образ: {e}"

    # ── Установка ARGOS на текущую систему ───────────────────────────────
    def install_local(self) -> str:
        """Устанавливает ARGOS на текущую систему (PC/Mac)."""
        sys_name = platform.system()
        lines = [
            f"📥 Локальная установка ARGOS OS — {sys_name}:",
            "",
        ]
        if sys_name in ("Linux", "Darwin"):
            lines += [
                "  1. python3 -m venv venv",
                "  2. source venv/bin/activate",
                "  3. pip install -r requirements.txt",
                "  4. python main.py",
            ]
        elif sys_name == "Windows":
            lines += [
                "  1. python -m venv venv",
                "  2. venv\\Scripts\\activate",
                "  3. pip install -r requirements.txt",
                "  4. python main.py",
            ]
        lines += [
            "",
            "  Или используй скрипты установки:",
            "    launch.sh (Linux/Mac) / launch.bat (Windows)",
        ]
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS (для core.py dispatch)
# ══════════════════════════════════════════════════════════════════════════════

def build_kolibri_image(output_dir: str = "releases") -> str:
    """Точка входа: создаёт ZIP образ ARGOS on КолибриОС."""
    builder = KolibriOSBuilder(output_dir)
    return builder.build_zip()


def build_multiplatform(output_dir: str = "releases", target: str = "all") -> str:
    """Точка входа: мультиплатформенная сборка."""
    installer = MultiPlatformInstaller(output_dir)
    if target == "all":
        return installer.build_all()
    return installer.build_for(target)


def kolibri_status(output_dir: str = "releases") -> str:
    """Статус КолибриОС инструментов и возможностей."""
    k = KolibriOSBuilder(output_dir)
    m = MultiPlatformInstaller(output_dir)
    return k.status() + "\n\n" + m.status_report()
