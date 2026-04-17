from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


def prompt_hash(prompt: str) -> str:
    return hashlib.md5((prompt or "").encode("utf-8")).hexdigest()[:12]


def ensure_output_dir(path: str | Path) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_generation_record(
    db_path: str | Path,
    prompt: str,
    negative_prompt: str,
    model_name: str,
    file_path: str,
    width: int,
    height: int,
    steps: int,
) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generated_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                prompt TEXT,
                negative_prompt TEXT,
                model_name TEXT,
                file_path TEXT,
                width INTEGER,
                height INTEGER,
                steps INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO generated_images
            (prompt, negative_prompt, model_name, file_path, width, height, steps)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (prompt, negative_prompt, model_name, file_path, width, height, steps),
        )
        conn.commit()

