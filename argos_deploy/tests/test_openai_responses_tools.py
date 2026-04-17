import unittest
from types import SimpleNamespace

from src.openai_responses_tools import (
    build_function_call_outputs,
    build_shell_tool,
    execute_tool_call,
    parse_tool_arguments,
)


class OpenAIResponsesToolsTests(unittest.TestCase):
    def test_parse_tool_arguments_accepts_json_object(self):
        self.assertEqual(parse_tool_arguments('{"sign":"Aquarius"}'), {"sign": "Aquarius"})

    def test_parse_tool_arguments_rejects_non_object_json(self):
        with self.assertRaises(ValueError):
            parse_tool_arguments('["Aquarius"]')

    def test_execute_tool_call_supports_mock_email_tool(self):
        result = execute_tool_call("send_email", {"to": "bob@example.com", "body": "Hi Bob"})
        self.assertIn('"status": "sent"', result)
        self.assertIn('"to": "bob@example.com"', result)

    def test_build_function_call_outputs_handles_multiple_calls(self):
        items = [
            SimpleNamespace(
                type="function_call",
                call_id="call-weather",
                name="get_weather",
                arguments='{"location":"Paris, France"}',
            ),
            SimpleNamespace(
                type="function_call",
                call_id="call-email",
                name="send_email",
                arguments='{"to":"bob@example.com","body":"Hi Bob"}',
            ),
        ]

        outputs = build_function_call_outputs(items)

        self.assertEqual(len(outputs), 2)
        self.assertEqual(outputs[0]["call_id"], "call-weather")
        self.assertIn("Paris, France", outputs[0]["output"])
        self.assertEqual(outputs[1]["call_id"], "call-email")
        self.assertIn('"status": "sent"', outputs[1]["output"])

    def test_build_shell_tool_uses_skill_references(self):
        tool = build_shell_tool(["skill_alpha", "skill_beta"])
        self.assertEqual(tool["type"], "shell")
        self.assertEqual(tool["environment"]["type"], "container_auto")
        self.assertEqual(
            tool["environment"]["skills"],
            [
                {"type": "skill_reference", "skill_id": "skill_alpha"},
                {"type": "skill_reference", "skill_id": "skill_beta"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
