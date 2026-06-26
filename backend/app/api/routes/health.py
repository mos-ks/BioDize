"""Health check."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "extractor": settings.extractor,
        "ocr_engine": settings.ocr_engine,
        "db": settings.database_url.split(":")[0],
    }
