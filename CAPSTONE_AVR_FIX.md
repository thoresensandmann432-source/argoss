# 🐦 Исправление: Capstone/Keystone AVR устарел

## Проблема
```
AttributeError: module 'capstone' has no attribute 'CS_ARCH_AVR'
AttributeError: module 'keystone' has no attribute 'KS_ARCH_AVR'
```

## Причина
В **Capstone 5.0** и **Keystone 0.9.2** архитектура **AVR устарела и удалена** из основных констант.

## Исправленные файлы

### 1. `src/connectivity/colibri_daemon.py`
```python
# AVR удалён в Capstone 5.0 — проверяем наличие
if hasattr(cs_mod, 'CS_ARCH_AVR'):
    _CS_ARCHS["avr"] = (cs_mod.CS_ARCH_AVR, cs_mod.CS_MODE_AVR)
```

### 2. `colibri_daemon.py` (root)
```python
# AVR удалён в Capstone 5.0 — проверяем наличие
if hasattr(cs_mod, 'CS_ARCH_AVR'):
    _CS_ARCHS["avr"] = (cs_mod.CS_ARCH_AVR, cs_mod.CS_MODE_AVR)
```

### 3. `src/firmware_builder.py`
```python
# Keystone — AVR проверка
if hasattr(ks_mod, 'KS_ARCH_AVR'):
    KS_ARCH_MAP["avr"] = (ks_mod.KS_ARCH_AVR, ks_mod.KS_MODE_AVR32)

# Capstone — AVR проверка
if hasattr(capstone, 'CS_ARCH_AVR'):
    CS_ARCH_MAP["avr"] = (capstone.CS_ARCH_AVR, capstone.CS_MODE_AVR)

# WEARABLE_ARCH — ссылки на avr/arduino удалены
if "avr" not in CS_ARCH_MAP and "avr" in WEARABLE_ARCH:
    del WEARABLE_ARCH["avr"]
if "avr" not in CS_ARCH_MAP and "arduino" in WEARABLE_ARCH:
    del WEARABLE_ARCH["arduino"]
```

## Результат
```
✅ colibri_daemon — OK
✅ firmware_builder — OK

CS_ARCH_MAP: ['x86', 'x86_64', 'arm', 'arm_thumb', 'arm64', 'mips']
KS_ARCH_MAP: ['x86', 'x86_64', 'arm', 'arm_thumb', 'arm64', 'mips']
WEARABLE_ARCH: ['esp32', 'esp8266', 'stm32', 'nrf52', 'rp2040', 'samd21', 'samd51']
```

## Примечание
- **ARM** (включая Thumb) — работает ✅
- **x86/x86_64** — работает ✅
- **MIPS** — работает ✅
- **AVR/Arduino** — недоступно в Capstone 5.0+ ❌

Для AVR/Arduino используйте внешние инструменты: `avr-gcc`, `avrdude`, `objdump`.