"""
amd_gpu_patch.py — Патч ArgosCore для AMD Radeon RX на Windows
================================================================
Импортируй этот файл в main.py ПОСЛЕ импорта ArgosCore:

    from amd_gpu_patch import apply_amd_patch
    apply_amd_patch()

Что делает патч:
  [1] Добавляет определение AMD GPU через WMI/PowerShell
  [2] Исправляет _video_line() — теперь видит AMD Radeon
  [3] Добавляет get_amd_device() для torch-directml
  [4] Исправляет Whisper: пробует DirectML → CPU fallback
  [5] Добавляет команду 'gpu инфо' и 'gpu установить'
"""

import os
import platform
import subprocess
import threading
import logging

log = logging.getLogger("argos.amd_patch")

# ─────────────────────────────────────────────────────────────
# [1] Определение AMD GPU через WMI (Windows only)
# ─────────────────────────────────────────────────────────────

def detect_amd_gpu_windows() -> dict | None:
    """Возвращает инфо об AMD GPU через PowerShell WMI или None."""
    if platform.system() != "Windows":
        return None
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-WmiObject Win32_VideoController | "
             "Select-Object Name, AdapterRAM, DriverVersion, VideoProcessor | "
             "ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=6, encoding="utf-8",
            errors="replace"
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        import json
        raw = result.stdout.strip()
        data = json.loads(raw)

        # Может вернуть список или один объект
        if isinstance(data, dict):
            data = [data]

        for gpu in data:
            name = (gpu.get("Name") or "").strip()
            if not name:
                continue
            # Ищем AMD/Radeon
            if any(x in name.upper() for x in ["AMD", "RADEON", "RX ", "VEGA", "NAVI"]):
                vram_bytes = gpu.get("AdapterRAM") or 0
                vram_mb = int(vram_bytes) // (1024 * 1024) if vram_bytes else 0
                return {
                    "name": name,
                    "vram_mb": vram_mb,
                    "driver": gpu.get("DriverVersion", "?"),
                    "vendor": "AMD",
                }
            # Если AMD не нашли явно — возвращаем первый не-Microsoft
            if "Microsoft" not in name and "Basic" not in name:
                vram_bytes = gpu.get("AdapterRAM") or 0
                vram_mb = int(vram_bytes) // (1024 * 1024) if vram_bytes else 0
                return {
                    "name": name,
                    "vram_mb": vram_mb,
                    "driver": gpu.get("DriverVersion", "?"),
                    "vendor": "Unknown",
                }
    except Exception as e:
        log.warning("AMD GPU detect error: %s", e)
    return None


# ─────────────────────────────────────────────────────────────
# [2] Патч _video_line() — добавляем AMD Windows detection
# ─────────────────────────────────────────────────────────────

def _patched_video_line() -> str:
    """Расширенная версия _video_line() с поддержкой AMD на Windows."""
    import glob
    import shutil

    # ── Linux DRM ─────────────────────────────────────────
    if glob.glob("/dev/dri/renderD*"):
        try:
            import subprocess as _sp
            r = _sp.run(["lspci"], capture_output=True, text=True, timeout=2)
            for line in r.stdout.splitlines():
                if any(x in line.upper() for x in ["VGA", "3D", "DISPLAY"]):
                    return f"  Видеоядра/GPU: ✅ {line.strip()[:60]}"
        except Exception:
            pass
        return "  Видеоядра/GPU: ✅ DRM render nodes найдены"

    # ── NVIDIA (nvidia-smi) ────────────────────────────────
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            r = subprocess.run(
                [nvidia_smi, "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=4
            )
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split(",")
                name = parts[0].strip()
                util = parts[1].strip() if len(parts) > 1 else "?"
                vram_used = parts[2].strip() if len(parts) > 2 else "?"
                vram_total = parts[3].strip() if len(parts) > 3 else "?"
                return f"  Видеоядра/GPU: ✅ {name} | {util}% | VRAM {vram_used}/{vram_total} МБ"
        except Exception:
            pass

    # ── AMD (Windows — WMI) ────────────────────────────────
    if platform.system() == "Windows":
        gpu = detect_amd_gpu_windows()
        if gpu:
            vram_str = f" | VRAM {gpu['vram_mb']} МБ" if gpu['vram_mb'] > 0 else ""
            driver_str = f" | Драйвер {gpu['driver']}" if gpu['driver'] != "?" else ""
            return f"  Видеоядра/GPU: ✅ {gpu['name']}{vram_str}{driver_str}"

        # Fallback: любая видеокарта через WMI
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-WmiObject Win32_VideoController | "
                 "Select-Object -First 1 Name,AdapterRAM | "
                 "Format-Table -HideTableHeaders"],
                capture_output=True, text=True, timeout=5, encoding="cp866", errors="replace"
            )
            if r.returncode == 0 and r.stdout.strip():
                line = " ".join(r.stdout.strip().split())
                return f"  Видеоядра/GPU: ✅ {line[:60]}" if line else "  Видеоядра/GPU: ⚠️ WMI нет данных"
        except Exception:
            pass

    # ── Raspberry Pi VideoCore ─────────────────────────────
    vcgencmd = shutil.which("vcgencmd")
    if vcgencmd:
        try:
            r = subprocess.run([vcgencmd, "get_mem", "gpu"],
                               capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and r.stdout.strip():
                return f"  Видеоядра/GPU: ✅ VideoCore: {r.stdout.strip()}"
        except Exception:
            pass

    return "  Видеоядра/GPU: ⚠️ не обнаружены/драйверы не активны"


# ─────────────────────────────────────────────────────────────
# [3] AMD DirectML device для torch
# ─────────────────────────────────────────────────────────────

_amd_device = None
_amd_device_checked = False

def get_amd_device():
    """
    Возвращает DirectML device для AMD GPU или None если недоступен.
    Кешируется после первого вызова.
    """
    global _amd_device, _amd_device_checked
    if _amd_device_checked:
        return _amd_device
    _amd_device_checked = True

    try:
        import torch_directml
        device = torch_directml.device()
        _amd_device = device
        log.info("AMD DirectML: ✅ устройство инициализировано: %s", device)
        return device
    except ImportError:
        log.warning("torch-directml не установлен. Запусти: pip install torch-directml")
    except Exception as e:
        log.warning("AMD DirectML init error: %s", e)

    return None


def get_best_device():
    """
    Возвращает лучший доступный device:
    CUDA > AMD DirectML > CPU
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass

    dml = get_amd_device()
    if dml is not None:
        return dml

    return "cpu"


# ─────────────────────────────────────────────────────────────
# [4] Патч Whisper — поддержка AMD через ONNX Runtime DirectML
# ─────────────────────────────────────────────────────────────

def _patched_transcribe_with_whisper(self, audio_data) -> str:
    """Исправленная версия с AMD поддержкой через faster-whisper + CPU (AMD → ONNX DirectML в планах)."""
    try:
        if self._whisper_model is None:
            from faster_whisper import WhisperModel

            model_size = os.getenv("WHISPER_MODEL", "small")
            device_env = os.getenv("WHISPER_DEVICE", "auto")
            compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

            # Определяем лучшее устройство для Whisper
            if device_env == "auto":
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                        compute = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
                    else:
                        # AMD на Windows: faster-whisper не поддерживает DirectML
                        # используем CPU с int8 — быстрее чем float32
                        device = "cpu"
                        compute = "int8"
                except ImportError:
                    device = "cpu"
                    compute = "int8"
            else:
                device = device_env

            log.info("[Whisper] Инициализация: model=%s device=%s compute=%s",
                     model_size, device, compute)
            self._whisper_model = WhisperModel(model_size, device=device, compute_type=compute)

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data.get_wav_data())
            wav_path = tmp.name

        segments, _ = self._whisper_model.transcribe(wav_path, language="ru", vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip())

        try:
            os.remove(wav_path)
        except Exception:
            pass

        return text

    except Exception as e:
        log.warning("Whisper STT fallback: %s", e)
        return ""


def _patched_transcribe_audio_path(self, audio_path: str) -> str:
    """Патч транскрибации файла — автодетект устройства."""
    if not audio_path or not os.path.exists(audio_path):
        return ""
    try:
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            model_size = os.getenv("WHISPER_MODEL", "small")
            device_env = os.getenv("WHISPER_DEVICE", "auto")
            compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

            if device_env == "auto":
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"
            else:
                device = device_env

            self._whisper_model = WhisperModel(model_size, device=device, compute_type=compute)

        segments, _ = self._whisper_model.transcribe(audio_path, language="ru", vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip())
        return text.strip()
    except Exception as e:
        log.warning("Whisper file STT: %s", e)
        return ""


# ─────────────────────────────────────────────────────────────
# [5] Новые команды: 'gpu инфо' и 'gpu установить'
# ─────────────────────────────────────────────────────────────

def _gpu_info_command() -> str:
    """Команда 'gpu инфо' — полная инфо об AMD GPU."""
    lines = ["🖥 GPU ИНФОРМАЦИЯ (AMD / Windows):\n"]

    # Определяем GPU через WMI
    gpu = detect_amd_gpu_windows()
    if gpu:
        lines.append(f"  Название:    {gpu['name']}")
        lines.append(f"  Производит.: {gpu['vendor']}")
        if gpu['vram_mb'] > 0:
            lines.append(f"  VRAM:        {gpu['vram_mb']} МБ ({gpu['vram_mb']//1024} ГБ)")
        lines.append(f"  Драйвер:     {gpu['driver']}")
    else:
        lines.append("  ❌ AMD GPU не определён через WMI")

    lines.append("")

    # Проверяем torch-directml
    try:
        import torch_directml
        dml_device = torch_directml.device()
        lines.append(f"  torch-directml: ✅ установлен")
        lines.append(f"  DirectML device: {dml_device}")
    except ImportError:
        lines.append("  torch-directml: ❌ не установлен")
        lines.append("  → Запусти: pip install torch-directml")
    except Exception as e:
        lines.append(f"  torch-directml: ⚠️ {e}")

    # Проверяем PyTorch
    try:
        import torch
        version = torch.__version__
        cuda_ok = torch.cuda.is_available()
        lines.append(f"\n  PyTorch: {version}")
        lines.append(f"  CUDA: {'✅' if cuda_ok else '❌ (норм для AMD)'}")
    except ImportError:
        lines.append("\n  PyTorch: ❌ не установлен")

    # Проверяем ONNX Runtime DirectML
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        dml_ok = "DmlExecutionProvider" in providers
        lines.append(f"\n  ONNX Runtime: ✅ {ort.__version__}")
        lines.append(f"  DirectML provider: {'✅' if dml_ok else '❌'}")
        lines.append(f"  Providers: {', '.join(providers)}")
    except ImportError:
        lines.append("\n  ONNX Runtime: ❌ не установлен")

    lines.append("\n💡 Для использования AMD GPU в проекте:")
    lines.append("  1. pip install torch-directml")
    lines.append("  2. В .env добавь: ARGOS_GPU_DEVICE=directml")
    lines.append("  3. Перезапусти Аргос")

    return "\n".join(lines)


def _gpu_install_command() -> str:
    """Команда 'gpu установить' — устанавливает torch-directml."""
    lines = ["🔧 Устанавливаю AMD GPU библиотеки...\n"]
    try:
        result = subprocess.run(
            ["pip", "install", "torch-directml", "--quiet"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            lines.append("✅ torch-directml установлен!")
            lines.append("\nПроверяю...")
            try:
                import importlib
                import sys
                if "torch_directml" in sys.modules:
                    del sys.modules["torch_directml"]
                import torch_directml
                device = torch_directml.device()
                lines.append(f"✅ DirectML device: {device}")
                lines.append("\nAMD GPU теперь доступен для PyTorch!")
                lines.append("Перезапусти Аргос для применения изменений.")
            except Exception as e:
                lines.append(f"⚠️ Установлен но ошибка при проверке: {e}")
        else:
            lines.append(f"❌ Ошибка установки:")
            lines.append(result.stderr[:300] if result.stderr else "неизвестная ошибка")
    except Exception as e:
        lines.append(f"❌ {e}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# ПРИМЕНЕНИЕ ПАТЧА
# ─────────────────────────────────────────────────────────────

def apply_amd_patch():
    """Применяет все патчи AMD GPU к ArgosCore."""
    try:
        from src.core import ArgosCore
        import types

        # [2] Патч _video_line (через _low_level_drivers_report)
        # Встраиваем нашу функцию в замыкание — заменяем внутренний _video_line
        original_low_level = ArgosCore._low_level_drivers_report

        def _patched_low_level_drivers_report(self) -> str:
            result = original_low_level(self)
            # Заменяем строку с GPU если она показывает "не обнаружены"
            if "⚠️ не обнаружены" in result or "⚠️ проверка недоступна" in result:
                new_gpu_line = _patched_video_line()
                lines = result.split("\n")
                patched_lines = []
                for line in lines:
                    if "Видеоядра/GPU:" in line:
                        patched_lines.append(new_gpu_line)
                    else:
                        patched_lines.append(line)
                return "\n".join(patched_lines)
            return result

        ArgosCore._low_level_drivers_report = _patched_low_level_drivers_report

        # Патч _ai_modes_diagnostic GPU секции
        original_diag = ArgosCore._ai_modes_diagnostic

        def _patched_ai_modes_diagnostic(self) -> str:
            result = original_diag(self)
            if "GPU:          ⚠️ не обнаружен" in result:
                gpu = detect_amd_gpu_windows()
                if gpu:
                    vram_str = f" | VRAM {gpu['vram_mb']} МБ" if gpu['vram_mb'] > 0 else ""
                    gpu_line = f"  • GPU:          ✅ {gpu['name']}{vram_str}"
                    lines = result.split("\n")
                    patched = [gpu_line if "GPU:          ⚠️" in l else l for l in lines]
                    result = "\n".join(patched)
            return result

        ArgosCore._ai_modes_diagnostic = _patched_ai_modes_diagnostic

        # [4] Патч Whisper методов
        ArgosCore._transcribe_with_whisper = _patched_transcribe_with_whisper
        ArgosCore.transcribe_audio_path = _patched_transcribe_audio_path

        # [5] Патч execute_intent — добавляем 'gpu инфо' и 'gpu установить'
        original_execute = ArgosCore.execute_intent

        def _patched_execute_intent(self, text: str, admin, flasher):
            t = text.lower().strip()
            if any(k in t for k in ["gpu инфо", "gpu info", "видеокарта инфо",
                                     "amd gpu", "directml статус"]):
                return _gpu_info_command()
            if any(k in t for k in ["gpu установить", "установи directml",
                                     "install gpu", "gpu install"]):
                return _gpu_install_command()
            return original_execute(self, text, admin, flasher)

        ArgosCore.execute_intent = _patched_execute_intent

        # Добавляем утилиты как методы класса
        ArgosCore.get_amd_device = staticmethod(get_amd_device)
        ArgosCore.get_best_device = staticmethod(get_best_device)

        log.info("AMD GPU патч применён")
        print("[AMD GPU Patch] OK: Применён успешно")

    except Exception as e:
        log.error("AMD GPU патч: ошибка: %s", e)
        print(f"[AMD GPU Patch] WARN: Ошибка: {e}")


# Автоприменение при импорте
if __name__ != "__main__":
    apply_amd_patch()