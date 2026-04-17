"""
auto_patcher.py — Автоприменение патчей из Telegram
"""
import os
import sys
import subprocess
import importlib
from pathlib import Path
from src.argos_logger import get_logger

log = get_logger("argos.patcher")


class AutoPatcher:
    def __init__(self, core=None):
        self.core = core
        self.patches_dir = Path("data/patches")
        self.patches_dir.mkdir(parents=True, exist_ok=True)

    def apply_file(self, file_path: str, content: bytes) -> str:
        """Применяет патч из файла"""
        path = Path(file_path)
        ext = path.suffix.lower()
        try:
            if ext == ".py":
                return self._apply_python(path, content)
            elif ext == ".sh":
                return self._apply_shell(path, content)
            elif ext == ".json":
                return self._apply_json(path, content)
            elif path.name.startswith(".env"):
                return self._apply_env(path, content)
            else:
                return f"Неизвестный тип файла: {ext}"
        except Exception as e:
            log.error(f"Ошибка применения патча: {e}")
            return f"Ошибка патча: {e}"

    def _apply_python(self, path: Path, content: bytes) -> str:
        text = content.decode("utf-8", errors="replace")
        try:
            compile(text, str(path), "exec")
        except SyntaxError as e:
            return f"Синтаксис: {e}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        log.info(f"Патч применён: {path}")
        mod_name = str(path).replace("/", ".").replace("\\", ".").rstrip(".py")
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass
        return f"✅ Патч применён: {path}"

    def _apply_shell(self, path: Path, content: bytes) -> str:
        path.write_bytes(content)
        os.chmod(path, 0o755)
        result = subprocess.run(["bash", str(path)], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return f"Ошибка: {result.stderr[:300]}"
        return f"✅ Скрипт выполнен: {result.stdout[:200]}"

    def _apply_json(self, path: Path, content: bytes) -> str:
        import json
        try:
            data = json.loads(content.decode("utf-8"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return f"✅ JSON обновлён: {path}"
        except json.JSONDecodeError as e:
            return f"Невалидный JSON: {e}"

    def _apply_env(self, path: Path, content: bytes) -> str:
        text = content.decode("utf-8", errors="replace")
        path.write_text(text, encoding="utf-8")
        return f"✅ .env обновлён: {path}"
