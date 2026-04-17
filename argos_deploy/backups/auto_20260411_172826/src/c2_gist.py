"""
Argos C2 Gist Module v1.20.5 → v2.1.3 Integration
Ghost Drone Command & Control via GitHub Gists
Re-exports from argos_c2_gist for backwards compatibility.
"""
from src.argos_c2_gist import GistC2, GhostDroneClient  # noqa: F401

__all__ = ["GistC2", "GhostDroneClient"]
