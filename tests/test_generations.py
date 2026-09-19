"""Generation API tests: submit, poll, SSE, downloads, delete."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.generation import GenerationStatus
from app.services.integration import ServiceAdapter
from tests.conftest import FakeAdapter, wait_for_status

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
    # The rejected LaTeX is kept on disk for debugging, but it is not a
    # deliverable, so the response must not advertise it.
    assert failed["tex_url"] is None

    assert client.get(f"/api/generations/{generation_id}/pdf").status_code == 404
    # ...while the raw artifact stays reachable for post-mortems.
    assert client.get(f"/api/generations/{generation_id}/tex").status_code == 200


def test_empty_artifact_is_not_served_as_success(client, store):
    """A zero-byte .pdf/.tex must 404, and stop being advertised.

    Truncated runs used to leave empty files behind and the API answered 200
    with an empty body, which looks like a successful download to the browser.
    """
    generation_id = client.post("/api/generations", json=PAYLOAD).json()["id"]
    completed = wait_for_status(client, generation_id)
    assert completed["pdf_url"] is not None

    # Truncate exactly what the API resolves for this generation: the pdf from
    # the adapter and the per-generation .tex snapshot in the output dir.
    row = store.get_generation(generation_id)
    for stored_path in (row.pdf_path, row.tex_path):
        assert stored_path, "fixture should have produced both artifacts"
        Path(stored_path).write_bytes(b"")

    assert client.get(f"/api/generations/{generation_id}/pdf").status_code == 404
    assert client.get(f"/api/generations/{generation_id}/tex").status_code == 404

    # The listing must stop offering links that cannot be fulfilled either.
    after = client.get(f"/api/generations/{generation_id}").json()
    assert after["pdf_url"] is None
    assert after["tex_url"] is None


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


def test_tex_artifact_is_snapshotted_per_generation(settings, store, jobs):
    """A later run must not clobber an earlier generation's downloadable LaTeX."""
    shared = settings.phase1_workspace_dir / "GopalKumar_Resume.tex"
    adapter = FakeAdapter(settings.artifacts_dir, shared_tex_path=shared)
    app = create_app(settings=settings, store=store, jobs=jobs, adapter=adapter)

    with TestClient(app) as test_client:
        first = test_client.post("/api/generations", json=PAYLOAD).json()["id"]
        wait_for_status(test_client, first)

        stored = store.get_generation(first)
        assert stored.tex_path is not None
        assert stored.tex_path.startswith(str(settings.phase1_output_dir))
        assert stored.tex_path != str(shared)

        # Simulate a subsequent generation overwriting the shared working file.
        shared.write_text("CLOBBERED", encoding="utf-8")

        tex = test_client.get(f"/api/generations/{first}/tex")
        assert tex.status_code == 200
        assert "CLOBBERED" not in tex.text
        assert "documentclass" in tex.text


def _orphan(gid: str):
    from app.models.generation import (
        Generation,
        GenerationStage,
        GenerationStatus,
    )

    return Generation(
        id=gid,
        company="Stripe",
        role="Technical Program Manager",
        job_description="Lead cross-functional programs.",
        status=GenerationStatus.RUNNING,
        stage=GenerationStage.CALLING_KIMI,
    )


def test_events_stream_terminates_for_an_orphaned_generation(client, store):
    """A row whose process died must end its SSE stream instead of hanging.

    The UI waits on this stream; before the fix it stayed open forever because
    no producer would ever publish the terminal event.
    """
    store.create_generation(_orphan("orphan-events"))

    with client.stream(
        "GET", "/api/generations/orphan-events/events"
    ) as stream:
        assert stream.status_code == 200
        events = [
            json.loads(line[len("data:") :].strip())
            for line in stream.iter_lines()
            if line.startswith("data:")
        ]

    assert len(events) == 1
    assert events[0]["generation_id"] == "orphan-events"
    assert events[0]["status"] == "failed"
    assert events[0]["stage"] == "failed"
    assert events[0]["error_code"] == "interrupted"

    row = store.get_generation("orphan-events")
    assert row.status == GenerationStatus.FAILED
    assert row.error_code == "interrupted"

    # The reaped row is terminal, so /history stops showing it as live.
    assert client.get("/api/generations/orphan-events/events").status_code == 200


def test_startup_reaps_generations_left_behind_by_a_previous_run(
    settings, store, jobs
):
    store.create_generation(_orphan("orphan-startup"))

    app = create_app(
        settings=settings,
        store=store,
        jobs=jobs,
        adapter=FakeAdapter(settings.artifacts_dir),
    )
    with TestClient(app):
        listing = store.list_generations()
    assert [row.id for row in listing if row.status not in (GenerationStatus.COMPLETED, GenerationStatus.FAILED)] == []

    row = store.get_generation("orphan-startup")
    assert row.status == GenerationStatus.FAILED
    assert row.error_code == "interrupted"
    assert row.completed_at is not None


def test_client_disconnect_does_not_fail_a_live_generation(
    settings, store, jobs
):
    """Ending the SSE stream early must not reap a generation that is running.

    Browsers disconnect constantly in normal use (navigating away, reload, or
    the Next dev server remounting the view). The row belongs to the job, which
    will publish its own terminal event, so a disconnect has to close the
    stream without writing ``failed`` over a live run.
    """
    import asyncio
    import threading
    import time

    from starlette.requests import Request

    from app.api.generations import generation_events
    from app.contracts import (
        STAGE_CALLING_KIMI,
        STAGE_PREPARING_PROMPT,
        ProgressEvent,
    )

    release = threading.Event()

    class BlockingAdapter(FakeAdapter):
        """Run long enough for a subscriber to attach, then finish normally."""

        def run(self, request, progress_callback=None):
            if progress_callback is not None:
                progress_callback(
                    ProgressEvent(stage=STAGE_PREPARING_PROMPT, message="prep")
                )
                progress_callback(
                    ProgressEvent(stage=STAGE_CALLING_KIMI, message="kimi")
                )
            release.wait(timeout=10)
            return super().run(request)

    app = create_app(
        settings=settings,
        store=store,
        jobs=jobs,
        adapter=BlockingAdapter(settings.artifacts_dir),
    )

    with TestClient(app) as client:
        created = client.post("/api/generations", json=PAYLOAD)
        assert created.status_code == 202
        generation_id = created.json()["id"]

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not jobs.has_events(generation_id):
            time.sleep(0.01)
        assert jobs.has_events(generation_id)
        assert jobs.is_active(generation_id)

        async def disconnected():
            return {"type": "http.disconnect"}

        request = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": f"/api/generations/{generation_id}/events",
                "raw_path": b"/events",
                "query_string": b"",
                "headers": [],
                "server": ("testserver", 80),
                "client": ("testclient", 12345),
                "root_path": "",
                "app": app,
            },
            disconnected,
        )

        async def drain() -> list:
            response = await generation_events(generation_id, request)
            return [chunk async for chunk in response.body_iterator]

        try:
            assert asyncio.run(drain()) == []

            row = store.get_generation(generation_id)
            assert row.status == GenerationStatus.RUNNING
            assert row.error_code is None
        finally:
            release.set()

        assert wait_for_status(client, generation_id)["status"] == "completed"
        assert store.get_generation(generation_id).error_code is None
