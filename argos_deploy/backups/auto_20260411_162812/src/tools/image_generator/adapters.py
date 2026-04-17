from __future__ import annotations

from typing import Any, Callable

from .generator import ArgosImageGenerator


def image_generate(
    prompt: str,
    negative_prompt: str = "",
    steps: int = 20,
    width: int = 1024,
    height: int = 1024,
    model_name: str | None = None,
) -> str:
    gen = ArgosImageGenerator(model_name=model_name)
    return gen.generate(
        prompt=prompt,
        negative_prompt=negative_prompt,
        steps=steps,
        width=width,
        height=height,
    )


def register_with_autogpt(register_tool: Callable[..., Any]) -> bool:
    """Register for Auto-GPT style custom tool API."""
    try:
        register_tool(
            name="image_generator.generate",
            description="Generate an image from text prompt and return local file path.",
            func=image_generate,
        )
        return True
    except Exception:
        return False


def register_with_babyagi(babyagi_module: Any) -> bool:
    """Register for BabyAGI functionz API if available."""
    try:
        decorator = getattr(babyagi_module, "register_function")
    except Exception:
        return False
    try:
        decorator(image_generate)
        return True
    except Exception:
        return False


def build_autogen_tool() -> Any:
    """Return AutoGen AgentTool if autogen is installed, else plain callable."""
    try:
        from autogen_core.tools import FunctionTool  # type: ignore

        return FunctionTool(
            func=image_generate,
            description="Generate an image from prompt and return path to PNG file.",
            name="image_generator_generate",
        )
    except Exception:
        return image_generate

