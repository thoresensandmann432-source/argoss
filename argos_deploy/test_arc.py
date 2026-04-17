import random

print("=== Checking ARC modules ===")

# Check arcengine
try:
    from arcengine import GameAction, GameState
    print("OK arcengine imported")
except ImportError as e:
    print(f"MISSING arcengine: {e}")

# Check arc_agi
try:
    import arc_agi
    print("OK arc_agi imported")
    classes = [x for x in dir(arc_agi) if not x.startswith("_")]
    print(f"Available classes: {classes}")
    
    # Try Arcade
    try:
        arc = arc_agi.Arcade()
        print("OK Arcade exists")
    except AttributeError as e:
        print(f"MISSING Arcade: {e}")
    except Exception as e:
        print(f"ERROR Arcade: {e}")
        
except ImportError as e:
    print(f"MISSING arc_agi: {e}")

print("\n=== Done ===")
