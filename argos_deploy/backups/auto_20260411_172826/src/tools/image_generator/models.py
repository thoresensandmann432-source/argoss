from __future__ import annotations

import os


DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"

MODEL_ALIASES = {
    "flux2": "black-forest-labs/FLUX.2-dev",
    "flux2-dev": "black-forest-labs/FLUX.2-dev",
    "flux2-klein": "black-forest-labs/FLUX.2-klein-4B",
    "flux1": "black-forest-labs/FLUX.1-schnell",
    "flux1-schnell": "black-forest-labs/FLUX.1-schnell",
    "sd35": "stabilityai/stable-diffusion-3.5-large",
    "sdxl": "stabilityai/stable-diffusion-xl-base-1.0",
}


def resolve_model_name(name: str | None) -> str:
    raw = (name or "").strip()
    if not raw:
        raw = (os.getenv("ARGOS_IMAGE_MODEL") or os.getenv("HF_TXT2IMG_MODEL") or DEFAULT_MODEL).strip()
    return MODEL_ALIASES.get(raw.lower(), raw)

