#!/usr/bin/env python3
"""Исправленный сканер скиллов Argos"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict

def find_python_files(root_dir):
    python_files = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    return python_files

def analyze_skill_v2(file_path, src_root):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if not content.strip():
            return None
        
        rel_path = os.path.relpath(file_path, src_root).replace(os.sep, '/')
        
        skill_patterns = {
            'has_skill_description': 'SKILL_DESCRIPTION' in content,
            'has_skill_name': 'SKILL_NAME' in content,
            'has_skill_triggers': 'SKILL_TRIGGERS' in content,
            'has_register_func': 'def register(' in content,
            'has_execute_func': 'def execute(' in content,
            'has_handle_func': 'def handle(' in content,
        }
        
        skill_name = None
        skill_desc = None
        
        name_match = re.search(r'SKILL_NAME\s*=\s*["\']([^"\']+)["\']', content)
        if name_match:
            skill_name = name_match.group(1)
        
        desc_match = re.search(r'SKILL_DESCRIPTION\s*=\s*["\']([^"\']+)["\']', content)
        if desc_match:
            skill_desc = desc_match.group(1)
        
        is_skill = (
            skill_patterns['has_skill_description'] or
            skill_patterns['has_skill_name'] or
            skill_patterns['has_skill_triggers'] or
            skill_patterns['has_register_func'] or
            skill_patterns['has_execute_func'] or
            skill_patterns['has_handle_func']
        )
        
        return {
            'path': rel_path,
            'name': skill_name or Path(file_path).stem,
            'description': skill_desc or 'No description',
            'is_skill': is_skill,
            'patterns': skill_patterns,
            'line_count': len(content.splitlines())
        }
    except Exception as e:
        return {'path': str(file_path), 'error': str(e)}

def scan_skills_v2(src_root, output_file):
    print(f"Сканирование: {src_root}")
    print("=" * 70)
    
    python_files = find_python_files(src_root)
    print(f"Всего файлов: {len(python_files)}")
    
    skills = []
    regular_modules = []
    errors = []
    
    for i, file_path in enumerate(python_files, 1):
        if i % 50 == 0:
            print(f"Обработано: {i}/{len(python_files)}")
        
        result = analyze_skill_v2(file_path, src_root)
        if result:
            if 'error' in result:
                errors.append(result)
            elif result['is_skill']:
                skills.append(result)
            else:
                regular_modules.append(result['path'])
    
    skills_by_folder = defaultdict(list)
    for skill in skills:
        folder = str(Path(skill['path']).parent)
        skills_by_folder[folder].append(skill)
    
    print("\n" + "=" * 70)
    print(f"НАЙДЕНО СКИЛЛОВ: {len(skills)}")
    print("=" * 70)
    
    for folder, folder_skills in sorted(skills_by_folder.items()):
        print(f"\n[DIR] {folder}/ ({len(folder_skills)} skills):")
        for skill in sorted(folder_skills, key=lambda x: x['name']):
            print(f"  [OK] {skill['name']:<30} ({skill['line_count']:>4} lines)")
    
    results = {
        'meta': {
            'total_files': len(python_files),
            'skills_found': len(skills),
            'regular_modules': len(regular_modules),
            'errors': len(errors)
        },
        'skills': skills,
        'by_folder': {k: [s['name'] for s in v] for k, v in skills_by_folder.items()},
        'errors': errors
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SAVED] {output_file}")
    return results

if __name__ == "__main__":
    src_root = r"F:\debug\argoss\src"
    output_file = r"F:\debug\argoss\skills_report_v2.json"
    
    if not os.path.exists(src_root):
        print(f"ERROR: {src_root} not found!")
    else:
        scan_skills_v2(src_root, output_file)
