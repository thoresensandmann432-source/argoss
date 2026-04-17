"""
src/launch_config.py — Нормализация аргументов запуска ARGOS
=============================================================
Обрабатывает флаги командной строки перед передачей в ArgosOrchestrator.
"""

from __future__ import annotations

__all__ = ["normalize_launch_args"]


def normalize_launch_args(args: list[str]) -> list[str]:
    """
    Нормализует аргументы запуска.

    Правила:
    - ``--full`` разворачивается в ``--full --dashboard --wake``
      (без дублирования уже существующих флагов)
    - Остальные аргументы передаются без изменений.

    Args:
        args: Список аргументов (обычно ``sys.argv``).

    Returns:
        Нормализованный список аргументов.

    Examples:
        >>> normalize_launch_args(["prog", "--full"])
        ['prog', '--full', '--dashboard', '--wake']

        >>> normalize_launch_args(["prog", "--full", "--wake"])
        ['prog', '--full', '--wake', '--dashboard']

        >>> normalize_launch_args(["prog", "--no-gui"])
        ['prog', '--no-gui']
    """
    result = list(args)

    if "--full" in result:
        for extra in ("--dashboard", "--wake"):
            if extra not in result:
                result.append(extra)

    return result
