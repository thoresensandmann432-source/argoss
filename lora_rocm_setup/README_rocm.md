# ARGOS LoRA ROCm — Руководство

Железо: **RX 580 4GB (gfx803)** + **RX 560 4GB (gfx803)** + Vega11 (iGPU)  
ОС: Windows 11 + WSL2 (Ubuntu 22.04)

---

## Быстрый старт

```bash
# 1. Установка (один раз)
bash setup_rocm_wsl2.sh

# 2. Активация окружения
source ~/.bashrc

# 3. Тест (50 шагов)
python train_lora_rocm.py --quick

# 4. Полное обучение
python train_lora_rocm.py
```

---

## Конфигурация моделей

| Модель | VRAM | Скорость | Рекомендация |
|--------|------|----------|--------------|
| `meta-llama/Llama-3.2-1B-Instruct` | ~2GB | быстро | ✅ дефолт |
| `meta-llama/Llama-3.2-3B-Instruct` | ~4GB | средне | хорошее качество |
| `Qwen/Qwen2.5-0.5B-Instruct` | ~1GB | очень быстро | тест окружения |
| `Qwen/Qwen2.5-7B-Instruct` | ~6GB 4-bit | медленно | с двумя GPU |
| `meta-llama/Meta-Llama-3-8B-Instruct` | ~6GB 4-bit | медленно | требует 8GB+ |

```bash
# Сменить модель
python train_lora_rocm.py --model Qwen/Qwen2.5-0.5B-Instruct --quick
```

---

## Переменные окружения (ROCm)

```bash
# Обязательно для RX 580 / RX 560 (Polaris gfx803)
export HSA_OVERRIDE_GFX_VERSION=8.0.3
export ROCR_VISIBLE_DEVICES=0,1
export ROC_ENABLE_PRE_VEGA=1
export PATH="/opt/rocm/bin:$PATH"
```

> **Почему 8.0.3?** RX 580 — архитектура Polaris (gfx803).  
> ROCm 6.x официально не поддерживает gfx803, но `HSA_OVERRIDE_GFX_VERSION=8.0.3` заставляет ROCm работать с ним как с gfx900 (Vega). Это даёт ~70-80% производительности.

---

## Troubleshooting

### GPU не виден (`torch.cuda.is_available() == False`)

**Сценарий 1: HSA_OVERRIDE не применён**
```bash
echo $HSA_OVERRIDE_GFX_VERSION    # должно быть 8.0.3
source ~/.bashrc                  # если пусто — перезагрузи .bashrc
```

**Сценарий 2: Нужен reboot WSL2**
```powershell
# В PowerShell (Windows)
wsl --shutdown
wsl
```
После этого:
```bash
source ~/.bashrc
python -c "import torch; print(torch.cuda.is_available())"
```

**Сценарий 3: libhsa-runtime64 не найден**
```bash
sudo ldconfig
echo $LD_LIBRARY_PATH    # должно содержать /opt/rocm/lib
export LD_LIBRARY_PATH="/opt/rocm/lib:$LD_LIBRARY_PATH"
```

**Сценарий 4: GPU виден rocm-smi но не виден PyTorch**
```bash
rocm-smi                      # проверить GPU
pip install torch --index-url https://download.pytorch.org/whl/rocm6.0 --force-reinstall
```

**Сценарий 5: Ошибка "No kernel image is available"**
```bash
# Неверная GFX версия — попробуй другие значения:
export HSA_OVERRIDE_GFX_VERSION=9.0.0   # Vega10
export HSA_OVERRIDE_GFX_VERSION=9.0.6   # Vega20
export HSA_OVERRIDE_GFX_VERSION=10.3.0  # RDNA2 (не Polaris, но иногда работает)
```

**Сценарий 6: Permission denied /dev/kfd**
```bash
sudo usermod -aG video,render $USER
# Перелогинься или:
newgrp video
```

### OOM (нехватка VRAM)

**Уменьшить батч:**
```python
# В train_lora_rocm.py измени TRAIN_CONFIG:
TRAIN_CONFIG["per_device_train_batch_size"] = 1
TRAIN_CONFIG["gradient_accumulation_steps"] = 8
```

**Уменьшить MAX_SEQ_LEN:**
```python
MAX_SEQ_LEN = 256   # было 512
```

**Использовать более мелкую модель:**
```bash
python train_lora_rocm.py --model Qwen/Qwen2.5-0.5B-Instruct
```

**Уменьшить LoRA rank:**
```python
LORA_CONFIG["r"] = 8       # было 16
LORA_CONFIG["lora_alpha"] = 16  # было 32
```

### Мониторинг VRAM в реальном времени

```bash
# Терминал 1 — мониторинг
watch -n 1 rocm-smi --showmeminfo vram

# Терминал 2 — обучение
python train_lora_rocm.py --quick
```

Или через Python:
```python
import torch
print(f"VRAM использовано: {torch.cuda.memory_allocated(0) / 1024**2:.0f} MB")
print(f"VRAM зарезервировано: {torch.cuda.memory_reserved(0) / 1024**2:.0f} MB")
```

### bitsandbytes не работает на ROCm

```bash
# Собрать из исходников с поддержкой ROCm
pip uninstall bitsandbytes -y
pip install bitsandbytes --prefer-binary \
    --index-url https://jllllll.github.io/bitsandbytes-windows-webui
```

Или отключить квантизацию (при наличии достаточно VRAM):
```python
# В train_lora_rocm.py установи bnb_config = None принудительно
# и измени dtype:
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto",
)
```

---

## Интеграция с ARGOS

После обучения адаптер сохраняется в `../models/argos-lora-adapter/`.  
Для слияния с базовой моделью и конвертации в GGUF:

```bash
# Из корня проекта ARGOS
python src/argos_lora_trainer.py --step merge
python src/argos_lora_trainer.py --step convert
python src/argos_lora_trainer.py --step register
```

Или весь пайплайн:
```bash
python src/argos_lora_trainer.py  # запустит все шаги подряд
```

После этого `argos-v1:latest` обновится в Ollama.

---

## Использование своего датасета

Формат совместим с `data/evolver_dataset.jsonl`:

```jsonl
{"user": "вопрос или команда", "answer": "ответ АРГОСА на русском", "context": "...системный промпт..."}
```

```bash
python train_lora_rocm.py --dataset ../data/evolver_dataset.jsonl
```

Или используй `dataset_example.jsonl` как шаблон.

---

## Производительность (ориентировочно)

| Конфигурация | Скорость | Примечание |
|---|---|---|
| RX 580 4GB, Llama-3.2-1B 4-bit | ~8-12 it/s | норма |
| RX 580 + RX 560, Llama-3.2-1B 4-bit | ~14-18 it/s | device_map="auto" |
| RX 580 4GB, Qwen2.5-0.5B fp16 | ~20-30 it/s | маленькая модель |
| CPU (40GB RAM), Qwen2.5-0.5B | ~0.5 it/s | только для теста |
