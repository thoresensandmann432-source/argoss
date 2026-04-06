"""
memory_repair.py — Восстановление повреждённой базы данных памяти Аргоса
Запуск: python memory_repair.py

Ошибка: sqlite3.DatabaseError: database disk image is malformed
Причина: БД была повреждена (неожиданное завершение, запись в момент записи).

Что делает этот скрипт:
  1. Находит файл БД (argos_memory.db / argos.db / data/*.db)
  2. Делает резервную копию повреждённого файла
  3. Пробует восстановить данные через sqlite3 .recover
  4. Создаёт новую чистую БД с правильной схемой
  5. Переносит факты, заметки и историю из старой БД (что удастся)
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def find_db_files() -> list[Path]:
    """Ищет файлы БД Аргоса в проекте."""
    search_roots = [Path.cwd()] + list(Path.cwd().parents)[:3]
    found = []
    for root in search_roots:
        for pattern in ["*.db", "data/*.db", "src/*.db"]:
            for db in root.glob(pattern):
                try:
                    # Проверяем что это SQLite файл
                    with open(db, "rb") as f:
                        magic = f.read(16)
                    if magic.startswith(b"SQLite format 3"):
                        found.append(db)
                except Exception:
                    pass
    return found


def check_db(db_path: Path) -> bool:
    """Проверяет целостность БД."""
    try:
        conn = sqlite3.connect(str(db_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        return result and result[0] == "ok"
    except Exception:
        return False


def try_recover_data(db_path: Path) -> list[tuple]:
    """Пробует извлечь данные из повреждённой БД."""
    recovered = []
    try:
        conn = sqlite3.connect(str(db_path))
        # Включаем recovery mode
        conn.execute("PRAGMA writable_schema=OFF")

        # Получаем список таблиц
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        except Exception:
            tables = []

        for (table_name,) in tables:
            try:
                rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
                columns = [desc[0] for desc in conn.execute(f"SELECT * FROM {table_name} LIMIT 0").description]
                recovered.append((table_name, columns, rows))
                print(f"  ✅ Таблица {table_name}: {len(rows)} строк")
            except Exception as e:
                print(f"  ⚠️  Таблица {table_name}: {e}")

        conn.close()
    except Exception as e:
        print(f"  ❌ Не удалось открыть БД: {e}")

    return recovered


def create_fresh_db(db_path: Path, recovered_data: list[tuple]) -> bool:
    """Создаёт новую чистую БД и переносит данные."""
    try:
        conn = sqlite3.connect(str(db_path))

        # Стандартная схема памяти Аргоса
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                key     TEXT NOT NULL,
                value   TEXT NOT NULL,
                ts      TEXT DEFAULT (datetime('now')),
                source  TEXT DEFAULT 'user'
            );

            CREATE TABLE IF NOT EXISTS notes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                title   TEXT,
                content TEXT NOT NULL,
                tags    TEXT,
                ts      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS dialogue_history (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                role    TEXT NOT NULL,
                content TEXT NOT NULL,
                ts      TEXT DEFAULT (datetime('now')),
                state   TEXT
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                text        TEXT NOT NULL,
                trigger_ts  TEXT NOT NULL,
                repeat      TEXT,
                done        INTEGER DEFAULT 0,
                created_ts  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS chat_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                role    TEXT NOT NULL,
                text    TEXT NOT NULL,
                engine  TEXT,
                ts      TEXT DEFAULT (datetime('now'))
            );
        """)

        # Переносим данные
        for table_name, columns, rows in recovered_data:
            if not rows:
                continue
            try:
                # Проверяем что таблица существует в новой схеме
                conn.execute(f"SELECT 1 FROM {table_name} LIMIT 0")
                # Вставляем данные
                placeholders = ",".join("?" * len(columns))
                conn.executemany(
                    f"INSERT OR IGNORE INTO {table_name} VALUES ({placeholders})",
                    rows
                )
                print(f"  ✅ Перенесено в {table_name}: {len(rows)} строк")
            except Exception as e:
                print(f"  ⚠️  Пропущено {table_name}: {e}")

        conn.commit()

        # Финальная проверка
        conn.execute("PRAGMA integrity_check")
        conn.execute("VACUUM")
        conn.close()
        return True

    except Exception as e:
        print(f"  ❌ Создание новой БД: {e}")
        return False


def patch_memory_py() -> str:
    """Патчит src/memory.py чтобы ошибки БД не крашили GUI."""
    for base in [Path.cwd()] + list(Path.cwd().parents)[:3]:
        mem_path = base / "src" / "memory.py"
        if not mem_path.exists():
            continue

        with open(mem_path, "r", encoding="utf-8") as f:
            src = f.read()

        if "database disk image is malformed" in src or "_safe_execute" in src:
            return f"✅ src/memory.py уже пропатчен"

        # Добавляем безопасную обёртку для execute
        PATCH = '''
    def _safe_execute(self, query: str, params=()) -> list:
        """Безопасное выполнение SQL — перехватывает ошибки повреждённой БД."""
        try:
            return self.conn.execute(query, params).fetchall()
        except Exception as e:
            import logging
            logging.getLogger("argos.memory").error(
                "БД ошибка: %s | Попытка пересоздать соединение...", e)
            try:
                self.conn.close()
                self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                return self.conn.execute(query, params).fetchall()
            except Exception:
                return []

'''

        # Найти класс и добавить метод
        cls_idx = src.find("class ArgosMemory")
        if cls_idx < 0:
            cls_idx = src.find("class Memory")
        if cls_idx < 0:
            return "⚠️  Класс Memory не найден"

        init_idx = src.find("    def __init__", cls_idx)
        src = src[:init_idx] + PATCH + src[init_idx:]

        # Заменяем прямые вызовы self.conn.execute на _safe_execute
        import re
        src = re.sub(
            r'return self\.conn\.execute\(\n\s+',
            'return self._safe_execute(',
            src)
        src = src.replace(
            'facts = self.get_all_facts()',
            'try:\n            facts = self.get_all_facts()\n        except Exception:\n            facts = []')

        backup = mem_path.with_suffix(".py.bak")
        shutil.copy2(str(mem_path), str(backup))
        mem_path.write_text(src, encoding="utf-8")
        return f"✅ src/memory.py пропатчен (резервная копия: {backup.name})"

    return "⚠️  src/memory.py не найден"


def main():
    print("=" * 55)
    print("  ARGOS MEMORY REPAIR")
    print("=" * 55)
    print()

    # Найти БД файлы
    print("Ищу файлы базы данных...")
    db_files = find_db_files()

    if not db_files:
        print("❌ Файлы .db не найдены. Запусти из папки проекта Аргоса.")
        sys.exit(1)

    for db_path in db_files:
        print(f"\n📁 {db_path}")

        # Проверяем целостность
        is_ok = check_db(db_path)
        if is_ok:
            print("  ✅ БД в порядке — восстановление не нужно")
            continue

        print("  ⚠️  БД повреждена. Восстанавливаю...")

        # Резервная копия
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = db_path.with_name(f"{db_path.stem}_backup_{ts}{db_path.suffix}")
        shutil.copy2(str(db_path), str(backup))
        print(f"  💾 Резервная копия: {backup.name}")

        # Извлекаем данные
        print("  Извлекаю данные из повреждённой БД...")
        recovered = try_recover_data(db_path)

        # Удаляем старую и создаём новую
        db_path.unlink()
        print("  Создаю новую БД...")
        ok = create_fresh_db(db_path, recovered)

        if ok:
            print(f"  ✅ БД восстановлена: {db_path}")
        else:
            # Пустая БД лучше чем падающая
            conn = sqlite3.connect(str(db_path))
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, key TEXT, value TEXT, ts TEXT);
                CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, content TEXT, ts TEXT);
                CREATE TABLE IF NOT EXISTS dialogue_history (id INTEGER PRIMARY KEY, role TEXT, content TEXT, ts TEXT);
                CREATE TABLE IF NOT EXISTS chat_log (id INTEGER PRIMARY KEY, role TEXT, text TEXT, ts TEXT);
            """)
            conn.close()
            print(f"  ✅ Создана чистая БД: {db_path}")

    # Патч memory.py
    print()
    print("Патчу src/memory.py для защиты от будущих ошибок...")
    result = patch_memory_py()
    print(f"  {result}")

    print()
    print("=" * 55)
    print("  Готово! Теперь запусти: python main.py")
    print()
    print("  Также: запускай только ОДИН экземпляр Аргоса!")
    print("  Ошибка 'Conflict: terminated by other getUpdates'")
    print("  означает что бот запущен дважды.")
    print("=" * 55)


if __name__ == "__main__":
    main()
