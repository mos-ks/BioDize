"""FastAPI application entry point.

Run:  uvicorn app.main:app --reload   (from the backend/ directory)
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.base import init_db
from app.api.routes import documents, export, fields, flags, health, pages, stats

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Create tables eagerly (idempotent) so the app works under uvicorn and tests alike.
# For real migrations use Alembic.
init_db()


# Health is unprefixed; everything else under /api/v1.
app.include_router(health.router)
for module in (documents, fields, flags, pages, stats, export):
    app.include_router(module.router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "api": settings.api_prefix}
