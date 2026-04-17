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

        # ── Аварийная установка отсутствующих методов ──────────────────────
        if not hasattr(self.__class__, 'dispatchskill'):
            import types as _types
            def _dispatchskill_patch(self_, text_, t_=None):
                t_ = t_ or text_.lower()
                return self_._dispatch_skill(text_, t_) if hasattr(self_, '_dispatch_skill') else None
            self.__class__.dispatchskill  = _types.MethodType(_dispatchskill_patch, self).__func__
            self.__class__.dispatch_skill = _types.MethodType(_dispatchskill_patch, self).__func__

        import importlib.util as _ilu, os as _os
        from pathlib import Path as _P

        _t = text.lower().strip()

        # ══ АБСОЛЮТНЫЙ ПЕРВЫЙ ПРИОРИТЕТ ══
        # Эти проверки работают ВСЕГДА, без зависимостей
        if _t in ("список навыков", "навыки аргоса", "все навыки", "навыки"):
            try:
                _base_a = _P(__file__).parent
                for _sd_a in [_base_a/"src"/"skills", _base_a/"skills",
                               _P.cwd()/"src"/"skills", _P.cwd()/"skills"]:
                    if _sd_a.exists():
                        _sk_list = []
                        for _f_a in sorted(_sd_a.iterdir()):
                            if not _f_a.name.startswith("_"):
                                _icon = "📦" if _f_a.is_dir() else "📄"
                                _sk_list.append(f"  {_icon} {_f_a.stem if _f_a.is_file() else _f_a.name}")
                        return f"📚 НАВЫКИ ({len(_sk_list)}):\n" + "\n".join(_sk_list)
            except Exception as _ea:
                return f"❌ Список навыков: {_ea}"

        if any(_t.startswith(_k) for _k in ("создай файл", "напиши файл")):
            _adm_a = getattr(self, "_internal_admin", None) or getattr(self, "admin", None)
            if _adm_a is None:
                try:
                    from src.admin import ArgosAdmin as _AA_a
                    _adm_a = _AA_a()
                    self._internal_admin = _adm_a
                except Exception as _e_a:
                    return f"❌ admin: {_e_a}"
            _body_a = text.replace("создай файл","").replace("напиши файл","").strip()
            _parts_a = _body_a.split(None, 1)
            _fname_a = _parts_a[0] if _parts_a else "note.txt"
            _ftext_a = _parts_a[1] if len(_parts_a) > 1 else ""
            try:
                return _adm_a.create_file(_fname_a, _ftext_a)
            except Exception as _e_a:
                return f"❌ {_e_a}"

        _t_patch = _t  # Совместимость со старыми блоками

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
            _lines = []
            # Пробуем skill_loader
            if self.skill_loader:
                try:
                    _result = self.skill_loader.list_skills()
                    if _result and len(_result) > 5:
                        return _result
                except Exception:
                    pass
            # Прямой скан src/skills/
            try:
                _base = _P(__file__).parent
                _sd = None
                for _b in [_base, _P.cwd()]:
                    for _sub in ["src/skills", "skills"]:
                        _c = _b / _sub.replace("/", _os.sep)
                        if _c.exists():
                            _sd = _c
                            break
                    if _sd: break
                if _sd:
                    _pkg, _flat = [], []
                    for _f in sorted(_sd.iterdir()):
                        if _f.name.startswith("_"): continue
                        if _f.is_dir() and (_f/"__init__.py").exists():
                            _pkg.append(f"  📦 {_f.name}")
                        elif _f.is_file() and _f.suffix == ".py":
                            _flat.append(f"  📄 {_f.stem}")
                    _lines.append(f"📚 НАВЫКИ АРГОСА ({len(_pkg)+len(_flat)} всего):\n")
                    if _pkg:
                        _lines.append("  [ПАКЕТЫ]")
                        _lines.extend(_pkg)
                    if _flat:
                        _lines.append("  [ФАЙЛЫ]")
                        _lines.extend(_flat)
                    _lines.append(f"\n  Каталог: {_sd}")
                    return "\n".join(_lines)
            except Exception as _e:
                return f"❌ Список навыков: {_e}"
            return "❌ src/skills не найден"

        # ── Запуск навыка по точному имени (напр. "Evolution v2.1.0") ────
        import re as _re2
        _SMAP = {
            "evolution":      ("evolution",      "ArgosEvolution",  None),
            "netscanner":     ("net_scanner",    "NetGhost",        "scan"),
            "net_scanner":    ("net_scanner",    "NetGhost",        "scan"),
            "cryptomonitor":  ("crypto_monitor", "CryptoSentinel",  "report"),
            "contentgen":     ("content_gen",    "ContentGen",      "generate_digest"),
            "webscrapper":    ("web_scrapper",   None,              None),
            "weather":        ("weather",        None,              None),
            "hardwareintel":  ("hardware_intel", None,              None),
            "hardware_intel": ("hardware_intel", None,              None),
            "shodanscanner":  ("shodan_scanner", None,              None),
            "huggingfaceai":  ("huggingface_ai", None,              None),
            "networkshadow":  ("network_shadow", None,              None),
        }
        # Убираем версию ("v2.1.0"), пробелы, тире — получаем чистое имя навыка
        _sq = _re2.sub(r'[\\s_v\\d\\.]+$', '', _t.strip().replace("-","_").replace(" ",""))
        # Также проверяем полное совпадение без преобразований (для "evolution")
        _sq_raw = _t.strip().replace(" ","").replace("-","_")
        if _sq in _SMAP or _sq_raw in _SMAP:
            _sq = _sq if _sq in _SMAP else _sq_raw
            _sn2, _sc2, _sm2 = _SMAP[_sq]
            _cls2 = _load_skill(_sn2, _sc2 or "")
            if _cls2:
                try:
                    _obj2 = _cls2()
                    # Если задан метод и он существует — вызываем его
                    if _sm2 and hasattr(_obj2, _sm2):
                        _res2 = getattr(_obj2, _sm2)()
                        return str(_res2) if _res2 is not None else f"✅ {_sn2}.{_sm2}() выполнен"
                    # Автовыбор метода по приоритету
                    for _m2 in ("report","scan","run","execute","generate_digest",
                                "get_status","status","info","describe","help"):
                        if hasattr(_obj2, _m2):
                            try:
                                _res2 = getattr(_obj2, _m2)()
                                return str(_res2) if _res2 is not None else f"✅ {_sn2}.{_m2}() выполнен"
                            except Exception:
                                continue
                    # Если ни один метод не сработал — показываем что есть
                    _methods = [m for m in dir(_obj2) if not m.startswith("_")]
                    _mlist = ', '.join(_methods[:8])
                    return f"✅ Навык {_sn2} загружен.\nМетоды: {_mlist}"
                except Exception as _e2:
                    return f"❌ {_sn2}: {_e2}"
            # Класс не найден — попробуем handle() напрямую
            _base3 = _P(__file__).parent
            for _sd3 in [_base3/"src"/"skills", _base3/"skills"]:
                for _fp3 in [_sd3/_sn2/"__init__.py", _sd3/f"{_sn2}.py"]:
                    if _fp3.exists():
                        try:
                            _sp3 = _ilu.spec_from_file_location(f"sk_{_sn2}", str(_fp3))
                            _m3  = _ilu.module_from_spec(_sp3)
                            _sp3.loader.exec_module(_m3)
                            if hasattr(_m3, "handle"):
                                _r3 = _m3.handle(text)
                                return _r3 if _r3 else f"✅ {_sn2} выполнен"
                            if hasattr(_m3, "execute"):
                                return str(_m3.execute())
                        except Exception as _e3:
                            return f"❌ {_sn2}: {_e3}"
            return f"❌ Навык {_sn2!r} не найден в src/skills/"

        # ── Создание файлов (гарантированное выполнение) ─────────────────
        if any(_t.startswith(_k) for _k in ("создай файл", "напиши файл")):
            _adm = getattr(self, "_internal_admin", None) or getattr(self, "admin", None)
            if _adm is None:
                try:
                    from src.admin import ArgosAdmin as _AA
                    _adm = _AA()
                    self._internal_admin = _adm
                except Exception as _ae:
                    return f"❌ admin недоступен: {_ae}"
            _body = text
            for _k in ("создай файл", "напиши файл"):
                _body = _body.replace(_k, "").strip()
            _parts = _body.split(None, 1)
            _fname = _parts[0] if _parts else "note.txt"
            _fcontent = _parts[1] if len(_parts) > 1 else ""
            try:
                return _adm.create_file(_fname, _fcontent)
            except Exception as _fe:
                return f"❌ Создание файла: {_fe}"

        if any(_t.startswith(_k) for _k in ("прочитай файл", "открой файл")):
            _adm = getattr(self, "_internal_admin", None) or getattr(self, "admin", None)
            if _adm is None:
                try:
                    from src.admin import ArgosAdmin as _AA
                    _adm = _AA()
                except Exception: pass
            _path = text
            for _k in ("прочитай файл", "открой файл"):
                _path = _path.replace(_k, "").strip()
            if _adm:
                try: return _adm.read_file(_path)
                except Exception as _re: return f"❌ {_re}"
            return f"❌ admin недоступен"

        # ── Помощь ───────────────────────────────────────────────────────
        if _t.strip() in ("помощь", "help", "команды", "список команд",
                           "что ты умеешь", "возможности", "?"):
            if hasattr(self, "_help"):
                return self._help()
            return (
                "📋 АРГОС — ОСНОВНЫЕ КОМАНДЫ:\n"
                "  список навыков · диагностика навыков\n"
                "  статус системы · диагностика ии\n"
                "  крипто · биткоин · сканируй сеть\n"
                "  проверь железо · погода · дайджест\n"
                "  создай файл [имя] [текст]\n"
                "  прочитай файл [путь]\n"
                "  покажи файлы [путь]\n"
                "  консоль [команда]\n"
                "  запусти навык [имя] · Evolution · Netscanner\n"
                "  обнови себя · git статус · win bridge"
            )


        # ── Создание файлов (включая блокнот/заметки) ────────────────────
        if any(k in _t for k in [
            "создай файл", "напиши файл", "создай блокнот",
            "создай заметку", "запишен файл", "сохрани в файл",
            "создай текстовый файл", "создай новый файл",
        ]):
            _body = text
            for _k in ["создай файл", "напиши файл", "создай блокнот",
                       "создай заметку", "сохрани в файл",
                       "создай текстовый файл", "создай новый файл"]:
                _body = _body.replace(_k, "").replace(_k.capitalize(), "").strip()
            _parts = _body.split(maxsplit=1)
            _stopw = {"и","с","в","для","на","из","о","по","к","у","за","до","от","а"}
            if _parts and _parts[0].lower().strip(".") in _stopw:
                _fname, _fcontent = "note.txt", _body.strip()
            else:
                _fname    = (_parts[0] if _parts else "note.txt").strip()
                _fcontent = _parts[1].strip() if len(_parts) > 1 else ""
            if "." not in _fname:
                _fname += ".txt"
            try:
                import os as _osc
                _fpath = _osc.path.join(_osc.getcwd(), _fname)
                with open(_fpath, "w", encoding="utf-8") as _fh:
                    _fh.write(_fcontent)
                _size = _osc.path.getsize(_fpath)
                return f"✅ Файл создан: {_fname} ({_size} байт)\nПуть: {_fpath}"
            except Exception as _fe:
                return f"❌ Ошибка создания файла: {_fe}"

        # ── Прочитать файл ────────────────────────────────────────────────
        if any(k in _t for k in ["прочитай файл", "открой файл", "покажи содержимое"]):
            _body = text
            for _k in ["прочитай файл", "открой файл", "покажи содержимое"]:
                _body = _body.replace(_k, "").strip()
            _fpath = _body.strip()
            try:
                with open(_fpath, "r", encoding="utf-8", errors="replace") as _fh:
                    _content = _fh.read()
                _preview = _content[:2000]
                _dots = "..." if len(_content) > 2000 else ""
                return f"📄 {_fpath}:\n{_preview}{_dots}"
            except FileNotFoundError:
                return f"❌ Файл не найден: {_fpath}"
            except Exception as _fe:
                return f"❌ Ошибка чтения: {_fe}"

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
    """Вставляет перехватчик в execute_intent. Предварительно удаляет ВСЕ старые блоки."""

    # Удаляем ВСЕ варианты старых патчей — их несколько из разных версий
    all_start_markers = [
        "# ═══ ARGOS_PATCHER_INTERCEPT ═══",
        "# ═══ ARGOS_PATCHER_V2 ═══",
        "# ПЕРВЫЙ ПРИОРИТЕТ",
        "# ════════════════════════════════════════════════════════════════",
    ]
    all_end_markers = [
        "# ═══ END ARGOS_PATCHER_INTERCEPT ═══",
        "# ═══ END ARGOS_PATCHER_V2 ═══",
        "# ═══ END",
    ]

    import re as _re

    # Удаляем по парам start→end
    for sm in all_start_markers:
        while sm in src:
            si = src.find(sm)
            if si == -1:
                break
            # Найти начало строки с маркером
            line_start = src.rfind("\n", 0, si) + 1
            # Найти ближайший end-маркер
            ei_best = len(src)
            for em in all_end_markers:
                ei = src.find(em, si)
                if ei != -1:
                    ei_best = min(ei_best, ei)
            if ei_best < len(src):
                # Удаляем до конца строки end-маркера
                end_of_line = src.find("\n", ei_best)
                if end_of_line == -1:
                    end_of_line = len(src)
                src = src[:line_start] + src[end_of_line + 1:]
                info("Старый блок перехватчика удалён")
            else:
                break

    # Найти точку вставки — ПЕРВАЯ строка после t = text.lower() в execute_intent
    ei_pos = src.find("    def execute_intent(")
    if ei_pos == -1:
        return src, "❌ execute_intent не найден"

    t_line = src.find("        t = text.lower()", ei_pos)
    if t_line == -1:
        t_line = src.find("        t = text", ei_pos)
    if t_line == -1:
        return src, "❌ t = text.lower() не найден"

    eol = src.find("\n", t_line)
    patched = src[:eol + 1] + INTERCEPT_CODE + src[eol + 1:]
    # Добавляем alias для dispatchskill если отсутствует (совместимость со старыми патчами)
    if "def dispatchskill(" not in patched and "def _dispatch_skill(" in patched:
        alias = '\n    def dispatchskill(self, text: str, t=None) -> str | None:\n'
        alias += '        return self._dispatch_skill(text, t)\n'
        insert_at = patched.find("\n    def _run_skill(")
        if insert_at > 0:
            patched = patched[:insert_at] + alias + patched[insert_at:]
            info("Alias dispatchskill добавлен")

    # ── Добавляем dispatchskill алиас если отсутствует ───────────────────
    _ALIASES = {
        "dispatchskill": "_dispatch_skill",
        "dispatch_skill": "_dispatch_skill",
        "_run_dispatch":  "_dispatch_skill",
    }
    for _alias, _target in _ALIASES.items():
        if f"def {_alias}(" not in patched and f"def {_target}(" in patched:
            _alias_code = (
                f"\n    def {_alias}(self, text: str, t=None) -> str | None:\n"
                f"        return self.{_target}(text, t or text.lower())\n"
            )
            # Вставляем перед def _run_skill или перед последним def класса
            _insert_before = "    def _run_skill("
            if _insert_before in patched:
                patched = patched.replace(_insert_before, _alias_code + _insert_before, 1)
            info(f"Alias {_alias} добавлен")

    # Финальная защита: если где-то осталось _t_patch вне блока — заменяем на t
    _intercept_start = patched.find("# ═══ ARGOS_PATCHER_V2 ═══")
    _intercept_end   = patched.find("# ═══ END ARGOS_PATCHER_V2 ═══")
    if _intercept_start >= 0 and _intercept_end > _intercept_start:
        _before  = patched[:_intercept_start]
        _inside  = patched[_intercept_start:_intercept_end + 50]
        _after   = patched[_intercept_end + 50:]
        # Заменяем _t_patch в коде ВНЕ блока перехватчика
        _after_fixed = _after.replace("_t_patch", "t")
        if _after_fixed != _after:
            info("Исправлены ссылки на _t_patch вне блока")
        patched = _before + _inside + _after_fixed
    return patched, "✅ перехватчик вставлен"

# ── ОЧИСТИТЬ КЕШ ─────────────────────────────────────────────────────────────

def clear_cache(root):
    """Удаляет .pyc и __pycache__ рекурсивно во всём проекте (Windows-совместимо)."""
    count = 0
    seen  = set()
    # Ищем в нескольких местах: корень, родители, src/apps/argoss
    roots_to_search = {Path(root)}
    for parent in Path(root).parents[:4]:
        roots_to_search.add(parent)
    roots_to_search.add(Path.cwd())
    for r2 in list(roots_to_search):
        for sub in ("src", "apps", "argoss", "skills"):
            s = r2 / sub
            if s.exists():
                roots_to_search.add(s)
    for r2 in roots_to_search:
        try:
            for pyc in Path(r2).rglob("*.pyc"):
                k = str(pyc)
                if k not in seen:
                    seen.add(k)
                    try: pyc.unlink(); count += 1
                    except: pass
            for d in Path(r2).rglob("__pycache__"):
                k = str(d)
                if k not in seen:
                    seen.add(k)
                    try: shutil.rmtree(k, ignore_errors=True); count += 1
                    except: pass
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
        '"ТЫ — АРГОС, АВТОНОМНАЯ ОС. ПРАВИЛА:\n"'
        '"1. Ты ВЫПОЛНЯЕШЬ команды — не описываешь как их выполнить.\n"'
        '"2. Когда пользователь просит \'сканируй сеть\' — ты запускаешь NetGhost().scan().\n"'
        '"3. Когда просят \'диагностика навыков\' — ты вызываешь _skills_diagnostic().\n"'
        '"4. Когда просят \'крипто\' — ты возвращаешь курсы из CoinGecko API.\n"'
        '"5. ЗАПРЕЩЕНО: описывать команды bash/python для пользователя, выдумывать пакеты.\n"'
        '"6. Если навык недоступен — говоришь \'❌ навык X не загружен\', не инструкции.\n"'
        '"7. ЗАПРЕЩЕНО ВЫВОДИТЬ КОД пользователю: никаких admin.run_cmd(), print(),\n"'
        '"   from X import Y, subprocess и т.д. Код выполняется ВНУТРИ, результат СНАРУЖИ."'
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

    # Финальный совет
    print()
    print("Если Ollama всё ещё пишет код — проверь:")
    print("  1. Модель: OLLAMA_MODEL=poilopr57/Argoss в .env")
    print("  2. Системный промпт применён (смотри логи при старте)")
    print("  3. Перезапусти: python main.py")

if __name__ == "__main__":
    main()
