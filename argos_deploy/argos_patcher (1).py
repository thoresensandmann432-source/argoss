#!/usr/bin/env python3
"""
argos_patcher.py — Автономный патчер Аргоса для Windows
Запуск: python argos_patcher.py

Вставляет полный перехватчик команд в execute_intent,
включая прямые вызовы всех навыков.
"""
import os, sys, re, ast, shutil
from pathlib import Path

def info(m): print(f"[INFO]  {m}")
def ok(m):   print(f"[OK]    {m}")
def err(m):  print(f"[ERR]   {m}")
def warn(m): print(f"[WARN]  {m}")

INTERCEPT_MARKER = "# ═══ ARGOS_PATCHER_V2 ═══"

# ─────────────────────────────────────────────────────────────────────────────
# ПОЛНЫЙ ПЕРЕХВАТЧИК — вставляется в начало execute_intent
# Содержит ВСЕ обработчики навыков напрямую, без обращения к LLM
# ─────────────────────────────────────────────────────────────────────────────
INTERCEPT_CODE = r'''
        # ═══ ARGOS_PATCHER_V2 ═══  (не удалять эту строку!)
        import importlib.util as _ilu, os as _os
        from pathlib import Path as _P

        _t = text.lower().strip()

        def _load_skill(name, cls_name):
            """Загружает класс навыка из src/skills/name/ или src/skills/name.py."""
            # Путь к src/skills относительно core.py
            _base = _P(__file__).parent
            for _sd in [_base/"src"/"skills", _base/"skills"]:
                for _path in [_sd/name/"__init__.py", _sd/f"{name}.py"]:
                    if _path.exists():
                        try:
                            _sp = _ilu.spec_from_file_location(f"_skill_{name}", str(_path))
                            _m  = _ilu.module_from_spec(_sp)
                            _sp.loader.exec_module(_m)
                            return getattr(_m, cls_name, None)
                        except Exception:
                            pass
            return None

        # ── Диагностика навыков ──────────────────────────────────────────
        if any(k in _t for k in ["диагностика навыков", "проверь навыки", "навыки статус"]):
            if hasattr(self, "_skills_diagnostic"):
                return self._skills_diagnostic()
            # Встроенная диагностика
            _base = _P(__file__).parent
            _sd = next((_b/"src"/"skills" for _b in [_base] if (_b/"src"/"skills").exists()),
                       next((_b/"skills" for _b in [_base] if (_b/"skills").exists()), None))
            if not _sd:
                return f"❌ src/skills не найден. Ищем рядом с {_base}"
            _lines = [f"🔧 НАВЫКИ ({_sd}):\n"]
            _ok = _fail = _warn = 0
            for _item in sorted(_sd.iterdir()):
                if _item.name.startswith("_"): continue
                _n = _item.stem if _item.is_file() else _item.name
                _lp = str(_item/"__init__.py") if _item.is_dir() else str(_item)
                if not _P(_lp).exists(): continue
                try:
                    _sp = _ilu.spec_from_file_location(f"_sk_{_n}", _lp)
                    _m  = _ilu.module_from_spec(_sp)
                    _sp.loader.exec_module(_m)
                    _has = any([hasattr(_m,"handle"),hasattr(_m,"execute"),
                                any(k[0].isupper() for k in dir(_m) if not k.startswith("_"))])
                    _lines.append(f"  {'✅' if _has else '⚠️ '} {_n}")
                    if _has: _ok += 1
                    else: _warn += 1
                except ImportError as _e:
                    _lines.append(f"  ❌ {_n} — {str(_e)[:40]}")
                    _fail += 1
                except Exception as _e:
                    _lines.append(f"  ⚠️  {_n} — {str(_e)[:40]}")
                    _warn += 1
            _lines.append(f"\n✅ {_ok}  ⚠️ {_warn}  ❌ {_fail}")
            return "\n".join(_lines)

        # ── Статус системы ──────────────────────────────────────────────
        if any(k in _t for k in ["статус системы", "чек-ап", "состояние здоровья"]):
            try:
                import psutil as _ps
                _cpu  = _ps.cpu_percent(interval=0.3)
                _ram  = _ps.virtual_memory()
                _disk = _ps.disk_usage(_os.getcwd())
                return (f"📊 СОСТОЯНИЕ СИСТЕМЫ:\n"
                        f"  💻 CPU:  {_cpu}%\n"
                        f"  🧠 RAM:  {_ram.percent:.1f}% "
                        f"({_ram.used//1024//1024:,} / {_ram.total//1024//1024:,} МБ)\n"
                        f"  💾 Диск: {_disk.free//1024**3:.1f} ГБ свободно "
                        f"из {_disk.total//1024**3:.1f} ГБ\n"
                        f"  🖥  ОС:   {__import__('platform').system()} "
                        f"{__import__('platform').release()}")
            except Exception as _e:
                return f"❌ psutil: {_e}"

        # ── Крипто ───────────────────────────────────────────────────────
        if any(k in _t for k in ["крипто", "биткоин", "bitcoin", "ethereum", "btc", "eth"]):
            _CLS = _load_skill("crypto_monitor", "CryptoSentinel")
            if _CLS: 
                try: return _CLS().report()
                except Exception as _e: return f"❌ CryptoSentinel: {_e}"
            return "❌ Навык crypto_monitor не найден в src/skills/"

        # ── Сканирование сети ────────────────────────────────────────────
        if any(k in _t for k in ["сканируй сеть", "сетевой призрак", "сканировать сеть",
                                   "network scan", "net scan"]):
            _CLS = _load_skill("net_scanner", "NetGhost")
            if _CLS:
                try: return _CLS().scan()
                except Exception as _e: return f"❌ NetGhost: {_e}"
            # Fallback — базовое сканирование через socket
            try:
                import socket, subprocess as _sp2
                _r = _sp2.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
                return f"📡 ARP таблица:\n{_r.stdout[:1500]}" if _r.returncode == 0 else "❌ arp -a недоступен"
            except Exception as _e:
                return f"❌ Сканирование: {_e}"

        # ── Дайджест ─────────────────────────────────────────────────────
        if any(k in _t for k in ["дайджест", "опубликуй", "digest"]):
            _CLS = _load_skill("content_gen", "ContentGen")
            if _CLS:
                try: return _CLS().generate_digest()
                except Exception as _e: return f"❌ ContentGen: {_e}"
            return "❌ Навык content_gen не найден"

        # ── Погода ───────────────────────────────────────────────────────
        if any(k in _t for k in ["погода", "weather", "прогноз погоды"]):
            _CLS = _load_skill("weather", "WeatherSkill") or _load_skill("weather", "Weather")
            if _CLS:
                try: return _CLS().report()
                except Exception as _e: return f"❌ Weather: {_e}"
            # Fallback — wttr.in без API ключа
            try:
                import urllib.request as _ur
                city = _t.replace("погода","").replace("weather","").replace("прогноз","").strip() or "Moscow"
                _resp = _ur.urlopen(f"https://wttr.in/{city}?format=3", timeout=8)
                return f"🌤 {_resp.read().decode()}"
            except Exception as _e:
                return f"❌ Погода: {_e}"

        # ── Проверь железо ───────────────────────────────────────────────
        if any(k in _t for k in ["проверь железо", "hardware", "железо", "характеристики железа"]):
            _CLS = (_load_skill("hardware_intel", "HardwareIntelSkill") or
                    _load_skill("hardware_intel", "HardwareIntel"))
            if _CLS:
                try: return _CLS().report()
                except Exception as _e: return f"❌ HardwareIntel: {_e}"
            try:
                import platform as _plat, psutil as _ps2
                _cpu = _ps2.cpu_percent(interval=0.2)
                _ram = _ps2.virtual_memory()
                return (f"🖥 ЖЕЛЕЗО:\n"
                        f"  ОС: {_plat.system()} {_plat.release()} {_plat.machine()}\n"
                        f"  CPU: {_plat.processor()}\n"
                        f"  Ядра: {_ps2.cpu_count()} логических\n"
                        f"  RAM: {_ram.total//1024**3:.1f} ГБ\n"
                        f"  Загрузка: CPU {_cpu}% / RAM {_ram.percent:.1f}%")
            except Exception as _e:
                return f"❌ {_e}"

        # ── Shodan ───────────────────────────────────────────────────────
        if any(k in _t for k in ["shodan", "сканируй shodan"]):
            _CLS = _load_skill("shodan_scanner", "ShodanScanner")
            if _CLS:
                try: return _CLS().scan()
                except Exception as _e: return f"❌ ShodanScanner: {_e}"
            return "❌ Shodan Scanner не найден. Нужен SHODAN_API_KEY в .env"

        # ── Напиши/создай навык ──────────────────────────────────────────
        if any(k in _t for k in ["напиши навык", "создай навык"]):
            _CLS = _load_skill("evolution", "ArgosEvolution")
            if _CLS:
                _desc = text.replace("напиши навык","").replace("создай навык","").strip()
                try: return _CLS(ai_core=self).generate_skill(_desc)
                except TypeError:
                    try: return _CLS().generate_skill(_desc)
                    except Exception as _e2: return f"❌ Evolution: {_e2}"
            return "❌ Навык evolution не найден"

        # ── Список навыков ───────────────────────────────────────────────
        if any(k in _t for k in ["список навыков", "навыки аргоса", "все навыки"]):
            if self.skill_loader:
                try: return self.skill_loader.list_skills()
                except Exception: pass
            _base = _P(__file__).parent
            _sd = next((_b/"src"/"skills" for _b in [_base] if (_b/"src"/"skills").exists()), None)
            if _sd:
                _skills = [f"  • {f.stem if f.is_file() else f.name}" 
                           for f in sorted(_sd.iterdir()) 
                           if not f.name.startswith("_")]
                return "📚 НАВЫКИ АРГОСА:\n" + "\n".join(_skills)
            return "❌ src/skills не найден"

        # ── Помощь ───────────────────────────────────────────────────────
        if _t.strip() in ("помощь", "help", "команды", "?"):
            return self._help() if hasattr(self, "_help") else (
                "📋 Команды: статус системы · крипто · сканируй сеть · "
                "дайджест · погода · проверь железо · список навыков · "
                "диагностика навыков · создай файл [имя] · прочитай файл [путь]"
            )

        # ═══ END ARGOS_PATCHER_V2 ═══
'''

# ── НАЙТИ core.py ─────────────────────────────────────────────────────────────

def find_core_py():
    for base in [Path.cwd()] + list(Path.cwd().parents)[:5]:
        for pat in ["core.py", "*/core.py", "apps/**/core.py", "src/../core.py"]:
            for f in base.glob(pat):
                try:
                    t = f.read_text(encoding="utf-8", errors="ignore")
                    if "ArgosCore" in t and "execute_intent" in t:
                        return f
                except Exception:
                    pass
    return None

# ── ПАТЧИТЬ execute_intent ────────────────────────────────────────────────────

def patch(src):
    # Убираем старый патч если есть
    old_markers = ["# ═══ ARGOS_PATCHER_INTERCEPT ═══", "# ═══ ARGOS_PATCHER_V2 ═══"]
    for marker in old_markers:
        if marker in src:
            # Найти и удалить блок от marker до END marker
            start = src.find(f"\n        {marker.strip()}")
            if start == -1:
                start = src.find(f"        {marker.strip()}")
            end_marker = "# ═══ END ARGOS_PATCHER_V2 ═══"
            end = src.find(end_marker)
            if end != -1:
                end = src.find("\n", end) + 1
            if start != -1 and end != -1 and end > start:
                src = src[:start] + src[end:]
                info(f"Старый патч удалён")

    # Найти точку вставки
    ei = src.find("    def execute_intent(")
    if ei == -1:
        return src, "❌ execute_intent не найден"
    t_line = src.find("        t = text.lower()", ei)
    if t_line == -1:
        return src, "❌ t = text.lower() не найден"
    eol = src.find("\n", t_line)
    patched = src[:eol+1] + INTERCEPT_CODE + src[eol+1:]
    return patched, "✅ патч вставлен"

# ── ОЧИСТИТЬ КЕШ ─────────────────────────────────────────────────────────────

def clear_cache(root):
    count = 0
    for pyc in root.rglob("*.pyc"):
        try: pyc.unlink(); count += 1
        except: pass
    for d in root.rglob("__pycache__"):
        try: shutil.rmtree(str(d), ignore_errors=True); count += 1
        except: pass
    return count

# ── MAIN ─────────────────────────────────────────────────────────────────────

def _patch_ollama_prompt(core_src: str) -> tuple[str, str]:
    """Ужесточает системный промпт для Ollama в core.py."""
    if "ARGOS_OLLAMA_PATCHED" in core_src:
        return core_src, "уже пропатчено"

    # Найти context в process_logic и добавить правила
    OLD_CTX = 'f"Ты Аргос — автономный ИИ-ассистент Всеволода. Год: 2026. "'
    if OLD_CTX not in core_src:
        return core_src, "⚠️ context pattern не найден"

    NEW_CTX = (
        'f"Ты Аргос — автономный ИИ-ассистент Всеволода. Год: 2026. "'
        '# ARGOS_OLLAMA_PATCHED'
    )
    # Just mark it as patched and add the rule suffix
    RULES = (
        '"\n# ARGOS_OLLAMA_PATCHED\n"'
        '"ПРАВИЛО: если пользователь просит выполнить команду (создай файл, диагностика, статус) — "'
        '"скажи что система уже выполнила, не описывай инструкции. "'
        '"ЗАПРЕЩЕНО выдумывать пакеты и SDK."'
    )
    idx = core_src.find(OLD_CTX)
    line_end = core_src.find("\n", idx)
    if line_end == -1:
        return core_src, "⚠️ конец строки не найден"
    patched = core_src[:line_end] + "\n            " + RULES + core_src[line_end:]
    return patched, "✅ Ollama system prompt усилен"



def main():
    print("="*55)
    print("  ARGOS PATCHER v2 — полный перехватчик навыков")
    print("="*55)

    info("Ищу core.py...")
    core = find_core_py()
    if core is None:
        err(f"core.py не найден! Текущая папка: {Path.cwd()}")
        err("Запусти скрипт из папки проекта Аргоса.")
        sys.exit(1)
    ok(f"Найден: {core}")

    src = core.read_text(encoding="utf-8")

    bak = core.with_suffix(".py.bak")
    shutil.copy2(str(core), str(bak))
    ok(f"Резервная копия: {bak}")

    patched, status = patch(src)
    info(f"Патч: {status}")

    try:
        ast.parse(patched)
        ok("Синтаксис: OK")
    except SyntaxError as e:
        err(f"Синтаксическая ошибка: {e}")
        shutil.copy2(str(bak), str(core))
        err("Откат выполнен.")
        sys.exit(1)

    core.write_text(patched, encoding="utf-8")
    ok(f"core.py записан ({core.stat().st_size:,} байт)")

    n = clear_cache(core.parent)
    ok(f"Кеш очищен: {n} объектов удалено")

    print()
    print("="*55)
    ok("Готово! Перезапусти Аргос: python main.py")
    print()
    print("Теперь работают напрямую (без LLM):")
    print("  крипто            → CryptoSentinel().report()")
    print("  сканируй сеть     → NetGhost().scan()")
    print("  дайджест          → ContentGen().generate_digest()")
    print("  погода [город]    → wttr.in")
    print("  проверь железо    → psutil + platform")
    print("  диагностика навыков → сканирует src/skills/")
    print("  статус системы    → реальный psutil CPU/RAM")
    print("  список навыков    → все файлы в src/skills/")
    print("="*55)

if __name__ == "__main__":
    main()
