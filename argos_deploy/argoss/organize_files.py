#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
organize_files.py — Организация файлов в корне репозитория ARGOS
=================================================================
Перемещает файлы из корня в правильные директории:
  - docs/   — документация, CHANGELOG, README-дополнения
  - scripts/ — утилиты сборки и обслуживания
  - docker/  — Dockerfile-варианты и сервисы
  - notebooks/ — Jupyter-ноутбуки
  - reports/   — отчёты и .txt файлы

Запуск: python organize_files.py [--project PATH]
"""
from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


# Файлы, которые ОСТАЮТСЯ в корне (не перемещаются)
KEEP_ROOT = {
    "main.py",
    "genesis.py",
    "README.md",
    "requirements.txt",
    ".env",
    ".env.example",
    ".gitignore",
    "docker-compose.yml",
    "Dockerfile",
    "pyproject.toml",
    "buildozer.spec",
    "buildozer_local.spec",
    "p4a_hook.py",
    "CHANGELOG.md",
    "LICENSE",
    "setup.cfg",
    "Makefile",
    "launch.sh",
    "launch.bat",
    "launch.ps1",
    "bump_version.py",
    "pack_archive.py",
    "status_report.py",
    "release_final.py",
    "health_check.py",
    "organize_files.py",
    "cleanup_repo.py",
    "awareness.py",
    "whisper_node.py",
    "ardware_intel.py",
    "hardware_intel.py",
    "telegram_bot.py",
    "index.html",
    "argos.spec",
}


@dataclass
class OrganizationResult:
    moved: list[str] = field(default_factory=list)
    root_files: list[str] = field(default_factory=list)
    root_dirs: list[str] = field(default_factory=list)


def _move_from_root(
    project_path: Path,
    src: str,
    dst_dir: str,
    moved: list[str],
) -> None:
    """Перемещает файл из корня проекта в dst_dir."""
    src_path = project_path / src
    if not src_path.exists() or not src_path.is_file():
        return

    dst_folder = project_path / dst_dir
    dst_folder.mkdir(parents=True, exist_ok=True)
    dst_path = dst_folder / src_path.name

    # Не перезаписывать существующие
    if dst_path.exists():
        return

    shutil.move(str(src_path), str(dst_path))
    moved.append(f"  📄 {src}  →  {dst_dir}/")


# ── Правила перемещения ───────────────────────────────────────────────────────

# Документация → docs/
_DOCS_FILES = [
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "QUICK_START.md",
    "QUICKSTART.md",
    "SECURITY.md",
    "METRICS.md",
    "RELEASE_NOTES_v1.3.md",
    "FINAL_REPORT.md",
    "APK_BUILD_REPORT.md",
    "AUDIT_FIXES_SUMMARY.md",
    "mkdocs.yml",
]

# Утилиты → scripts/
_SCRIPTS_FILES = [
    "build_apk.py",
    "build_exe.py",
    "setup_builder.py",
    "setup_secrets.py",
    "db_init.py",
    "check_readiness.py",
    "deploy.sh",
    "create_release.sh",
    "install_windows.bat",
    "run_windows.bat",
    "setup_argos.nsi",
    "setup_argos.exe",
    "trainer.py",
    "mypy.ini",
    ".flake8",
    ".pre-commit-config.yaml",
]

# Docker → docker/
_DOCKER_FILES = [
    "Dockerfile.windows",
    "argos.service",
]

# Ноутбуки → notebooks/
_NOTEBOOK_FILES = [
    "Untitled6.ipynb",
    "Argos_Master_Core_Part_1.ipynb",
    'Копия_блокнота_"Untitled7_ipynb".ipynb',
]

# Отчёты → reports/
_REPORTS_FILES = [
    "argos_startup_log.txt",
    ".coverage",
]


def organize_files(project: str | Path = ".") -> OrganizationResult:
    """
    Организует файлы в корне репозитория, перемещая их в нужные директории.

    Args:
        project: Путь к корню репозитория.

    Returns:
        OrganizationResult с информацией о перемещённых файлах.
    """
    project_path = Path(project).resolve()
    result = OrganizationResult()

    print("📁 Организация файлов...\n")

    # Явные перемещения
    for f in _DOCS_FILES:
        _move_from_root(project_path, f, "docs", result.moved)

    for f in _SCRIPTS_FILES:
        _move_from_root(project_path, f, "scripts", result.moved)

    for f in _DOCKER_FILES:
        _move_from_root(project_path, f, "docker", result.moved)

    for f in _NOTEBOOK_FILES:
        _move_from_root(project_path, f, "notebooks", result.moved)

    for f in _REPORTS_FILES:
        _move_from_root(project_path, f, "reports", result.moved)

    # Авто-перемещение по расширению (только из корня)
    for path in list(project_path.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name in KEEP_ROOT:
            continue
        if name.startswith("."):
            continue

        if path.suffix == ".ipynb":
            _move_from_root(project_path, name, "notebooks", result.moved)
        elif path.suffix == ".md" and name not in KEEP_ROOT:
            _move_from_root(project_path, name, "docs", result.moved)
        elif path.suffix == ".txt" and name not in {"requirements.txt"}:
            _move_from_root(project_path, name, "reports", result.moved)

    # Вывод результата
    for item in result.moved:
        print(item)

    print(f"\n{'═' * 50}")
    print("  📁 СТРУКТУРА КОРНЕВОЙ ДИРЕКТОРИИ")
    print(f"{'═' * 50}")

    result.root_files = sorted(
        f.name for f in project_path.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )
    result.root_dirs = sorted(
        d.name for d in project_path.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__"
    )

    print("\n  📄 Файлы в корне:")
    for file_name in result.root_files:
        tag = "⭐" if file_name in KEEP_ROOT else "📄"
        print(f"    {tag} {file_name}")

    print("\n  📁 Директории:")
    for directory in result.root_dirs:
        try:
            file_count = sum(len(files) for _, _, files in os.walk(project_path / directory))
        except Exception:
            file_count = 0
        print(f"    📂 {directory}/  ({file_count} файлов)")

    print(f"\n{'═' * 50}")
    print(f"  Перемещено: {len(result.moved)} файлов")
    print("  ✅ Готово!")
    print(f"{'═' * 50}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="ARGOS file organizer")
    parser.add_argument(
        "--project",
        default=".",
        help="Путь к корню репозитория (default: .)",
    )
    args = parser.parse_args()
    organize_files(args.project)


if __name__ == "__main__":
    main()
