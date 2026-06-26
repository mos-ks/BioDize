"""Image preprocessing (deskew / denoise / contrast).

Placeholder for the hackathon scaffold — returns the page unchanged. When OCR
quality on real scans demands it, plug OpenCV here (deskew via Hough/projection,
denoise, adaptive threshold) BEFORE the OCR layer.
"""
from __future__ import annotations

from app.pipeline.ingest import PageImage


def preprocess(page: PageImage) -> PageImage:
    # TODO: deskew + denoise + contrast normalization (OpenCV).
    return page
