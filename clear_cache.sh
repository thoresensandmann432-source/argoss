#!/bin/bash
# Запусти один раз после обновления файлов:
# chmod +x clear_cache.sh && ./clear_cache.sh

echo "Очищаю кеш Python..."
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
echo "✅ Кеш очищен. Теперь запусти: python3 main.py"
