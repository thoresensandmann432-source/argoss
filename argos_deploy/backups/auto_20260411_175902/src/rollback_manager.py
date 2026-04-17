from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RollbackRecord:
    patch_id: str
    target_file: str
    backup_file: str
    created_at: float


class RollbackManager:
    def __init__(
        self,
        backup_root: str = ".argos_patch_backups",
        state_file: str = ".argos_patch_backups/rollback_state.json",
    ):
        self.backup_root = Path(backup_root)
        self.state_file = Path(state_file)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.records: list[RollbackRecord] = self._load()

    def _load(self) -> list[RollbackRecord]:
        if not self.state_file.exists():
            return []
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return [RollbackRecord(**item) for item in data]
        except Exception:
            return []

    def _save(self) -> None:
        self.state_file.write_text(
            json.dumps([asdict(r) for r in self.records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def backup_file(self, patch_id: str, file_path: str) -> str:
        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(file_path)
        ts = int(time.time())
        dst = self.backup_root / f"{src.name}.{patch_id}.{ts}.bak"
        shutil.copy2(src, dst)
        rec = RollbackRecord(
            patch_id=patch_id,
            target_file=str(src),
            backup_file=str(dst),
            created_at=time.time(),
        )
        self.records.append(rec)
        self._save()
        return str(dst)

    def rollback_patch(self, patch_id: str) -> bool:
        candidates = [r for r in self.records if r.patch_id == patch_id]
        if not candidates:
            return False
        for rec in reversed(candidates):
            src = Path(rec.backup_file)
            dst = Path(rec.target_file)
            if src.exists():
                shutil.copy2(src, dst)
        return True

    def rollback_last(self) -> bool:
        if not self.records:
            return False
        last_patch_id = self.records[-1].patch_id
        return self.rollback_patch(last_patch_id)

    def last_patch_id(self) -> Optional[str]:
        if not self.records:
            return None
        return self.records[-1].patch_id
