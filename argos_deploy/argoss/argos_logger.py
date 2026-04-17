"""
src/argos_logger.py — Единый логгер проекта ARGOS
==================================================
Предоставляет именованные логгеры с настраиваемым уровнем.
setup_debug_logging() подключает RotatingFileHandler для детального лога.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

__all__ = ["get_logger", "setup_debug_logging"]

# Уже добавленные файловые обработчики (для идемпотентности)
_file_handlers: dict[str, RotatingFileHandler] = {}


def get_logger(name: str) -> logging.Logger:
    """
    Возвращает именованный логгер с единым форматом.

    Уровень задаётся через переменную окружения ``ARGOS_LOG_LEVEL``
    (по умолчанию INFO). Повторный вызов с тем же именем возвращает
    тот же объект без дублирования обработчиков.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)

    level_name = os.getenv("ARGOS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    return logger


def setup_debug_logging(
    log_dir: str = "logs",
    log_file: str = "argos_debug.log",
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> str:
    """
    Подключает RotatingFileHandler к корневому логгеру.

    Идемпотентен — повторный вызов с теми же параметрами
    не добавляет дублирующих обработчиков.

    Путь к файлу может быть переопределён переменной окружения
    ``ARGOS_DEBUG_LOG_FILE``.

    Args:
        log_dir:      Директория для лог-файла (создаётся автоматически).
        log_file:     Имя файла.
        max_bytes:    Максимальный размер файла до ротации (5 МБ по умолчанию).
        backup_count: Количество архивных копий.

    Returns:
        Абсолютный путь к лог-файлу.
    """
    # Переменная окружения имеет приоритет
    env_path = os.environ.get("ARGOS_DEBUG_LOG_FILE", "").strip()
    if env_path:
        full_path = str(Path(env_path).resolve())
    else:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        full_path = str((Path(log_dir) / log_file).resolve())

    root = logging.getLogger()

    # Проверяем, не добавлен ли уже такой обработчик
    for h in root.handlers:
        if isinstance(h, RotatingFileHandler) and h.baseFilename == full_path:
            return full_path

    # Создаём директорию если нужно
    Path(full_path).parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        full_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    _file_handlers[full_path] = handler
    return full_path
