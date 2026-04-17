"""src/platform_admin.py — Платформенный администратор ARGOS"""
from __future__ import annotations
import os, platform, shutil, subprocess, sys
from typing import Optional

__all__ = [
    "PlatformAdmin", "LinuxAdmin", "WindowsAdmin", "AndroidAdmin",
    "_run", "_cmd_available", "_OS", "_IS_ANDROID",
]

_OS = platform.system()
_IS_ANDROID = os.path.exists("/system/build.prop")


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + r.stderr).strip()
        return out if out else "✅ OK"
    except FileNotFoundError:
        return f"❌ Команда не найдена: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"⏱ Таймаут {timeout}с: {' '.join(cmd)}"
    except Exception as e:
        return f"❌ {e}"


def _cmd_available(cmd: str) -> bool:
    return shutil.which(cmd) is not None


class AndroidAdmin:
    def adb_devices(self) -> str:
        if not _cmd_available("adb"):
            return "❌ ADB не найден"
        return _run(["adb", "devices"])

    def app_list(self, flags: str = "-3") -> str:
        return _run(["adb", "shell", "pm", "list", "packages", flags])

    def battery_info(self) -> str:
        return _run(["adb", "shell", "dumpsys", "battery"])

    def storage_info(self) -> str:
        return _run(["adb", "shell", "df", "-h"])

    def sys_info(self) -> str:
        model   = _run(["adb", "shell", "getprop", "ro.product.model"])
        version = _run(["adb", "shell", "getprop", "ro.build.version.release"])
        return f"📱 ANDROID INFO\n  Модель: {model}\n  Android: {version}"

    def termux_install(self, pkg: str) -> str:
        return _run(["pkg", "install", "-y", pkg])

    def termux_update(self) -> str:
        return _run(["pkg", "update", "-y"])


class LinuxAdmin:
    def disk_usage(self) -> str:
        return _run(["df", "-h"])

    def user_info(self) -> str:
        name = _run(["whoami"])
        return f"👤 Пользователь: {name}"

    def network_info(self) -> str:
        if _cmd_available("ip"):
            return _run(["ip", "a"])
        return _run(["ifconfig"])

    def pkg_search(self, pkg: str) -> str:
        if _cmd_available("apt-cache"):
            return _run(["apt-cache", "search", pkg])
        return f"❌ apt-cache недоступен"

    def top_processes(self, n: int = 10) -> str:
        return _run(["ps", "aux", "--sort=-%cpu"])

    def sys_info(self) -> str:
        uname = _run(["uname", "-a"])
        return f"🐧 Linux: {uname}"


class WindowsAdmin:
    def sys_info(self) -> str:
        return _run(["systeminfo"])

    def list_processes(self) -> str:
        return _run(["tasklist"])


class PlatformAdmin:
    def __init__(self, core=None) -> None:
        self._core = core
        self.os      = _OS
        self.android = AndroidAdmin()
        self.linux   = LinuxAdmin()
        self.windows = WindowsAdmin()

    def status(self) -> str:
        android_flag = " (Android)" if _IS_ANDROID else ""
        return (
            f"🖥️ ПЛАТФОРМЕННЫЙ АДМИНИСТРАТОР\n"
            f"  ОС: {self.os}{android_flag}\n"
            f"  ADB: {'✅' if _cmd_available('adb') else '❌'}\n"
            f"  Python: {sys.version.split()[0]}"
        )

    def handle_command(self, text: str) -> str:  # noqa: C901
        t = text.strip().lower()

        if "платформа статус" in t:
            return self.status()

        if "adb устройства" in t:
            return self.android.adb_devices()

        if "android батарея" in t:
            return self.android.battery_info()

        if "android инфо" in t:
            return self.android.sys_info()

        if "android приложения" in t:
            return self.android.app_list()

        if "pkg обновить" in t:
            return self.android.termux_update()

        if _OS == "Linux" and not _IS_ANDROID:
            if "диск linux" in t:
                return self.linux.disk_usage()
            if "пользователь linux" in t:
                return self.linux.user_info()
            if "процессы linux" in t:
                return self.linux.top_processes()

        # Команда tail для просмотра логов
        if t.startswith("tail ") or t == "tail":
            count = 50
            parts = t.split()
            if len(parts) > 1 and parts[1].isdigit():
                count = max(1, min(int(parts[1]), 200))
            with open("logs/argos_debug.log", "r", encoding="utf-8", errors="ignore") as f:
                return "".join(f.readlines()[-count:]) or "Лог пуст"

        return f"❓ Команда не распознана: {text}"
