"""Helpers for OpenAI Responses API tool-calling demos inside ARGOS."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from src.argos_logger import get_logger

load_dotenv()

log = get_logger("argos.openai.responses")

DEFAULT_FUNCTION_PROMPT = "What is my horoscope? I am an Aquarius."
DEFAULT_FUNCTION_INSTRUCTIONS = "Respond only with results grounded in tool outputs."
DEFAULT_FUNCTION_MODEL = "gpt-5"
DEFAULT_SHELL_MODEL = "gpt-5.4"

FUNCTION_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_horoscope",
        "description": "Get today's horoscope for an astrological sign.",
        "parameters": {
            "type": "object",
            "properties": {
                "sign": {
                    "type": "string",
                    "description": "An astrological sign like Taurus or Aquarius.",
                }
            },
            "required": ["sign"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather for a location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City and country, for example Paris, France.",
                }
            },
            "required": ["location"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "send_email",
        "description": "Send a short plain-text email.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Destination email address.",
                },
                "body": {
                    "type": "string",
                    "description": "Email body.",
                },
            },
            "required": ["to", "body"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def get_horoscope(sign: str) -> str:
    """Return a deterministic demo horoscope."""
    return f"{sign}: Next Tuesday you will befriend a baby otter."


def get_weather(location: str) -> str:
    """Return a deterministic mock weather payload."""
    return json.dumps(
        {
            "location": location,
            "forecast": "mild",
            "temperature_c": 18,
        }
    )


def send_email(to: str, body: str) -> str:
    """Return a mock email delivery confirmation."""
    return json.dumps(
        {
            "status": "sent",
            "to": to,
            "body_preview": body[:80],
        }
    )


TOOL_IMPLEMENTATIONS = {
    "get_horoscope": get_horoscope,
    "get_weather": get_weather,
    "send_email": send_email,
}


def _build_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "openai SDK not installed. Install with `pip install openai` or use the "
            "`ai-full` optional dependency."
        ) from exc
    return OpenAI()


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    """Parse the JSON arguments from a Responses API function call."""
    data = json.loads(raw_arguments or "{}")
    if not isinstance(data, dict):
        raise ValueError("Tool arguments must decode to a JSON object.")
    return data


def execute_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Execute a locally implemented demo tool and return a string output."""
    tool = TOOL_IMPLEMENTATIONS.get(name)
    if tool is None:
        raise ValueError(f"Unsupported tool call: {name}")
    result = tool(**arguments)
    if isinstance(result, str):
        return result
    return json.dumps(result)


def build_function_call_outputs(output_items: list[Any]) -> list[dict[str, str]]:
    """Convert function_call items into function_call_output messages."""
    outputs: list[dict[str, str]] = []
    for item in output_items:
        if getattr(item, "type", None) != "function_call":
            continue
        arguments = parse_tool_arguments(getattr(item, "arguments", "{}"))
        result = execute_tool_call(getattr(item, "name", ""), arguments)
        outputs.append(
            {
                "type": "function_call_output",
                "call_id": getattr(item, "call_id", ""),
                "output": result,
            }
        )
    return outputs


def run_function_tools_demo(
    prompt: str = DEFAULT_FUNCTION_PROMPT,
    model: str = DEFAULT_FUNCTION_MODEL,
    instructions: str = DEFAULT_FUNCTION_INSTRUCTIONS,
) -> tuple[Any, list[Any]]:
    """Run a complete Responses API function-calling loop."""
    client = _build_client()
    input_items: list[Any] = [{"role": "user", "content": prompt}]

    response = client.responses.create(
        model=model,
        tools=FUNCTION_TOOLS,
        input=input_items,
    )

    while True:
        input_items.extend(response.output)
        function_outputs = build_function_call_outputs(response.output)
        if not function_outputs:
            return response, input_items

        input_items.extend(function_outputs)
        response = client.responses.create(
            model=model,
            instructions=instructions,
            tools=FUNCTION_TOOLS,
            input=input_items,
        )


def build_shell_tool(skill_ids: list[str]) -> dict[str, Any]:
    """Build the shell tool payload with skill references."""
    return {
        "type": "shell",
        "environment": {
            "type": "container_auto",
            "skills": [
                {"type": "skill_reference", "skill_id": skill_id}
                for skill_id in skill_ids
            ],
        },
    }


def run_shell_skills_demo(
    prompt: str,
    skill_ids: list[str],
    model: str = DEFAULT_SHELL_MODEL,
) -> Any:
    """Submit a shell-tool request that references OpenAI-hosted skills."""
    if not skill_ids:
        raise ValueError("At least one skill id is required for the shell demo.")

    client = _build_client()
    return client.responses.create(
        model=model,
        tools=[build_shell_tool(skill_ids)],
        input=prompt,
    )


def upload_skill_version(skill_id: str, zip_path: str) -> dict[str, Any]:
    """Upload a zipped skill bundle with the raw REST endpoint."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to upload skill versions.")

    archive = Path(zip_path)
    if not archive.is_file():
        raise FileNotFoundError(f"Skill archive not found: {archive}")

    with archive.open("rb") as handle:
        response = requests.post(
            f"https://api.openai.com/v1/skills/{skill_id}/versions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"files": (archive.name, handle, "application/zip")},
            timeout=120,
        )

    response.raise_for_status()
    return response.json()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ARGOS helper around the OpenAI Responses API tool-calling flow."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    function_parser = subparsers.add_parser(
        "function-demo",
        help="Run the Responses API with local function tools.",
    )
    function_parser.add_argument("--prompt", default=DEFAULT_FUNCTION_PROMPT)
    function_parser.add_argument("--model", default=DEFAULT_FUNCTION_MODEL)
    function_parser.add_argument("--instructions", default=DEFAULT_FUNCTION_INSTRUCTIONS)

    shell_parser = subparsers.add_parser(
        "shell-skills",
        help="Submit a shell tool request with one or more skill ids.",
    )
    shell_parser.add_argument("--prompt", required=True)
    shell_parser.add_argument("--model", default=DEFAULT_SHELL_MODEL)
    shell_parser.add_argument("--skill-id", action="append", dest="skill_ids", required=True)

    upload_parser = subparsers.add_parser(
        "upload-skill-version",
        help="Upload a zipped skill version through the REST API.",
    )
    upload_parser.add_argument("--skill-id", required=True)
    upload_parser.add_argument("--zip-path", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint used both by scripts/ and main.py."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "function-demo":
        response, input_items = run_function_tools_demo(
            prompt=args.prompt,
            model=args.model,
            instructions=args.instructions,
        )
        print("Final input:")
        print(json.dumps(input_items, indent=2, default=str))
        print("\nFinal output:")
        print(response.model_dump_json(indent=2))
        print("\n" + response.output_text)
        return 0

    if args.command == "shell-skills":
        response = run_shell_skills_demo(
            prompt=args.prompt,
            skill_ids=args.skill_ids,
            model=args.model,
        )
        print(response.model_dump_json(indent=2))
        return 0

    if args.command == "upload-skill-version":
        payload = upload_skill_version(
            skill_id=args.skill_id,
            zip_path=args.zip_path,
        )
        print(json.dumps(payload, indent=2))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
