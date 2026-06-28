"""Health check."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])

# The gold set lives at repo-root/ground_truth; it isn't bundled in the cloud image,
# so the UI hides "Eval AI" when it's absent (the eval is only meaningful for the
# bundled sample batch anyway).
_GOLD_DIR = Path(__file__).resolve().parents[4] / "ground_truth"


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "extractor": settings.extractor,
        "ocr_engine": settings.ocr_engine,
        "db": settings.database_url.split(":")[0],
        "ground_truth": _GOLD_DIR.exists(),
    }
