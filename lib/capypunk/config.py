"""Paths and settings shared by the pipelines, the player build and the scripts."""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MEDIA = Path(os.environ.get("CAPYPUNK_MEDIA", REPO / "media"))
SERIES = REPO / "series"
PLAYER = REPO / "player"

# Models (Alibaba family on Runware, by choice)
LLM_MODEL = "alibaba:qwen@4-max"
IMAGE_MODEL = "alibaba:qwen-image@2.1-turbo"
VIDEO_MODEL = "alibaba:wan@3.0-prime"

# Render settings
VIDEO_RESOLUTION = os.environ.get("CAPYPUNK_RESOLUTION", "720p")
STILL_W, STILL_H = 1920, 1088  # 16:9-ish; both multiples of 16

# Spend guardrail checked by the pipeline (USD)
RENDER_BUDGET_USD = float(os.environ.get("CAPYPUNK_BUDGET_USD", "40"))


def media_dir(*parts: str) -> Path:
    p = MEDIA.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p
