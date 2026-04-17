"""
fix_db.py — Экстренное восстановление БД Аргоса
Запускать прямо на Windows: python fix_db.py
"""
import os, sys, shutil, sqlite3, glob
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent

def find_all_dbs():
    dbs = []
    for pattern in ["*.db", "data/*.db", "src/*.db"]:
        dbs += [Path(p) for p in glob.glob(str(ROOT/pattern))]
    for p in ROOT.rglob("*.db"):
        if p not in dbs and "backup" not in p.name and "bak" not in p.name:
            dbs.append(p)
    return dbs

def is_ok(path):
    try:
        conn = sqlite3.connect(str(path), timeout=3)
        r = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        return r and r[0] == "ok"
    except Exception:
        return False

def repair(path):
    print(f"\n🔧 Ремонт: {path}")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_name(f"{path.stem}_{ts}.bak.db")
    shutil.copy2(str(path), str(bak))
    print(f"  💾 Резерв: {bak.name}")

    # Попытка dump + restore
    sqlite3_exe = shutil.which("sqlite3")
    recovered = False
    if sqlite3_exe:
        try:
            import subprocess
            r = subprocess.run([sqlite3_exe, str(path), ".dump"],
                               capture_output=True, text=True, timeout=15)
            if r.stdout.strip():
                recovered_path = path.with_name(path.stem + "_rec.db")
                new_conn = sqlite3.connect(str(recovered_path))
                new_conn.executescript(r.stdout)
                new_conn.commit()
                new_conn.close()
                if is_ok(recovered_path):
                    path.unlink()
                    recovered_path.rename(path)
                    print("  ✅ Восстановлено из дампа")
                    recovered = True
                else:
                    recovered_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"  ⚠️  dump: {e}")

    if not recovered:
        print("  ⚠️  Создаю новую пустую БД")
        try:
            path.unlink()
        except Exception:
            pass
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL, value TEXT,
                category TEXT DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT, text TEXT, engine TEXT,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT, fire_at TIMESTAMP,
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, body TEXT, tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()
        print("  ✅ Новая БД создана")

dbs = find_all_dbs()
if not dbs:
    print("БД не найдены — создаю новую data/argos_memory.db")
    (ROOT/"data").mkdir(exist_ok=True)
    repair(ROOT/"data"/"argos_memory.db")
else:
    for db in dbs:
        if not is_ok(db):
            print(f"❌ Повреждена: {db}")
            repair(db)
        else:
            print(f"✅ OK: {db}")

print("\n✅ Готово. Перезапусти Аргос: python main.py")
