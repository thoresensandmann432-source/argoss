import os
import json
from pathlib import Path

SKILLS_DIR = Path("src/skills")

print("=" * 60)
print("PROVERKA SKILLOV ARGOS")
print("=" * 60)

if not SKILLS_DIR.exists():
    print(f"ERROR: Directory not found: {SKILLS_DIR}")
    exit(1)

skills = [d for d in SKILLS_DIR.iterdir() if d.is_dir() and not d.name.startswith('_')]
print(f"\nVsego skillov: {len(skills)}\n")

ok_count = 0
error_count = 0

for skill in sorted(skills):
    name = skill.name
    manifest = skill / "manifest.json"
    skill_py = skill / "skill.py"
    
    if manifest.exists():
        try:
            with open(manifest, 'r', encoding='utf-8') as f:
                data = json.load(f)
            status = "[OK]"
            desc = data.get('description', 'No desc')
            ok_count += 1
        except Exception as e:
            status = f"[ERROR] {e}"
            desc = ""
            error_count += 1
    elif skill_py.exists():
        status = "[OK]"
        desc = "skill.py found"
        ok_count += 1
    else:
        status = "[WARNING] No manifest"
        desc = ""
    
    print(f"{status:30} | {name:20} | {desc[:30]}")

print("\n" + "=" * 60)
print(f"Rezultat:")
print(f"   [OK]: {ok_count}")
print(f"   [ERROR]: {error_count}")
print(f"   Vsego: {len(skills)}")
print("=" * 60)
