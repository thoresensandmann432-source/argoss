#!/usr/bin/env python3
"""
apply_integration.py - Применение интеграционного патча v1.20.5 → v2.1.3
"""
import os
import sys
import shutil
from datetime import datetime

PATCH_FILE = "integration_patch.py"
CORE_FILE = "src/core.py"
BACKUP_DIR = ".argos_patch_backups"

def main():
    print("🔧 Применение интеграционного патча...")
    print(f"📁 Рабочая директория: {os.getcwd()}")
    
    # Проверяем наличие файлов
    if not os.path.exists(PATCH_FILE):
        print(f"❌ Патч-файл не найден: {PATCH_FILE}")
        sys.exit(1)
    
    if not os.path.exists(CORE_FILE):
        print(f"❌ Core файл не найден: {CORE_FILE}")
        sys.exit(1)
    
    # Создаём бэкап
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_name = f"core_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    shutil.copy2(CORE_FILE, backup_path)
    print(f"💾 Бэкап создан: {backup_path}")
    
    # Читаем патч
    with open(PATCH_FILE, 'r', encoding='utf-8') as f:
        patch_content = f.read()
    
    # Читаем core.py
    with open(CORE_FILE, 'r', encoding='utf-8') as f:
        core_content = f.read()
    
    # Проверяем, не применён ли уже патч
    if "_init_c2_system" in core_content:
        print("⚠️ Патч уже применён (метод _init_c2_system найден)")
        print("✅ Пропускаем модификацию")
    else:
        # Находим место для вставки (после последнего def _init_)
        insert_marker = "# === КОНЕЦ ИНИЦИАЛИЗАЦИИ ==="
        
        if insert_marker in core_content:
            # Вставляем патч перед маркером
            new_content = core_content.replace(
                insert_marker,
                patch_content + "\n" + insert_marker
            )
        else:
            # Добавляем в конец класса
            new_content = core_content.rstrip() + "\n\n" + patch_content
        
        # Записываем обновлённый файл
        with open(CORE_FILE, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"✅ Патч применён к {CORE_FILE}")
    
    # Проверяем ARC_API_KEY
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        if "ARC_API_KEY=" in env_content:
            print("✅ ARC_API_KEY найден в .env")
        else:
            print("⚠️ ARC_API_KEY не найден в .env")
    
    print("\n🎉 Интеграция завершена!")
    print("📋 Следующие шаги:")
    print("   1. Перезапустите Argos: python main.py --no-gui")
    print("   2. Проверьте arc_agi3_skill через MCP")
    print("   3. Доступны новые команды: ghost, tasmota, pr2350, build apk")

if __name__ == "__main__":
    main()