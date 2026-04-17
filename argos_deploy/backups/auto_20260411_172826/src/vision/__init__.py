"""ARGOS Vision modules"""
try:
    from .shadow_vision import ShadowVision as ArgosVision
    __all__ = ["ArgosVision"]
except ImportError:
    ArgosVision = None
    __all__ = []
