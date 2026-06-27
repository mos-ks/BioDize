"""Application settings (pydantic-settings, read from environment / .env)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "BioDize Backend"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # --- Database ------------------------------------------------------------
    # SQLite by default; swap to Postgres/Supabase by changing this one value.
    database_url: str = "sqlite:///./biodize.db"

    # --- Extraction ----------------------------------------------------------
    # Which Extractor to use: "stub" (offline, no API) or "openai".
    extractor: str = "stub"

    # OpenAI / OpenAI-compatible endpoint. For the on-prem swap, point base_url
    # at a vLLM server (e.g. http://ocr-host:8000/v1) and change the model name.
    openai_api_key: str = ""
    openai_base_url: str | None = None          # None = api.openai.com
    openai_model: str = "gpt-5"                 # placeholder: set your exact GPT-5.x vision id in .env

    # --- OCR (bounding boxes + per-word confidence) --------------------------
    # The laptop can't run a local OCR engine, so boxes come from a cloud OCR API:
    #   "stub"     - none (stub fixture carries its own boxes)
    #   "mistral"  - Mistral OCR 4: per-block boxes, per-word confidence, structured JSON,
    #                single-container self-host later (best on-prem path). Weak on handwriting,
    #                so pair with an OpenAI read for handwritten values.
    #   "azure"    - Azure Document Intelligence Read (strong handwriting + word polygons)
    #   "google"   - Google Document AI (strongest handwriting + normalized boxes)
    # Pick the winner via a golden-set test on handwritten numeric/date fields.
    ocr_engine: str = "stub"
    mistral_api_key: str = ""
    azure_ocr_endpoint: str = ""
    azure_ocr_key: str = ""
    google_ocr_processor: str = ""              # projects/.../processors/...

    # --- Pipeline ------------------------------------------------------------
    storage_dir: str = "./var"                  # rendered page images live here
    render_dpi: int = 200
    # Bundled sample scan; POST /documents/process with no source_path uses this.
    sample_pdf_path: str = "../data/scanned_batch_documentation.pdf"
    # Confidence at/above which a clean, flag-free field is auto-accepted.
    # Conservative in production (calibrate on a golden set); 0.9 for the demo.
    auto_accept_threshold: float = 0.9
    # Below this, a clean field also gets a LOW_CONF warning ("verify the value").
    # Decoupled from auto-accept so the [warn, accept) band routes to review
    # WITHOUT spamming a warning on every handwritten read — only the genuinely
    # illegible (< warn) gets flagged. Handwriting OCR confidence runs ~0.5-0.7.
    low_conf_warn_threshold: float = 0.55
    # "confidence_gated" (auto-accept clean+confident) or "verify_everything".
    verification_policy: str = "confidence_gated"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
