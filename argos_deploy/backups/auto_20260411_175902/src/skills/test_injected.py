"""
test_injected.py — Тестовый навык для проверки инъекции.
"""

SKILL_DESCRIPTION = "Тестовый навык для проверки инъекции"


class TestSkill:
    def __init__(self, core=None):
        self.core = core
    def execute(self):
        return "Hello from TestSkill"
    def report(self):
        return "TestSkill OK"