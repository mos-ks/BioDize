"""Background processing job: POST /documents/process_async + GET /documents/jobs/{id}.

Forces the offline stub extractor so the test never makes API calls, then drives
the full async contract: start -> poll -> processed, with the finished record's
processing_ms recorded. Cleans up the document + its history rows afterwards.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "extractor", "stub")  # offline, no API calls
    from app.db.base import init_db
    init_db()
    from app.main import app
    return TestClient(app)


def _cleanup(client: TestClient, document_id: str) -> None:
    from app.db import models
    from app.db.base import SessionLocal
    db = SessionLocal()
    db.query(models.ParameterHistory).filter(
        models.ParameterHistory.document_id == document_id).delete()
    db.commit()
    db.close()
    client.delete(f"/api/v1/documents/{document_id}")


def test_process_async_runs_in_background_and_finishes(client):
    started = client.post("/api/v1/documents/process_async")
    assert started.status_code == 200
    body = started.json()
    job_id = body["job_id"]
    assert body["status"] == "processing"

    snap = None
    for _ in range(100):  # stub run is sub-second; generous ceiling for slow CI
        snap = client.get(f"/api/v1/documents/jobs/{job_id}").json()
        if snap["status"] != "processing":
            break
        time.sleep(0.1)

    assert snap is not None and snap["status"] == "processed", snap
    assert snap["document_id"]
    assert snap["stage"] == "Done"
    assert snap["elapsed_ms"] >= 0

    doc = client.get(f"/api/v1/documents/{snap['document_id']}").json()
    assert doc["processing_ms"] is not None
    assert doc["n_fields"] > 0

    _cleanup(client, snap["document_id"])


def test_unknown_job_is_404(client):
    assert client.get("/api/v1/documents/jobs/does-not-exist").status_code == 404
