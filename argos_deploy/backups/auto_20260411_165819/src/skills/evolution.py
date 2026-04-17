"""Skill re-export: evolution."""

SKILL_DESCRIPTION = "Эволюционные алгоритмы и генетическая оптимизация"

from src.skills.evolution.skill import ArgosEvolution


def register(core):
    return ArgosEvolution(core) if core else None
