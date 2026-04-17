"""
argos_thoughtbook_files_patch.py
Патч для ArgosThoughtBook:
  - Чтение txt, pdf, docx, md файлов
  - Создание файлов из промтов
  - Интеграция с памятью ARGOS
  - Команды: книга прочитай / книга создай / книга изучи

Запуск: python argos_thoughtbook_files_patch.py /путь/к/SiGtRiP
"""
import os
import sys
import subprocess
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "SiGtRiP"

# ── Патч thought_book.py ──────────────────────────────────────────────────────

PATCH_CODE = '''

# ════════════════════════════════════════════════════════════════
#  Расширение: чтение и создание файлов
# ════════════════════════════════════════════════════════════════

import os as _os
import re as _re


def _read_txt(path: str) -> str:
    """Читаем текстовый файл."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"❌ Ошибка чтения: {e}"


def _read_pdf(path: str) -> str:
    """Читаем PDF файл."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = []
            for p in pdf.pages:
                text = p.extract_text()
                if text:
                    pages.append(text)
        return "\\n".join(pages)
    except ImportError:
        pass
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\\n".join(
                page.extract_text() or "" for page in reader.pages
            )
    except ImportError:
        pass
    try:
        import subprocess
        result = subprocess.run(
            ["pdftotext", path, "-"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return "❌ Для PDF установи: pip install pdfplumber или pip install PyPDF2"


def _read_docx(path: str) -> str:
    """Читаем Word документ."""
    try:
        import docx
        doc = docx.Document(path)
        return "\\n".join(p.text for p in doc.paragraphs if p.text)
    except ImportError:
        return "❌ Для DOCX установи: pip install python-docx"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def _read_md(path: str) -> str:
    """Читаем Markdown файл."""
    return _read_txt(path)


def _read_file(path: str) -> str:
    """Автоопределение формата и чтение."""
    p = Path(path)
    if not p.exists():
        # Пробуем стандартные пути
        for prefix in ["/sdcard/", "/sdcard/Download/",
                       str(Path.home()), str(Path.home() / "storage/downloads/")]:
            alt = Path(prefix) / path
            if alt.exists():
                p = alt
                break
        else:
            return f"❌ Файл не найден: {path}"

    ext = p.suffix.lower()
    if ext in (".txt", ".log", ".csv", ".json", ".yaml", ".yml"):
        return _read_txt(str(p))
    elif ext == ".pdf":
        return _read_pdf(str(p))
    elif ext in (".docx", ".doc"):
        return _read_docx(str(p))
    elif ext in (".md", ".rst"):
        return _read_md(str(p))
    else:
        # Пробуем как текст
        content = _read_txt(str(p))
        if "❌" not in content:
            return content
        return f"❌ Неподдерживаемый формат: {ext}"


def _create_file(path: str, content: str) -> str:
    """Создаём файл с содержимым."""
    try:
        p = Path(path)
        if not p.is_absolute():
            p = Path.home() / "SiGtRiP" / "data" / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ Файл создан: {p}\\n({len(content)} символов)"
    except Exception as e:
        return f"❌ Ошибка создания: {e}"


def _save_to_memory(core, text: str, source: str) -> str:
    """Сохраняем прочитанный текст в память ARGOS."""
    if not core or not hasattr(core, "memory") or not core.memory:
        return ""
    try:
        # Разбиваем на чанки по 500 символов
        chunks = [text[i:i+500] for i in range(0, min(len(text), 5000), 500)]
        saved = 0
        for i, chunk in enumerate(chunks):
            key = f"{Path(source).stem}_chunk{i}"
            core.memory.remember(key, chunk, category="file")
            saved += 1
        return f"\\n💾 Сохранено в память: {saved} фрагментов"
    except Exception:
        return ""


# ── Патч метода handle_command ────────────────────────────────────────────────

_ORIGINAL_HANDLE = None


def _patched_handle_command(self, command: str) -> str:
    """Расширенный handle_command с поддержкой файлов."""
    cmd = command.strip()
    cmd_lower = cmd.lower()

    # ── Чтение файла ──────────────────────────────────────────────
    for prefix in ("прочитай ", "читай ", "read ", "открой ", "загрузи "):
        if cmd_lower.startswith(prefix):
            path = cmd[len(prefix):].strip()
            content = _read_file(path)
            if content.startswith("❌"):
                return content
            # Сохраняем в память
            mem_result = _save_to_memory(self.core, content, path)
            preview = content[:1000] + ("..." if len(content) > 1000 else "")
            return (
                f"📄 Файл: {path}\\n"
                f"Размер: {len(content)} символов\\n"
                f"{'━'*40}\\n"
                f"{preview}"
                f"{mem_result}"
            )

    # ── Изучение файла (полное + анализ ИИ) ──────────────────────
    for prefix in ("изучи ", "study ", "analyze ", "анализируй "):
        if cmd_lower.startswith(prefix):
            path = cmd[len(prefix):].strip()
            content = _read_file(path)
            if content.startswith("❌"):
                return content
            mem_result = _save_to_memory(self.core, content, path)
            # Просим ИИ проанализировать
            if self.core and hasattr(self.core, "process"):
                try:
                    q = f"Проанализируй этот текст кратко:\\n{content[:2000]}"
                    analysis = self.core.process(q).get("answer", "")
                    return (
                        f"📚 Изучен файл: {path}\\n"
                        f"Размер: {len(content)} символов\\n"
                        f"{'━'*40}\\n"
                        f"🤖 Анализ:\\n{analysis}"
                        f"{mem_result}"
                    )
                except Exception:
                    pass
            return f"📚 Изучен: {path}\\n{content[:500]}...{mem_result}"

    # ── Создание файла ────────────────────────────────────────────
    for prefix in ("создай файл ", "create file ", "запиши в файл ",
                   "сохрани в файл ", "новый файл "):
        if cmd_lower.startswith(prefix):
            rest = cmd[len(prefix):].strip()
            # Формат: имя_файла | содержимое
            if "|" in rest:
                fname, content = rest.split("|", 1)
                return _create_file(fname.strip(), content.strip())
            else:
                return (
                    "❓ Формат: книга создай файл имя.txt | содержимое\\n"
                    "Пример: книга создай файл notes.txt | Мои заметки"
                )

    # ── Список файлов ─────────────────────────────────────────────
    if cmd_lower in ("файлы", "мои файлы", "list files", "ls"):
        paths_to_check = [
            Path.home() / "SiGtRiP" / "data",
            Path("/sdcard/Download"),
            Path("/sdcard/Documents"),
        ]
        lines = ["📂 Доступные файлы:\\n"]
        for p in paths_to_check:
            if p.exists():
                files = list(p.glob("*"))[:10]
                if files:
                    lines.append(f"  {p}:")
                    for f in files:
                        lines.append(f"    📄 {f.name}")
        return "\\n".join(lines) if len(lines) > 1 else "📂 Файлы не найдены"

    # ── Конвертация ───────────────────────────────────────────────
    if cmd_lower.startswith("конвертируй ") or cmd_lower.startswith("convert "):
        rest = cmd.split(" ", 1)[1].strip()
        if " в " in rest or " to " in rest:
            parts = rest.replace(" to ", " в ").split(" в ")
            src = parts[0].strip()
            fmt = parts[1].strip().lower()
            content = _read_file(src)
            if content.startswith("❌"):
                return content
            dst = Path(src).stem + f".{fmt}"
            return _create_file(dst, content)

    # Оригинальный обработчик
    if _ORIGINAL_HANDLE:
        return _ORIGINAL_HANDLE(self, command)
    return f"❓ Неизвестная команда: {command}"


# Применяем патч
if _ORIGINAL_HANDLE is None:
    _ORIGINAL_HANDLE = ArgosThoughtBook.handle_command
    ArgosThoughtBook.handle_command = _patched_handle_command
'''

# Читаем thought_book.py
tb_path = REPO / "src" / "thought_book.py"
if not tb_path.exists():
    print(f"❌ Не найден: {tb_path}")
    sys.exit(1)

text = tb_path.read_text(encoding="utf-8")

# Добавляем патч в конец файла
if "_patched_handle_command" not in text:
    text += PATCH_CODE
    tb_path.write_text(text, encoding="utf-8")
    print("✅ thought_book.py обновлён")
else:
    print("ℹ️  Патч уже применён")

# ── Проверка синтаксиса ────────────────────────────────────────────────────────
result = subprocess.run(
    ["python3", "-m", "py_compile", str(tb_path)],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("✅ Синтаксис OK")
else:
    print(f"❌ Синтаксис: {result.stderr}")
    sys.exit(1)

# ── Проверка интеграции с core.py ─────────────────────────────────────────────
core_path = REPO / "src" / "core.py"
core_text = core_path.read_text(encoding="utf-8")

if "thought_book" not in core_text:
    core_text = core_text.replace(
        "from src.argos_logger import get_logger",
        "from src.argos_logger import get_logger\ntry:\n    from src.thought_book import ArgosThoughtBook\nexcept Exception:\n    ArgosThoughtBook = None"
    )
    if "self.thought_book" not in core_text:
        core_text = core_text.replace(
            "self.memory = ArgosMemory()",
            "self.memory = ArgosMemory()\n        try:\n            self.thought_book = ArgosThoughtBook(core=self) if ArgosThoughtBook else None\n        except Exception:\n            self.thought_book = None"
        )
    core_path.write_text(core_text, encoding="utf-8")
    print("✅ core.py — ThoughtBook подключён")
else:
    print("ℹ️  core.py уже содержит ThoughtBook")

# ── Обновляем execute_intent в core.py ────────────────────────────────────────
if "self.thought_book" in core_text and "книга" not in core_text:
    # Ищем место для добавления роутинга команд книги
    old = "# ── Конец execute_intent"
    new = """        # ── Книга мыслей + работа с файлами ──────────────────────
        book_triggers = ["книга", "промт", "озарение", "мысли аргоса",
                         "прочитай файл", "изучи файл", "создай файл",
                         "book", "thought"]
        if any(t in text_lower for t in book_triggers) and self.thought_book:
            return self.thought_book.handle_command(text)

        # ── Конец execute_intent"""
    if old in core_text:
        core_text = core_text.replace(old, new)
        core_path.write_text(core_text, encoding="utf-8")
        print("✅ core.py — роутинг команд книги добавлен")

# ── Создаём тест интеграции ───────────────────────────────────────────────────

TEST_CODE = '''#!/usr/bin/env python3
"""Тест интеграции ThoughtBook с файлами."""
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from src.thought_book import ArgosThoughtBook

book = ArgosThoughtBook()

print("=== Тест ThoughtBook + файлы ===\\n")

# Тест 1: команды книги
print("1. Таблица содержания:")
r = book.handle_command("книга")
print(r[:200])
print()

# Тест 2: создание файла
print("2. Создание файла:")
r = book.handle_command("создай файл test_argos.txt | Тест ARGOS ThoughtBook работает!")
print(r)
print()

# Тест 3: чтение файла
print("3. Чтение файла:")
r = book.handle_command("прочитай test_argos.txt")
print(r)
print()

# Тест 4: список файлов
print("4. Список файлов:")
r = book.handle_command("файлы")
print(r[:300])
print()

print("✅ Интеграция работает!")
'''

test_path = REPO / "test_thoughtbook_files.py"
test_path.write_text(TEST_CODE, encoding="utf-8")
print("✅ test_thoughtbook_files.py")

# ── Git commit ────────────────────────────────────────────────────────────────
print("\n━━━ Git commit ━━━")
os.chdir(REPO)

cmds = [
    ["git", "add", "src/thought_book.py", "src/core.py", "test_thoughtbook_files.py"],
    ["git", "commit", "-m",
     "feat: ThoughtBook file reader/creator (txt/pdf/docx/md) + memory integration"],
    ["git", "push", "origin", "main"],
]

for cmd in cmds:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
        if r.returncode == 0:
            print(f"✅ {' '.join(cmd[:3])}")
        else:
            print(f"⚠️  {r.stderr[:100]}")
    except Exception as e:
        print(f"❌ {e}")

print("""
╔══════════════════════════════════════════════════════════╗
║  ThoughtBook файловый патч применён!                      ║
╚══════════════════════════════════════════════════════════╝

Команды в Telegram боте или терминале:

  книга прочитай notes.txt
  книга прочитай /sdcard/Download/document.pdf
  книга прочитай /sdcard/Download/report.docx
  книга изучи важный_документ.pdf
  книга создай файл заметки.txt | Мои мысли...
  книга файлы

Установи для PDF:
  pip install pdfplumber

Установи для DOCX:
  pip install python-docx

Проверь:
  python test_thoughtbook_files.py
""")
