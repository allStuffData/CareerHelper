"""Generation API tests: submit, poll, SSE, downloads, delete."""

from __future__ import annotations

import json
from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.integration import ServiceAdapter
from tests.conftest import wait_for_status

PAYLOAD = {
    "company": "Stripe",
    "role": "Technical Program Manager",
    "job_description": "Lead cross-functional programs.",
}


def test_create_generation_completes_and_downloads(client):
    response = client.post("/api/generations", json=PAYLOAD)
    assert response.status_code == 202
    body = response.json()
    generation_id = body["id"]
    assert body["status"] in ("queued", "running")
    assert body["events_url"].endswith(f"/{generation_id}/events")
    assert body["pdf_url"] is None

    completed = wait_for_status(client, generation_id)
    assert completed["status"] == "completed"
    assert completed["stage"] == "completed"
    assert completed["pdf_url"] == f"/api/generations/{generation_id}/pdf"
    assert completed["tex_url"] == f"/api/generations/{generation_id}/tex"
    assert completed["model"] == "fake-model"
    assert completed["prompt_tokens"] == 123

    pdf = client.get(completed["pdf_url"])
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]
    assert f"{generation_id}.pdf" in unquote(
        pdf.headers["content-disposition"]
    )

    tex = client.get(completed["tex_url"])
    assert tex.status_code == 200
    assert "documentclass" in tex.text
    assert f"{generation_id}.tex" in unquote(
        tex.headers["content-disposition"]
    )


def test_generation_id_follows_phase1_naming_contract(client):
    from app.services.integration import build_generation_id

    response = client.post("/api/generations", json=PAYLOAD)
    generation_id = response.json()["id"]

    assert generation_id == build_generation_id(
        PAYLOAD["company"], PAYLOAD["role"]
    )
    assert generation_id.startswith("GopalKumar_")
    assert "Stripe" in generation_id


def test_duplicate_same_day_request_is_disambiguated(client):
    first = client.post("/api/generations", json=PAYLOAD).json()["id"]
    second = client.post("/api/generations", json=PAYLOAD).json()["id"]

    assert first != second
    assert second == f"{first}-2"
    # Both are persisted and addressable independently.
    assert client.get(f"/api/generations/{first}").status_code == 200
    assert client.get(f"/api/generations/{second}").status_code == 200


def test_create_generation_failure_is_recorded(client, adapter, settings):
    adapter.fail = True
    settings.opencode_go_api_key = "test-key"
    response = client.post("/api/generations", json=PAYLOAD)
    assert response.status_code == 202
    generation_id = response.json()["id"]

    failed = wait_for_status(client, generation_id)
    assert failed["status"] == "failed"
    assert failed["stage"] == "failed"
    assert failed["error_code"] == "compile_failed"
    assert "compilation failed" in failed["error_message"]
    assert failed["pdf_url"] is None

    assert client.get(f"/api/generations/{generation_id}/pdf").status_code == 404


def test_events_stream_reports_progress(client):
    response = client.post("/api/generations", json=PAYLOAD)
    generation_id = response.json()["id"]

    events = []
    with client.stream(
        "GET", f"/api/generations/{generation_id}/events"
    ) as stream:
        assert stream.status_code == 200
        for line in stream.iter_lines():
            if not line.startswith("data:"):
                continue
            event = json.loads(line[len("data:") :].strip())
            events.append(event)
            if event["stage"] in ("completed", "failed"):
                break

    stages = [event["stage"] for event in events]
    assert stages[0] == "queued"
    assert "calling_kimi" in stages
    assert stages[-1] == "completed"

    terminal = events[-1]
    assert terminal["generation_id"] == generation_id
    assert terminal["status"] == "completed"
    assert terminal["pdf_filename"] == f"{generation_id}.pdf"
    assert terminal["tex_filename"] == f"{generation_id}.tex"


def test_list_generations(client):
    first = client.post("/api/generations", json=PAYLOAD).json()
    second = client.post("/api/generations", json=PAYLOAD).json()
    wait_for_status(client, first["id"])
    wait_for_status(client, second["id"])

    response = client.get("/api/generations")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert {item["id"] for item in body["items"]} == {first["id"], second["id"]}


def test_delete_generation_removes_record_and_artifacts(client, settings):
    response = client.post("/api/generations", json=PAYLOAD)
    generation_id = response.json()["id"]
    completed = wait_for_status(client, generation_id)
    pdf_path = settings.artifacts_dir / f"{generation_id}.pdf"
    assert pdf_path.exists()

    delete = client.delete(f"/api/generations/{generation_id}")
    assert delete.status_code == 204
    assert client.get(f"/api/generations/{generation_id}").status_code == 404
    assert not pdf_path.exists()


def test_get_unknown_generation_returns_404(client):
    assert client.get("/api/generations/does-not-exist").status_code == 404
    assert client.get("/api/generations/does-not-exist/pdf").status_code == 404
    assert client.get("/api/generations/does-not-exist/events").status_code == 404


def test_create_rejects_unknown_template_version(client):
    payload = {**PAYLOAD, "template_version_id": 424242}
    response = client.post("/api/generations", json=payload)
    assert response.status_code == 404


def test_create_validates_payload(client):
    assert client.post("/api/generations", json={"company": "", "role": "x", "job_description": "y"}).status_code == 422
    response = client.post(
        "/api/generations",
        json={"company": "C", "role": "R", "job_description": ""},
    )
    assert response.status_code == 422


def test_missing_phase1_services_marks_generation_failed(settings, store, jobs):
    app = create_app(
        settings=settings, store=store, jobs=jobs, adapter=ServiceAdapter()
    )
    with TestClient(app) as test_client:
        response = test_client.post("/api/generations", json=PAYLOAD)
        assert response.status_code == 202
        generation_id = response.json()["id"]
        failed = wait_for_status(test_client, generation_id)
    assert failed["status"] == "failed"
    assert failed["error_code"] in ("unexpected_error", "generation_failed")
