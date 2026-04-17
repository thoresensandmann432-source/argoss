"""src/device_scanner.py — Автономный сканер устройств ARGOS"""
from __future__ import annotations
import json, os, platform, socket, zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["DeviceScanner", "AdaptiveImageBuilder", "PROFILES", "_GLOBAL_EXCLUDE"]

PROFILES = {
    "micro":    {"min_ram_mb": 0,    "max_ram_mb": 128,   "label": "Micro (MCU/ESP)"},
    "lite":     {"min_ram_mb": 128,  "max_ram_mb": 512,   "label": "Lite (RPi Zero)"},
    "standard": {"min_ram_mb": 512,  "max_ram_mb": 4096,  "label": "Standard (RPi4/Android)"},
    "full":     {"min_ram_mb": 4096, "max_ram_mb": 16384, "label": "Full (Desktop/Laptop)"},
    "server":   {"min_ram_mb": 16384,"max_ram_mb": 999999,"label": "Server"},
}

_GLOBAL_EXCLUDE = {".git", "__pycache__", ".venv", "venv", ".buildozer", "data", "logs", "dist", "build"}


class DeviceScanner:
    def scan(self) -> dict:
        return {
            "os":          self._scan_os(),
            "cpu":         self._scan_cpu(),
            "ram":         self._scan_ram(),
            "storage":     self._scan_storage(),
            "network":     self._scan_network(),
            "peripherals": self._scan_peripherals(),
            "tools":       self._scan_tools(),
            "packages":    self._scan_packages(),
            "firmware":    self._scan_firmware_type(),
            "profile":     self._select_profile(self._scan_ram()),
        }

    def report(self, info: dict | None = None) -> str:
        if info is None: info = self.scan()
        profile = info.get("profile", {})
        os_info = info.get("os", {})
        cpu     = info.get("cpu", {})
        ram     = info.get("ram", {})
        return (
            f"🔍 ARGOS DEVICE SCAN\n"
            f"  ОС      : {os_info.get('system','?')} {os_info.get('release','')}\n"
            f"  CPU     : {cpu.get('arch','?')} x{cpu.get('cores',1)}\n"
            f"  RAM     : {ram.get('total_mb',0)} МБ\n"
            f"  ПРОФИЛЬ : {profile.get('key','?').upper()} — {profile.get('label','')}\n"
        )

    # ── Сканеры ───────────────────────────────────────────────────────────
    def _scan_os(self) -> dict:
        return {
            "system":    platform.system() or "Linux",
            "release":   platform.release(),
            "version":   platform.version(),
            "python":    platform.python_version(),
            "is_android": os.path.exists("/system/build.prop"),
            "hostname":  socket.gethostname(),
        }

    def _scan_cpu(self) -> dict:
        arch = platform.machine()
        try:
            import psutil
            cores = psutil.cpu_count(logical=False) or 1
            freq  = (psutil.cpu_freq().current if psutil.cpu_freq() else 0)
        except Exception:
            cores, freq = os.cpu_count() or 1, 0
        return {
            "arch":    arch, "cores": cores, "model": platform.processor() or arch,
            "freq_mhz": int(freq), "is_arm": arch.startswith(("arm","aarch")),
            "is_x86": arch.startswith(("x86","AMD64","i386","i686")),
            "is_riscv": "riscv" in arch.lower(),
        }

    def _scan_ram(self) -> dict:
        try:
            import psutil
            m = psutil.virtual_memory()
            return {"total_mb": m.total//1024//1024, "available_mb": m.available//1024//1024}
        except Exception:
            return {"total_mb": 0, "available_mb": 0}

    def _scan_storage(self) -> list:
        try:
            import psutil
            return [{"mount": p.mountpoint, "total_gb": psutil.disk_usage(p.mountpoint).total//1024**3}
                    for p in psutil.disk_partitions() if p.fstype]
        except Exception:
            return []

    def _scan_network(self) -> dict:
        try:
            import psutil
            ifaces = list(psutil.net_if_addrs().keys())
        except Exception:
            ifaces = []
        return {
            "interfaces":    ifaces,
            "has_wifi":      any("wi" in i.lower() or "wlan" in i.lower() for i in ifaces),
            "has_ethernet":  any("eth" in i.lower() or "en" in i.lower() for i in ifaces),
            "has_bluetooth": any("bt" in i.lower() or "bluetooth" in i.lower() for i in ifaces),
            "internet":      self._check_internet(),
        }

    def _check_internet(self) -> bool:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return True
        except Exception:
            return False

    def _scan_peripherals(self) -> dict:
        gpu_name = ""
        try:
            import subprocess
            r = subprocess.run(["nvidia-smi","--query-gpu=name","--format=csv,noheader"],
                               capture_output=True, text=True, timeout=3)
            if r.returncode == 0: gpu_name = r.stdout.strip()
        except Exception:
            pass
        return {
            "serial_ports": [], "has_audio": False,
            "has_gpu": bool(gpu_name), "gpu_name": gpu_name,
            "has_display": "DISPLAY" in os.environ or platform.system() == "Windows",
            "has_gpio": os.path.exists("/sys/class/gpio"),
        }

    def _scan_tools(self) -> dict:
        import shutil
        return {t: bool(shutil.which(t)) for t in ["adb","fastboot","git","docker","ollama","python3"]}

    def _scan_packages(self) -> dict:
        result = {}
        for pkg in ["requests","psutil","fastapi","numpy","sklearn"]:
            try:
                __import__(pkg); result[pkg] = True
            except ImportError:
                result[pkg] = False
        return result

    def _scan_firmware_type(self) -> dict:
        is_efi = Path("/sys/firmware/efi").exists() or Path("C:/Windows/Boot/EFI").exists()
        return {"type": "UEFI" if is_efi else "BIOS", "is_efi": is_efi}

    def _select_profile(self, ram: dict) -> dict:
        total = ram.get("total_mb", 0)
        for key in ["server","full","standard","lite","micro"]:
            p = PROFILES[key]
            if total >= p["min_ram_mb"]:
                return {"key": key, "label": p["label"]}
        return {"key": "micro", "label": PROFILES["micro"]["label"]}


class AdaptiveImageBuilder:
    def __init__(self, output_dir: str = "builds") -> None:
        self._output_dir = Path(output_dir)
        self._scanner = DeviceScanner()

    def build_for_this_device(self, version: str = "2.2.0") -> str:
        info = self._scanner.scan()
        return self._build(info["profile"]["key"], info, version)

    def build_for_target(self, target: str, version: str = "2.2.0") -> str:
        if target == "windows":
            info = {"profile": {"key": "full", "label": "Full"}, "os": {"system": "Windows"}}
        elif target == "android":
            info = {"profile": {"key": "lite", "label": "Lite"}, "os": {"system": "Android"}}
        elif target in ("rpi", "raspberry"):
            info = {"profile": {"key": "standard", "label": "Standard"}, "os": {"system": "Linux"}}
        elif target in PROFILES:
            info = {"profile": {"key": target, "label": PROFILES[target]["label"]}, "os": {"system": "Linux"}}
        else:
            return f"❌ Неизвестная цель: {target}. Доступны: {', '.join(PROFILES.keys())} + windows/android/rpi"
        return self._build(target, info, version)

    def status(self) -> str:
        return f"🏗️ AdaptiveImageBuilder\n  Профили: {', '.join(PROFILES.keys())}\n  Выход: {self._output_dir}"

    def _build(self, profile_key: str, info: dict, version: str) -> str:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        zip_name = f"argos-{profile_key}-v{version}.zip"
        zip_path = self._output_dir / zip_name
        root = Path(".")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # device profile
            profile_data = {"profile": profile_key, "version": version,
                            "os": info.get("os", {}).get("system", "?"),
                            "info": info}
            zf.writestr(f"argos-{profile_key}/device_profile.json",
                        json.dumps(profile_data, indent=2, default=str))
            # requirements
            req = root / "requirements.txt"
            if req.exists():
                zf.write(req, f"argos-{profile_key}/requirements.txt")
            else:
                zf.writestr(f"argos-{profile_key}/requirements.txt", "requests\npsutil\n")
            # key source files
            for f in ["main.py", "genesis.py", ".env.example"]:
                fp = root / f
                if fp.exists():
                    zf.write(fp, f"argos-{profile_key}/{f}")
            # src/ excluding secrets
            for py in sorted(root.rglob("src/**/*.py")):
                rel = py.relative_to(root)
                if not any(p in rel.parts for p in _GLOBAL_EXCLUDE):
                    zf.write(py, f"argos-{profile_key}/{rel.as_posix()}")
        return f"✅ Образ собран: {zip_path}\n  Профиль: {profile_key} | Версия: {version}"
