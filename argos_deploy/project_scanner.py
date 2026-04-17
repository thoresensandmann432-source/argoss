#!/usr/bin/env python3
"""Полное сканирование проекта Argos и создание кэша"""

import os
import ast
import json
from pathlib import Path
from collections import defaultdict

def find_python_files(root_dir):
    """Найти все Python файлы в директории"""
    python_files = []
    for root, dirs, files in os.walk(root_dir):
        # Пропускаем __pycache__
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    return python_files

def parse_imports(node):
    """Извлечь импорты из AST"""
    imports = []
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for alias in n.names:
                imports.append(alias.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                mod = n.module
                for alias in n.names:
                    if alias.name == '*':
                        imports.append(mod)
                    else:
                        imports.append(f"{mod}.{alias.name}")
    return list(set(imports))

def parse_classes(node):
    """Извлечь имена классов"""
    return [n.name for n in ast.walk(node) if isinstance(n, ast.ClassDef)]

def parse_functions(node):
    """Извлечь имена функций"""
    funcs = []
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(n.name)
    return funcs

def is_skill_file(tree, content):
    """Определить, является ли файл 'скиллом'"""
    # По классу Skill
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and 'Skill' in base.id:
                    return True
                if isinstance(base, ast.Attribute) and 'Skill' in base.attr:
                    return True
    
    # По декоратору @skill
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and 'skill' in decorator.id.lower():
                    return True
    
    # По содержимому в skills/
    if 'def skill' in content.lower() or 'class.*Skill' in content:
        return True
    
    return False

def analyze_file(file_path, src_root):
    """Анализирует один файл"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if not content.strip():
            return None
        
        tree = ast.parse(content)
        rel_path = os.path.relpath(file_path, src_root).replace(os.sep, '/')
        
        return {
            'path': rel_path,
            'imports': parse_imports(tree),
            'classes': parse_classes(tree),
            'functions': parse_functions(tree),
            'is_skill': is_skill_file(tree, content),
            'line_count': len(content.splitlines())
        }
    except SyntaxError as e:
        return {'path': rel_path, 'error': f'SyntaxError: {e}'}
    except Exception as e:
        return {'path': str(file_path), 'error': str(e)}

def scan_project(src_root, cache_path):
    """Основная функция сканирования"""
    print(f"Сканирование: {src_root}")
    print("=" * 60)
    
    python_files = find_python_files(src_root)
    print(f"Найдено файлов: {len(python_files)}")
    
    modules = {}
    skills = []
    errors = []
    
    for i, file_path in enumerate(python_files, 1):
        if i % 50 == 0:
            print(f"Обработано: {i}/{len(python_files)}")
        
        result = analyze_file(file_path, src_root)
        if result:
            if 'error' in result:
                errors.append(result)
            else:
                modules[result['path']] = result
                if result['is_skill']:
                    skills.append(result['path'])
    
    # Создаем кэш
    cache = {
        'meta': {
            'total_files': len(python_files),
            'modules_ok': len(modules),
            'errors': len(errors),
            'skills_found': len(skills),
            'src_root': str(src_root)
        },
        'modules': modules,
        'skills': skills,
        'errors': errors
    }
    
    # Сохраняем
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    print("=" * 60)
    print(f"СКАНИРОВАНИЕ ЗАВЕРШЕНО!")
    print(f"  Модулей: {len(modules)}")
    print(f"  Скиллов: {len(skills)}")
    print(f"  Ошибок: {len(errors)}")
    print(f"  Кэш сохранен: {cache_path}")
    
    return cache

if __name__ == "__main__":
    src_root = r"F:\debug\argoss\src"
    cache_path = r"F:\debug\argoss\project_cache.json"
    
    if not os.path.exists(src_root):
        print(f"ОШИБКА: Директория {src_root} не найдена!")
    else:
        scan_project(src_root, cache_path)
