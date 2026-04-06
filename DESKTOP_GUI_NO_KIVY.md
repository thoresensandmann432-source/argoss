# ARGOS Desktop GUI — Без Kivy

## ✅ Что это?

Чистый desktop-интерфейс ARGOS на **customtkinter** без зависимостей от Kivy/OpenGL.

Идеально для Windows ПК без проблем совместимости графики.

---

## 📦 Преимущества

| Без Kivy | С Kivy |
|----------|--------|
| ✅ Быстрый запуск | ⏱️ Медленная инициализация |
| ✅ Нет зависимостей OpenGL | ⚠️ Проблемы с OpenGL на некоторых GPU |
| ✅ Нативный Windows-стиль | 🎨 Собственный стиль Kivy |
| ✅ Меньше памяти | 💾 SDL2 + Kivy = +100MB |
| ✅ Нет SDL2/warnings | ⚠️ Много warnings в консоли |

---

## 🚀 Запуск

### Вариант 1: BAT файл (рекомендуется)
```cmd
argos-desktop.bat
```

### Вариант 2: Python напрямую
```bash
cd C:\Users\AvA\debug\argoss
python src\argos_desktop.py
```

### Вариант 3: С параметрами
```bash
python src\argos_desktop.py --theme light
```

---

## 🎨 Возможности

✅ Все 35 навыков  
✅ 417 Claude агентов  
✅ CustomTkinter интерфейс (тёмная/светлая тема)  
✅ История команд (↑/↓)  
✅ Метрики CPU/RAM  
✅ Консоль с цветовым выводом  
✅ Вкладки: Консоль | Память | Система  

---

## 📁 Структура файлов

```
argoss/
├── src/
│   ├── argos_desktop.py          # ← НОВЫЙ: Desktop launcher
│   └── interface/
│       └── gui.py                  # CustomTkinter GUI
├── argos-desktop.bat               # ← НОВЫЙ: Windows запуск
└── DESKTOP_GUI_NO_KIVY.md          # ← Этот файл
```

---

## ⚡ Сравнение с main.py

### main.py (стандартный)
```bash
python main.py              # Запускает Kivy GUI (тяжёлый)
python main.py --no-gui     # Headless режим
```

### argos_desktop.py (новый)
```bash
python src\argos_desktop.py  # Запускает CustomTkinter GUI (лёгкий)
```

---

## 🔧 Troubleshooting

### Ошибка: customtkinter not found
```bash
pip install customtkinter
```

### Ошибка: другие зависимости
```bash
pip install -r requirements.txt
```

### Всё равно загружается Kivy?
Проверьте, что запускаете **argos_desktop.py**, а не main.py.

---

## 🎯 Быстрый старт

1. **Убедитесь**, что установлен customtkinter:
   ```bash
   python -c "import customtkinter; print(customtkinter.__version__)"
   ```

2. **Запустите**:
   ```bash
   cd C:\Users\AvA\debug\argoss
   argos-desktop.bat
   ```

3. **Готово!** GUI запустится без Kivy.

---

## 📝 Примечание

Оба интерфейса (Kivy и CustomTkinter) используют **одно и то же ядро** ArgosCore.
Разница только в оболочке. Все навыки, агенты и команды работают одинаково.

---

**Version:** 3.0  
**Date:** 2026-03-31  
**Status:** ✅ Ready