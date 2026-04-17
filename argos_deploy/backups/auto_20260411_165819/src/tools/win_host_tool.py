"""
win_host_tool.py — Алиас для win_host_tool.py.py
"""
import importlib.util, os, sys

_real = os.path.join(os.path.dirname(__file__), "win_host_tool.py.py")
_spec = importlib.util.spec_from_file_location("win_host_tool_impl", _real)
_mod  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules[__name__].__dict__.update({k: v for k, v in _mod.__dict__.items() if not k.startswith("__")})
