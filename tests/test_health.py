"""Health endpoint tests."""

from __future__ import annotations

import app.api.health as health_module
from app.main import create_app


def test_health_reports_ok_when_dependencies_present(client, monkeypatch):
    monkeypatch.setattr(
        health_module.shutil, "which", lambda name: "/usr/bin/pdflatex"
    )
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    checks = {check["name"]: check for check in body["checks"]}
    assert set(checks) == {"database", "storage", "latex", "llm"}
    assert checks["database"]["status"] == "ok"
    assert checks["storage"]["status"] == "ok"
    assert checks["latex"]["status"] == "ok"
    assert checks["llm"]["status"] == "ok"


def test_health_degraded_without_pdflatex_or_key(settings, store, jobs, adapter, monkeypatch):
    monkeypatch.setattr(health_module.shutil, "which", lambda name: None)
    settings.opencode_go_api_key = None
    app = create_app(settings=settings, store=store, jobs=jobs, adapter=adapter)
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        body = test_client.get("/api/health").json()
    assert body["status"] == "degraded"
    checks = {check["name"]: check for check in body["checks"]}
    assert checks["latex"]["status"] == "degraded"
    assert checks["llm"]["status"] == "degraded"
    assert checks["database"]["status"] == "ok"
