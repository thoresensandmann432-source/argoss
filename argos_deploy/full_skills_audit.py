#!/usr/bin/env python3
"""Полный аудит всех скиллов Argos"""

import os
import sys
import json
import ast
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("src")

def find_all_skills():
    """Находит все файлы которые могут быть скиллами"""
    skills = []
    
    # 1. Папка skills
    skills_dir = BASE_DIR / "skills"
    if skills_dir.exists():
        for item in skills_dir.rglob("*.py"):
            if item.name == "skill.py" or "_skill" in item.name:
                skills.append(("PACKAGED", item))
    
    # 2. Корневые файлы *_skill.py
    for item in BASE_DIR.rglob("*_skill.py"):
        skills.append(("MODULE", item))
    
    # 3. Файлы с декоратором @skill
    for item in BASE_DIR.rglob("*.py"):
        try:
            content = item.read_text(encoding='utf-8', errors='ignore')
            if '@skill' in content or 'def skill' in content or 'class.*Skill' in content:
                if item not in [s[1] for s in skills]:
                    skills.append(("DECORATED", item))
        except:
            pass
    
    return skills

def analyze_skill(path, skill_type):
    """Анализирует один скилл"""
    result = {
        'path': str(path),
        'type': skill_type,
        'name': path.stem,
        'status': 'UNKNOWN',
        'manifest': False,
        'has_skill_func': False,
        'has_skill_class': False,
        'dependencies': [],
        'errors': []
    }
    
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
        
        # Проверка manifest.json для packaged скиллов
        if skill_type == "PACKAGED":
            manifest = path.parent / "manifest.json"
            if manifest.exists():
                result['manifest'] = True
                try:
                    with open(manifest) as f:
                        data = json.load(f)
                    result['name'] = data.get('name', path.parent.name)
                except Exception as e:
                    result['errors'].append(f"manifest.json invalid: {e}")
        
        # Проверка на функцию skill
        if 'def skill(' in content or 'def skill_' in content:
            result['has_skill_func'] = True
        
        # Проверка на класс Skill
        if 'class Skill' in content or '(Skill)' in content:
            result['has_skill_class'] = True
        
        # Проверка декоратора @skill
        if '@skill' in content:
            result['has_decorator'] = True
        
        # Определение статуса
        checks = [
            result['manifest'] or result['has_skill_func'] or result['has_skill_class'] or result.get('has_decorator', False),
            len(result['errors']) == 0
        ]
        
        if all(checks):
            result['status'] = 'OK'
        elif result['errors']:
            result['status'] = 'ERROR'
        else:
            result['status'] = 'INCOMPLETE'
            
    except Exception as e:
        result['status'] = 'ERROR'
        result['errors'].append(str(e))
    
    return result

def main():
    print("=" * 70)
    print("POLNYJ AUDIT SKILLOV ARGOS")
    print("=" * 70)
    
    skills = find_all_skills()
    print(f"\nNajdeno potencialnyh skillov: {len(skills)}\n")
    
    results = []
    by_status = defaultdict(list)
    
    for skill_type, path in sorted(skills, key=lambda x: str(x[1])):
        result = analyze_skill(path, skill_type)
        results.append(result)
        by_status[result['status']].append(result)
    
    # Вывод по категориям
    for status in ['OK', 'INCOMPLETE', 'ERROR']:
        items = by_status.get(status, [])
        if not items:
            continue
            
        print(f"\n[{status}] - {len(items)} skillov:")
        print("-" * 70)
        
        for r in sorted(items, key=lambda x: x['path']):
            name = r['name'][:30]
            path_short = str(r['path']).replace('src/', '')[:35]
            features = []
            if r['manifest']: features.append('M')
            if r['has_skill_func']: features.append('F')
            if r['has_skill_class']: features.append('C')
            
            print(f"  {name:30} | {path_short:35} | {' '.join(features)}")
            
            if r['errors']:
                for e in r['errors'][:2]:
                    print(f"    -> ERROR: {e[:50]}")
    
    # Сводка
    print("\n" + "=" * 70)
    print("SVODKA:")
    print("=" * 70)
    total = len(results)
    ok = len(by_status.get('OK', []))
    incomplete = len(by_status.get('INCOMPLETE', []))
    errors = len(by_status.get('ERROR', []))
    
    print(f"  Vsego provereno:  {total}")
    print(f"  [OK]:             {ok} ({ok/total*100:.1f}%)")
    print(f"  [INCOMPLETE]:     {incomplete}")
    print(f"  [ERROR]:          {errors}")
    print("=" * 70)
    
    # Сохраняем отчет
    report_file = Path("skills_full_report.json")
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nOtchety sohranen: {report_file}")

if __name__ == "__main__":
    main()
