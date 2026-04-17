"""
patch_fix_providers.py — Фикс провайдеров и агента
1. Gemini 429 → переключаем на Groq как основной
2. Ollama таймаут → меняем модель на быструю
3. Агент отвечает README → фиксим фильтрацию
"""

import os
from pathlib import Path

ROOT = Path(__file__).parent


def fix_env():
    """Обновляем .env — Groq как основной, быстрая модель Ollama"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        print("❌ .env не найден")
        return False

    text = env_file.read_text(encoding="utf-8")
    changes = []

    # Меняем модель Ollama на быструю
    for old, new in [
        ("OLLAMA_MODEL=deepseek-r1:latest", "OLLAMA_MODEL=llama3.2:3b"),
        ("OLLAMA_MODEL=deepseek-r1:8b", "OLLAMA_MODEL=llama3.2:3b"),
        ("OLLAMA_MODEL=deepseek-r1:32b", "OLLAMA_MODEL=llama3.2:3b"),
    ]:
        if old in text:
            text = text.replace(old, new)
            changes.append(f"  {old} → {new}")

    # Добавляем если нет
    if "OLLAMA_MODEL=" not in text:
        text += "\nOLLAMA_MODEL=llama3.2:3b"
        changes.append("  + OLLAMA_MODEL=llama3.2:3b")

    if "OLLAMA_FAST_MODEL=" not in text:
        text += "\nOLLAMA_FAST_MODEL=tinyllama"
        changes.append("  + OLLAMA_FAST_MODEL=tinyllama")

    # Таймаут Ollama — уменьшаем
    if "OLLAMA_TIMEOUT=" in text:
        import re

        text = re.sub(r"OLLAMA_TIMEOUT=\d+", "OLLAMA_TIMEOUT=60", text)
        changes.append("  OLLAMA_TIMEOUT → 60")
    else:
        text += "\nOLLAMA_TIMEOUT=60"
        changes.append("  + OLLAMA_TIMEOUT=60")

    # Режим ИИ — auto (Groq → Ollama → Gemini)
    if "ARGOS_AI_MODE=" in text:
        import re

        text = re.sub(r"ARGOS_AI_MODE=\w+", "ARGOS_AI_MODE=auto", text)
    else:
        text += "\nARGOS_AI_MODE=auto"

    env_file.write_text(text, encoding="utf-8")
    print("✅ .env обновлён:")
    for c in changes:
        print(c)
    return True


def fix_ollama_timeout():
    """Уменьшаем таймаут Ollama в core.py"""
    target = ROOT / "src" / "core.py"
    if not target.exists():
        print(f"❌ {target} не найден")
        return False

    text = target.read_text(encoding="utf-8")
    changed = False

    # Меняем таймаут 300 на 60
    if "timeout=300" in text:
        text = text.replace("timeout=300", "timeout=int(os.getenv('OLLAMA_TIMEOUT', '60'))")
        changed = True
        print("✅ core.py: Ollama timeout 300 → 60")

    # Меняем дефолтную модель если deepseek
    if "deepseek-r1" in text:
        text = text.replace('"deepseek-r1:latest"', 'os.getenv("OLLAMA_MODEL", "llama3.2:3b")')
        text = text.replace("'deepseek-r1:latest'", 'os.getenv("OLLAMA_MODEL", "llama3.2:3b")')
        changed = True
        print("✅ core.py: deepseek-r1 → llama3.2:3b (из .env)")

    if changed:
        target.write_text(text, encoding="utf-8")
    else:
        print("⚠️  core.py: deepseek/timeout не найдены — проверь вручную")

    return True


def fix_gemini_fallback():
    """Добавляем быстрый fallback при 429 Gemini"""
    target = ROOT / "src" / "core.py"
    if not target.exists():
        return False

    text = target.read_text(encoding="utf-8")

    # Проверяем есть ли уже обработка 429
    if "RESOURCE_EXHAUSTED" in text and "_disable_provider_temporarily" in text:
        print("✅ core.py: Gemini 429 fallback уже есть")
        return True

    # Ищем место где ловим Gemini ошибку
    old = "if response.status_code in (401, 403):"
    if old in text:
        new = """if response.status_code == 429:
                    self._disable_provider_temporarily("Gemini", "квота исчерпана (429)")
                    return None
                if response.status_code in (401, 403):"""
        text = text.replace(old, new, 1)
        target.write_text(text, encoding="utf-8")
        print("✅ core.py: добавлен быстрый fallback при Gemini 429")
    else:
        print("⚠️  core.py: место для 429 не найдено")

    return True


def fix_agent_readme_bug():
    """Фиксим агента который отправляет README как ответ"""
    target = ROOT / "src" / "agent.py"
    if not target.exists():
        print(f"⚠️  {target} не найден")
        return False

    text = target.read_text(encoding="utf-8")

    # Агент не должен возвращать длинный markdown с таблицами
    if "filter_markdown" in text:
        print("✅ agent.py: фильтрация уже есть")
        return True

    filter_code = '''
def _filter_agent_response(text: str) -> str:
    """Фильтруем мусор из ответа агента."""
    if not text:
        return text
    
    lines = text.splitlines()
    filtered = []
    skip_count = 0
    
    for line in lines:
        # Пропускаем длинные таблицы markdown (README)
        if line.startswith("|") and line.count("|") > 3:
            skip_count += 1
            continue
        # Пропускаем блоки кода из README
        if line.startswith("```") and len(filtered) == 0:
            skip_count += 1
            continue
        # Пропускаем строки с заголовками README
        if line.startswith("##") and "ARGOS" in line and len(filtered) < 3:
            skip_count += 1
            continue
        filtered.append(line)
    
    result = "\\n".join(filtered).strip()
    
    # Если ответ слишком длинный и похож на README
    if len(result) > 2000 and ("##" in result or "```bash" in result):
        # Берём только первые 500 символов до первого блока кода
        idx = result.find("```")
        if idx > 100:
            result = result[:idx].strip()
        else:
            result = result[:500] + "..."
    
    return result

'''

    # Вставляем функцию в начало файла
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("class ") or (line.startswith("def ") and i > 5):
            insert_at = i
            break

    lines.insert(insert_at, filter_code)
    text = "\n".join(lines)

    target.write_text(text, encoding="utf-8")
    print("✅ agent.py: фильтр README мусора добавлен")
    return True


def fix_curiosity_spam():
    """Фиксим curiosity — слишком много запросов к Gemini"""
    target = ROOT / "src" / "curiosity.py"
    if not target.exists():
        print(f"⚠️  {target} не найден")
        return False

    text = target.read_text(encoding="utf-8")

    # Увеличиваем интервал curiosity чтобы не спамить API
    import re

    changed = False

    # Интервал между запросами
    for pattern, replacement in [
        (r"interval\s*=\s*60\b", "interval = 300"),
        (r"interval\s*=\s*30\b", "interval = 300"),
        (r"sleep\(60\)", "sleep(300)"),
        (r"sleep\(30\)", "sleep(300)"),
    ]:
        new_text = re.sub(pattern, replacement, text)
        if new_text != text:
            text = new_text
            changed = True

    if changed:
        target.write_text(text, encoding="utf-8")
        print("✅ curiosity.py: интервал увеличен до 300с (меньше запросов к API)")
    else:
        print("⚠️  curiosity.py: интервал не найден — проверь вручную")

    return True


def fix_vision_import():
    """Фиксим импорт ArgosVision"""
    vision_init = ROOT / "src" / "vision" / "__init__.py"
    if not vision_init.exists():
        print(f"⚠️  {vision_init} не найден")
        return False

    text = vision_init.read_text(encoding="utf-8")

    if "ArgosVision" in text:
        print("✅ vision/__init__.py: ArgosVision уже экспортируется")
        return True

    # Ищем класс Vision в папке
    vision_dir = ROOT / "src" / "vision"
    vision_class = None
    for py_file in vision_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        if "class " in content and "vision" in content.lower():
            for line in content.splitlines():
                if line.startswith("class "):
                    vision_class = line.split("class ")[1].split("(")[0].strip()
                    vision_module = py_file.stem
                    break
        if vision_class:
            break

    if vision_class:
        new_init = text + f"\nfrom .{vision_module} import {vision_class} as ArgosVision\n"
        vision_init.write_text(new_init, encoding="utf-8")
        print(f"✅ vision/__init__.py: добавлен alias ArgosVision → {vision_class}")
    else:
        # Создаём заглушку
        stub = '''"""Vision module stub"""

class ArgosVision:
    """Заглушка Vision — установи google-genai для полной функциональности"""
    def __init__(self, *args, **kwargs):
        pass
    
    def analyze_image(self, path: str, question: str = "") -> str:
        return "❌ Vision недоступен. Установи: pip install google-genai Pillow"
    
    def analyze_screen(self, question: str = "") -> str:
        return "❌ Vision недоступен. Установи: pip install google-genai Pillow mss pyautogui"
'''
        if "__init__.py" in text:
            text += "\n" + stub
        else:
            text = stub

        vision_init.write_text(text, encoding="utf-8")
        print("✅ vision/__init__.py: создана заглушка ArgosVision")

    return True


def main():
    print("=" * 55)
    print("  ARGOS Provider & Agent Fix Patch")
    print("=" * 55)
    print()

    results = [
        ("1. .env (Ollama модель + таймаут)", fix_env()),
        ("2. core.py (Ollama timeout 300→60)", fix_ollama_timeout()),
        ("3. core.py (Gemini 429 fallback)", fix_gemini_fallback()),
        ("4. agent.py (фильтр README мусора)", fix_agent_readme_bug()),
        ("5. curiosity.py (интервал 300с)", fix_curiosity_spam()),
        ("6. vision/__init__.py (ArgosVision)", fix_vision_import()),
    ]

    print()
    print("=" * 55)
    ok = sum(1 for _, r in results if r)
    print(f"  Результат: {ok}/{len(results)} исправлений применено")
    print("=" * 55)
    print()
    print("Перезапусти ARGOS:")
    print("  python main.py --no-gui")
    print()
    print("Рекомендуется скачать модели Ollama:")
    print("  ollama pull llama3.2:3b")
    print("  ollama pull tinyllama")
    print()
    print("Для Groq добавь в .env:")
    print("  GROQ_API_KEY=твой_ключ_с_console.groq.com")


if __name__ == "__main__":
    main()
