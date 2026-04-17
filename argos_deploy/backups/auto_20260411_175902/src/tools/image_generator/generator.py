from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from src.argos_logger import get_logger
from .models import resolve_model_name
from .utils import ensure_output_dir, prompt_hash, save_generation_record

log = get_logger("argos.image_generator")


class ArgosImageGenerator:
    def __init__(self, model_name: str | None = None):
        self.model_name = resolve_model_name(model_name)
        self.device = "cuda"
        self.pipe = None
        self.output_dir = ensure_output_dir(Path("data/generated_images"))
        self.db_path = Path("data/argos_memory.db")

    def load(self) -> None:
        if self.pipe is not None:
            return
        try:
            import torch
            from diffusers import DiffusionPipeline

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
            pipe = DiffusionPipeline.from_pretrained(self.model_name, torch_dtype=dtype)
            pipe.to(self.device)
            if self.device == "cuda":
                try:
                    pipe.enable_model_cpu_offload()
                except Exception:
                    pass
            self.pipe = pipe
            log.info("ImageGenerator local pipeline loaded: %s (%s)", self.model_name, self.device)
        except Exception as exc:
            self.pipe = None
            log.warning("ImageGenerator local pipeline unavailable: %s", exc)

    def _save(self, image: Image.Image, prompt: str, negative_prompt: str, width: int, height: int, steps: int) -> str:
        filename = f"{prompt_hash(prompt)}.png"
        path = self.output_dir / filename
        image.save(path)
        try:
            save_generation_record(
                self.db_path,
                prompt=prompt,
                negative_prompt=negative_prompt,
                model_name=self.model_name,
                file_path=str(path),
                width=width,
                height=height,
                steps=steps,
            )
        except Exception as exc:
            log.warning("ImageGenerator memory save failed: %s", exc)
        return str(path)

    def _generate_local(
        self,
        prompt: str,
        negative_prompt: str,
        steps: int,
        width: int,
        height: int,
        guidance_scale: float,
    ) -> str:
        self.load()
        if self.pipe is None:
            raise RuntimeError("local pipeline not available")
        image = self.pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=steps,
            width=width,
            height=height,
            guidance_scale=guidance_scale,
        ).images[0]
        return self._save(image, prompt, negative_prompt, width, height, steps)

    def _hf_tokens(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for key in ("HF_TOKEN", "HUGGINGFACE_TOKEN", "HUGGINGFACE_TOKEN0", "HF_TOKEN0"):
            val = (os.getenv(key) or "").strip()
            if val and val not in seen:
                out.append(val)
                seen.add(val)
        for i in range(20):
            for key in (f"HUGGINGFACE_TOKEN_{i}", f"HUGGINGFACE_TOKEN{i}", f"HF_TOKEN_{i}", f"HF_TOKEN{i}"):
                val = (os.getenv(key) or "").strip()
                if val and val not in seen:
                    out.append(val)
                    seen.add(val)
        return out

    def _generate_hf(self, prompt: str, negative_prompt: str, width: int, height: int) -> str:
        tokens = self._hf_tokens()
        if not tokens:
            raise RuntimeError("no HF token configured")
        payload: dict[str, Any] = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
            },
        }
        last_error = "hf generation failed"
        urls = [
            f"https://router.huggingface.co/hf-inference/models/{self.model_name}",
            f"https://api-inference.huggingface.co/models/{self.model_name}",
        ]
        for token in tokens:
            for url in urls:
                try:
                    resp = requests.post(
                        url,
                        headers={"Authorization": f"Bearer {token}"},
                        json=payload,
                        timeout=90,
                    )
                    if resp.ok and resp.content:
                        ctype = (resp.headers.get("content-type") or "").lower()
                        if "image" in ctype:
                            image = Image.open(io.BytesIO(resp.content)).convert("RGB")
                            return self._save(image, prompt, negative_prompt, width, height, steps=0)
                        # Some providers return base64 payload
                        data = resp.json()
                        if isinstance(data, dict) and data.get("image"):
                            raw = base64.b64decode(data["image"])
                            image = Image.open(io.BytesIO(raw)).convert("RGB")
                            return self._save(image, prompt, negative_prompt, width, height, steps=0)
                    else:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:180]}"
                except Exception as exc:
                    last_error = str(exc)
        raise RuntimeError(last_error)

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        steps: int = 20,
        width: int = 1024,
        height: int = 1024,
        guidance_scale: float = 3.5,
    ) -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required")

        try:
            return self._generate_local(
                prompt=prompt,
                negative_prompt=negative_prompt,
                steps=steps,
                width=width,
                height=height,
                guidance_scale=guidance_scale,
            )
        except Exception as exc:
            log.warning("ImageGenerator local path failed, fallback to HF API: %s", exc)
            return self._generate_hf(prompt=prompt, negative_prompt=negative_prompt, width=width, height=height)
