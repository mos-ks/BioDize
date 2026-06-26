"""Role distribution stats (for plots + Bayesian priors)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.pipeline.normalize import parse_german_number
from app.schemas.schemas import DistributionOut

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/roles/{role}/distribution", response_model=DistributionOut)
def role_distribution(role: str, bins: int = 10, db: Session = Depends(get_db)) -> DistributionOut:
    fields = (db.query(models.Field)
              .filter(models.Field.role == role,
                      models.Field.status.in_(["auto_accepted", "confirmed", "corrected"]))
              .all())
    values: list[float] = []
    for f in fields:
        v, _ = parse_german_number(f.value_norm or f.value_raw or "")
        if v is not None:
            values.append(v)

    if not values:
        return DistributionOut(role=role, n=0)

    n = len(values)
    mean = sum(values) / n
    std = (sum((v - mean) ** 2 for v in values) / n) ** 0.5
    lo, hi = min(values), max(values)
    hist = _histogram(values, lo, hi, bins)
    return DistributionOut(role=role, n=n, mean=mean, std=std, min=lo, max=hi, histogram=hist)


def _histogram(values: list[float], lo: float, hi: float, bins: int) -> list[dict]:
    if hi == lo:
        return [{"start": lo, "end": hi, "count": len(values)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    return [{"start": lo + i * width, "end": lo + (i + 1) * width, "count": c} for i, c in enumerate(counts)]
