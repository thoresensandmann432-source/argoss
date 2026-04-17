"""Small Hugging Face Hub HTTP helper for ARGOS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HF_API_BASE = "https://huggingface.co/api"


def get_hf_token() -> str:
    token = (os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("HUGGINGFACE_TOKEN or HF_TOKEN is required.")
    return token


def hf_get(path: str, params: dict[str, Any] | None = None) -> Any:
    token = get_hf_token()
    response = requests.get(
        f"{HF_API_BASE}{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def command_whoami() -> int:
    payload = hf_get("/whoami-v2")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_models(limit: int, search: str | None) -> int:
    params: dict[str, Any] = {"limit": limit}
    if search:
        params["search"] = search
    else:
        params["sort"] = "downloads"
        params["direction"] = -1
    payload = hf_get("/models", params=params)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_datasets(limit: int, search: str | None) -> int:
    params: dict[str, Any] = {"limit": limit}
    if search:
        params["search"] = search
    else:
        params["sort"] = "downloads"
        params["direction"] = -1
    payload = hf_get("/datasets", params=params)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Direct Hugging Face Hub checks over HTTP.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("whoami", help="Show authenticated Hugging Face account info.")

    models_parser = subparsers.add_parser("models", help="List or search models.")
    models_parser.add_argument("--limit", type=int, default=5)
    models_parser.add_argument("--search", default=None)

    datasets_parser = subparsers.add_parser("datasets", help="List or search datasets.")
    datasets_parser.add_argument("--limit", type=int, default=5)
    datasets_parser.add_argument("--search", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "whoami":
        return command_whoami()
    if args.command == "models":
        return command_models(args.limit, args.search)
    if args.command == "datasets":
        return command_datasets(args.limit, args.search)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
