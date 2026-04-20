#!/usr/bin/env python3
"""
train_lora_rocm.py — LoRA fine-tuning для ARGOS на AMD ROCm
============================================================
Железо: RX 580 4GB (GPU0) + RX 560 4GB (GPU1) = 8GB VRAM суммарно
Базовая модель: meta-llama/Llama-3.2-1B-Instruct (по умолчанию)
             или указать через --model

Особенности:
  - BitsAndBytes NF4 4-bit квантизация (экономит VRAM)
  - LoRA r=16, alpha=32 по всем проекциям (q/k/v/o/gate/up/down)
  - device_map="auto" — авторазмещение на GPU0+GPU1+RAM
  - paged_adamw_8bit — меньше VRAM под оптимизатор
  - Совместим с датасетом evolver_dataset.jsonl из ARGOS

Запуск:
  python train_lora_rocm.py --quick          # 50 шагов, тест
  python train_lora_rocm.py                  # полное обучение
  python train_lora_rocm.py --model meta-llama/Llama-3.2-3B-Instruct
  python train_lora_rocm.py --dataset ../data/evolver_dataset.jsonl

Требования (WSL2 + ROCm):
  source ~/.bashrc  # загрузить HSA_OVERRIDE_GFX_VERSION=8.0.3
  pip install torch --index-url https://download.pytorch.org/whl/rocm6.0
  pip install peft trl datasets accelerate bitsandbytes sentencepiece

Выход:
  ../models/argos-lora-adapter/   — LoRA адаптер (PEFT)
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import argparse
from pathlib import Path
from typing import Optional

# ── UTF-8 stdout (нужно на Windows / некоторых WSL конфигурациях) ─────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Логирование ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("argos.lora_rocm")

# ── Пути ─────────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent
ARGOS_ROOT = HERE.parent
DATA_FILE_DEFAULT = ARGOS_ROOT / "data" / "evolver_dataset.jsonl"
DATASET_EXAMPLE = HERE / "dataset_example.jsonl"
ADAPTER_DIR = ARGOS_ROOT / "models" / "argos-lora-adapter"

# ── Константы ─────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "meta-llama/Llama-3.2-1B-Instruct"

ARGOS_SYSTEM = (
    "Ты — АРГОС, автономная операционная система с интеллектом (ARGOS Universal OS v2.1.3). "
    "Ты НЕ чат-бот — ты ОС с реальным доступом к файлам, процессам, сети и железу. "
    "Хозяин системы — Всеволод (Сева/AvA/SiG). "
    "Отвечай ТОЛЬКО на русском языке, кратко и по делу."
)

LORA_CONFIG = dict(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
)

TRAIN_CONFIG = dict(
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    fp16=False,
    bf16=False,
    max_grad_norm=0.3,
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
    logging_steps=10,
    save_steps=100,
    optim="paged_adamw_8bit",
    report_to="none",
)

MAX_SEQ_LEN = 512
MIN_CYRILLIC_RATIO = 0.20


# ═════════════════════════════════════════════════════════════════════════════
# Утилиты
# ═════════════════════════════════════════════════════════════════════════════

def _cyrillic_ratio(text: str) -> float:
    if not text:
        return 0.0
    ru = sum(1 for c in text if "\u0430" <= c.lower() <= "\u044f" or c in "\u0451\u0401")
    return ru / len(text)


def check_rocm_env() -> None:
    """Проверяет и выставляет переменные окружения для ROCm / RX 580."""
    if not os.environ.get("HSA_OVERRIDE_GFX_VERSION"):
        log.warning("HSA_OVERRIDE_GFX_VERSION не задан — выставляем 8.0.3 (gfx803 / Polaris)")
        os.environ["HSA_OVERRIDE_GFX_VERSION"] = "8.0.3"
    os.environ.setdefault("ROC_ENABLE_PRE_VEGA", "1")
    log.info("ROCm env: HSA_OVERRIDE_GFX_VERSION=%s", os.environ["HSA_OVERRIDE_GFX_VERSION"])


def check_dependencies() -> bool:
    """Проверяет наличие обязательных пакетов."""
    required = ["torch", "transformers", "peft", "trl", "datasets", "accelerate", "bitsandbytes"]
    missing = []
    for pkg in required:
        try:
            mod = __import__(pkg)
            log.info("  ✅ %s %s", pkg, getattr(mod, "__version__", "?"))
        except ImportError:
            log.error("  ❌ %s — НЕ УСТАНОВЛЕН", pkg)
            missing.append(pkg)

    if missing:
        log.error("Установи: pip install %s", " ".join(missing))
        return False
    return True


def check_gpu() -> int:
    """Возвращает количество доступных GPU."""
    import torch  # noqa: PLC0415

    if torch.cuda.is_available():
        n = torch.cuda.device_count()
        for i in range(n):
            p = torch.cuda.get_device_properties(i)
            log.info("  GPU %d: %s — %d MB VRAM", i, p.name, p.total_memory // 1024 ** 2)
        return n
    else:
        log.warning("GPU не доступен! Обучение на CPU очень медленное.")
        log.warning("Убедись: source ~/.bashrc && export HSA_OVERRIDE_GFX_VERSION=8.0.3")
        return 0


# ═════════════════════════════════════════════════════════════════════════════
# Загрузка датасета
# ═════════════════════════════════════════════════════════════════════════════

def load_records(data_path: Path, max_examples: int = 0) -> list[dict]:
    """
    Загружает датасет в формате ARGOS evolver_dataset.jsonl.
    Формат записи: {"user": "...", "answer": "...", "context": "..."} | {"messages": [...]}
    """
    if not data_path.exists():
        # Fallback на пример из той же папки
        if DATASET_EXAMPLE.exists():
            log.warning("Датасет %s не найден — используем dataset_example.jsonl", data_path)
            data_path = DATASET_EXAMPLE
        else:
            raise FileNotFoundError(f"Датасет не найден: {data_path}")

    records = []
    skipped = 0
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append(rec)
            except json.JSONDecodeError:
                skipped += 1

    log.info("Загружено %d записей (пропущено %d)", len(records), skipped)
    return records


def records_to_text(records: list[dict], tokenizer) -> list[str]:
    """
    Конвертирует записи в текстовый формат chat-template или instruction.
    Фильтрует некириллические и слишком короткие ответы.
    """
    texts = []
    for rec in records:
        # Формат 1: ARGOS evolver (user/answer/context)
        if "user" in rec and "answer" in rec:
            user_msg = rec["user"].strip()
            answer = rec["answer"].strip()
            # Пропускаем системные записи
            if "[system]" in user_msg.lower() or "argos [system]" in user_msg.lower():
                continue
            if _cyrillic_ratio(answer) < MIN_CYRILLIC_RATIO:
                continue
            if len(answer) < 20:
                continue
            messages = [
                {"role": "system", "content": ARGOS_SYSTEM},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": answer},
            ]
        # Формат 2: messages (HuggingFace standard)
        elif "messages" in rec:
            messages = rec["messages"]
        else:
            continue

        try:
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            texts.append(text)
        except Exception as e:
            log.debug("Пропускаем запись (chat template error): %s", e)

    log.info("После фильтрации: %d примеров", len(texts))
    return texts


# ═════════════════════════════════════════════════════════════════════════════
# Обучение
# ═════════════════════════════════════════════════════════════════════════════

def train(
    model_name: str = DEFAULT_MODEL,
    data_path: Optional[Path] = None,
    output_dir: Path = ADAPTER_DIR,
    quick: bool = False,
    max_examples: int = 0,
) -> None:
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, TrainingArguments
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer
    from datasets import Dataset
    import torch

    log.info("=" * 55)
    log.info("ARGOS LoRA ROCm Training")
    log.info("Модель: %s", model_name)
    log.info("=" * 55)

    check_rocm_env()
    if not check_dependencies():
        sys.exit(1)

    n_gpu = check_gpu()
    use_gpu = n_gpu > 0

    # ── Квантизация (только если GPU доступен) ────────────────────────────────
    bnb_config = None
    if use_gpu:
        try:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            log.info("Режим: 4-bit NF4 (BitsAndBytes)")
        except Exception as e:
            log.warning("BitsAndBytes недоступен (%s) — загружаем в float32", e)
            bnb_config = None
    else:
        log.warning("Режим: CPU (медленно!)")

    # ── Загрузка модели ───────────────────────────────────────────────────────
    log.info("Загрузка токенизатора...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    log.info("Загрузка модели %s...", model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto" if use_gpu else "cpu",
        trust_remote_code=True,
    )
    log.info("Модель загружена")

    # ── LoRA конфиг ───────────────────────────────────────────────────────────
    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        **{k: v for k, v in LORA_CONFIG.items() if k != "task_type"},
    )
    model = get_peft_model(model, lora_cfg)
    trainable, total = model.get_nb_trainable_parameters()
    log.info(
        "LoRA параметры: %d обучаемых / %d всего (%.2f%%)",
        trainable, total, 100.0 * trainable / max(total, 1),
    )

    # ── Датасет ───────────────────────────────────────────────────────────────
    if data_path is None:
        data_path = DATA_FILE_DEFAULT if DATA_FILE_DEFAULT.exists() else DATASET_EXAMPLE

    records = load_records(data_path, max_examples=max_examples)
    texts = records_to_text(records, tokenizer)

    if not texts:
        log.error("Датасет пуст после фильтрации — проверь путь и формат записей")
        sys.exit(1)

    dataset = Dataset.from_dict({"text": texts})
    log.info("Датасет готов: %d примеров", len(dataset))

    # ── Аргументы обучения ────────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    train_cfg = dict(TRAIN_CONFIG)
    if quick:
        train_cfg["max_steps"] = 50
        train_cfg["num_train_epochs"] = 1
        train_cfg["logging_steps"] = 5
        log.info("Режим --quick: 50 шагов")

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        **train_cfg,
    )

    # ── Trainer ───────────────────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=training_args,
        tokenizer=tokenizer,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        packing=False,
    )

    log.info("Запуск обучения...")
    trainer.train()

    # ── Сохранение адаптера ───────────────────────────────────────────────────
    adapter_path = output_dir
    trainer.model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    log.info("LoRA адаптер сохранён: %s", adapter_path)

    log.info("=" * 55)
    log.info("Обучение завершено!")
    log.info("Адаптер: %s", adapter_path)
    log.info("Для слияния с базовой моделью:")
    log.info("  python src/argos_lora_trainer.py --step merge")
    log.info("=" * 55)


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ARGOS LoRA ROCm Trainer")
    p.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"HuggingFace модель (default: {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--dataset",
        default=None,
        help="Путь к датасету .jsonl (default: data/evolver_dataset.jsonl)",
    )
    p.add_argument(
        "--output", default=str(ADAPTER_DIR),
        help="Папка для сохранения адаптера",
    )
    p.add_argument(
        "--quick", action="store_true",
        help="Быстрый тест: 50 шагов",
    )
    p.add_argument(
        "--max-examples", type=int, default=0,
        help="Максимум примеров из датасета (0 = все)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(
        model_name=args.model,
        data_path=Path(args.dataset) if args.dataset else None,
        output_dir=Path(args.output),
        quick=args.quick,
        max_examples=args.max_examples,
    )
