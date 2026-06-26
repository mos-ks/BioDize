"""Shared FastAPI dependencies."""
from __future__ import annotations

from app.db.base import get_db  # re-export for routers

__all__ = ["get_db"]
