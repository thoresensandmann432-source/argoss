import os
import tempfile
import unittest
from pathlib import Path

from src.core import _load_argos_core_class

ArgosCore = _load_argos_core_class()


class _FakeAwareness:
    def reflect(self) -> str:
        return "👁️ awareness ok"


class _FakeAdmin:
    def get_stats(self) -> str:
        return "CPU: 1% | RAM: 2% | DISK: 3%"


class _FakeWebExplorer:
    def fetch_page(self, url: str) -> str:
        return f"FETCH:{url}"


class CoreAwarenessScanTests(unittest.TestCase):
    def test_detects_natural_scan_request(self):
        core = ArgosCore.__new__(ArgosCore)
        self.assertTrue(core._looks_like_awareness_scan_request("осознай свою систему и файлы"))
        self.assertTrue(core._looks_like_awareness_scan_request("просканируй проект"))
        self.assertFalse(core._looks_like_awareness_scan_request("расскажи анекдот"))

    def test_extract_direct_url(self):
        core = ArgosCore.__new__(ArgosCore)
        self.assertEqual(
            core._extract_direct_url("https://sigtrip-90014.slack.com/forgot/check"),
            "https://sigtrip-90014.slack.com/forgot/check",
        )
        self.assertEqual(
            core._extract_direct_url("открой ссылку https://example.com/test"),
            "https://example.com/test",
        )
        self.assertIsNone(core._extract_direct_url("расскажи про https://example.com"))

    def test_detects_bulk_dump(self):
        core = ArgosCore.__new__(ArgosCore)
        dump = """
        ## migrations
        ## alpha_tools
        # Assistant Response Preferences
        Confidence=high
        # User Interaction Metadata
        # Recent Conversation Content
        namespace file_search {
        https://example.com/test
        """
        self.assertTrue(core._looks_like_bulk_text_dump(dump))
        report = core._analyze_bulk_text_dump(dump)
        self.assertIn("большой текстовый дамп", report.lower())
        self.assertIn("memory prompt", report.lower())
        self.assertIn("https://example.com/test", report)

    def test_detects_escaped_single_line_dump(self):
        core = ArgosCore.__new__(ArgosCore)
        dump = (
            "<assistant>\\nimage safety policies:\\xa0 \\n"
            "never begin your responses with interjections like \"ah\"\\n"
            "## file_search\\n"
            "<user> classic car birthday ideas for 50 year old man </user>"
        )
        self.assertTrue(core._looks_like_bulk_text_dump(dump))
        report = core._analyze_bulk_text_dump(dump)
        self.assertIn("file_search", report.lower())
        self.assertIn("style rules", report.lower())

    def test_process_logic_prioritizes_direct_url_fetch(self):
        core = ArgosCore.__new__(ArgosCore)
        core.context = None
        core.db = None
        core.constitution_hooks = None
        core.web_explorer = _FakeWebExplorer()
        core._remember_dialog_turn = lambda *args, **kwargs: None
        core._apply_chatgpt_link_profile = lambda text: None
        result = core.process_logic(
            "https://zapier.com/app/dashboard?from=https%3A//zapier.com/pricing&context=26934779",
            admin=None,
            flasher=None,
        )
        self.assertEqual(
            result,
            {
                "answer": "FETCH:https://zapier.com/app/dashboard?from=https%3A//zapier.com/pricing&context=26934779",
                "state": "Direct",
            },
        )

    def test_classify_prompt_dump(self):
        core = ArgosCore.__new__(ArgosCore)
        text = "<assistant>\\n## file_search\\nimage safety policies"
        self.assertEqual(core._classify_input(text), "prompt_dump")

    def test_execute_intent_handles_direct_url_early(self):
        core = ArgosCore.__new__(ArgosCore)
        core.web_explorer = _FakeWebExplorer()
        self.assertEqual(
            core.execute_intent(
                "https://zapier.com/app/dashboard?from=https%3A//zapier.com/pricing&context=26934779",
                admin=None,
                flasher=None,
            ),
            "FETCH:https://zapier.com/app/dashboard?from=https%3A//zapier.com/pricing&context=26934779",
        )

    def test_execute_intent_handles_bulk_dump_early(self):
        core = ArgosCore.__new__(ArgosCore)
        dump = (
            "<assistant>\\nimage safety policies:\\xa0 \\n"
            "never begin your responses with interjections like \"ah\"\\n"
            "## file_search\\n"
            "<user> classic car birthday ideas for 50 year old man </user>"
        )
        result = core.execute_intent(dump, admin=None, flasher=None)
        self.assertIn("большой текстовый дамп", result.lower())
        self.assertIn("file_search", result.lower())

    def test_inventory_report_reads_project_layout(self):
        core = ArgosCore.__new__(ArgosCore)
        core.awareness = _FakeAwareness()
        core.memory = object()
        core.p2p = None
        core.vision = None
        core.tool_calling = None
        core.skill_loader = object()
        core.module_loader = object()
        core.dreamer = None
        core.evolution_engine = None
        core.self_model_v2 = object()
        core._internal_admin = _FakeAdmin()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("print('ok')", encoding="utf-8")
            (root / ".env").write_text("X=1", encoding="utf-8")
            (root / "requirements.txt").write_text("psutil", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "skills").mkdir(parents=True)
            (root / "src" / "skills" / "__init__.py").write_text("", encoding="utf-8")
            (root / "src" / "skills" / "weather.py").write_text("x=1", encoding="utf-8")
            (root / "src" / "mod.py").write_text("x=1", encoding="utf-8")

            prev = os.getcwd()
            try:
                os.chdir(root)
                report = core._system_awareness_report(core._internal_admin)
            finally:
                os.chdir(prev)

        self.assertIn("ARGOS SELF-SCAN", report)
        self.assertIn("main.py", report)
        self.assertIn("requirements.txt", report)
        self.assertIn("Навыки: 1", report)
        self.assertIn("skill_loader", report)
        self.assertIn("awareness ok", report)


if __name__ == "__main__":
    unittest.main()
