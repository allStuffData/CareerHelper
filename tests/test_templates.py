"""Template management, seeding, and generation retry."""

from __future__ import annotations

from app.models.generation import Generation, GenerationStatus

from tests.conftest import wait_for_status

UPLOADED_TEX = "UPLOADED LATEX v1"
UPLOADED_TEX_V2 = "UPLOADED LATEX v2"


def _create_template(client, name="My template", latex=UPLOADED_TEX):
    return client.post(
        "/api/templates",
        json={"name": name, "latex_content": latex, "description": "test"},
    )


def test_default_template_is_seeded_from_canonical_file(client, settings):
    body = client.get("/api/templates").json()
    assert body["count"] == 1
    seeded = body["items"][0]
    assert seeded["name"] == "Default resume"
    assert seeded["original_filename"] == "resume.tex"
    assert seeded["active_version_id"] is not None
    assert seeded["active_version"] == 1
    assert seeded["version_count"] == 1
    assert "latex_content" not in seeded


def test_create_template_appears_in_list_and_detail(client):
    created = _create_template(client, name="Tailored")
    assert created.status_code == 201
    template = created.json()
    assert template["name"] == "Tailored"
    assert template["active_version_id"] is not None

    listing = client.get("/api/templates").json()
    assert listing["count"] == 2
    assert {t["name"] for t in listing["items"]} == {"Default resume", "Tailored"}

    detail = client.get(f"/api/templates/{template['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["versions"]) == 1
    assert body["versions"][0]["latex_content"] == UPLOADED_TEX


def test_create_template_rejects_blank_fields(client):
    assert client.post(
        "/api/templates", json={"name": "   ", "latex_content": UPLOADED_TEX}
    ).status_code == 422
    assert client.post(
        "/api/templates", json={"name": "ok", "latex_content": "   "}
    ).status_code == 422


def test_missing_template_is_404(client):
    assert client.get("/api/templates/9999").status_code == 404
    assert client.post(
        "/api/templates/9999/versions", json={"latex_content": UPLOADED_TEX}
    ).status_code == 404


def test_new_version_becomes_active(client):
    template_id = _create_template(client).json()["id"]
    added = client.post(
        f"/api/templates/{template_id}/versions",
        json={"latex_content": UPLOADED_TEX_V2},
    )
    assert added.status_code == 201
    assert added.json()["version"] == 2

    detail = client.get(f"/api/templates/{template_id}").json()
    assert detail["version_count"] == 2
    assert detail["active_version"] == 2
    assert detail["versions"][0]["latex_content"] == UPLOADED_TEX_V2
    assert detail["versions"][0]["version"] == 2


def test_generation_uses_the_selected_template_version(client, adapter):
    template_id = _create_template(client, latex=UPLOADED_TEX).json()["id"]
    version_id = client.get(f"/api/templates/{template_id}").json()["active_version_id"]

    response = client.post(
        "/api/generations",
        json={
            "company": "Stripe",
            "role": "Engineer",
            "job_description": "Build payments.",
            "template_version_id": version_id,
        },
    )
    assert response.status_code == 202
    generation_id = response.json()["id"]
    assert wait_for_status(client, generation_id)["status"] == "completed"

    assert len(adapter.calls) == 1
    assert adapter.calls[0].template_latex == UPLOADED_TEX


def test_generation_with_unknown_template_version_is_404(client):
    response = client.post(
        "/api/generations",
        json={
            "company": "Stripe",
            "role": "Engineer",
            "job_description": "Build payments.",
            "template_version_id": 4242,
        },
    )
    assert response.status_code == 404


def _completed(client, company='Stripe', role='Engineer'):
    response = client.post('/api/generations', json={
        'company': company, 'role': role, 'job_description': 'Build payments.'})
    assert response.status_code == 202
    gen_id = response.json()['id']
    assert wait_for_status(client, gen_id)['status'] == 'completed'
    return gen_id


def test_retry_appends_a_new_generation(client, adapter):
    original = _completed(client)
    retried = client.post(f'/api/generations/{original}/retry')
    assert retried.status_code == 202
    new_id = retried.json()['id']
    assert new_id != original
    assert wait_for_status(client, new_id)['status'] == 'completed'
    ids = [g['id'] for g in client.get('/api/generations').json()['items']]
    assert original in ids and new_id in ids
    assert len(adapter.calls) == 2


def test_retry_rejects_unfinished_generation(client, store):
    pending = Generation(id='pending-1', company='Stripe', role='Engineer',
                         job_description='Build payments.')
    assert pending.status is GenerationStatus.QUEUED
    store.create_generation(pending)
    response = client.post('/api/generations/pending-1/retry')
    assert response.status_code == 409
    assert 'finished' in response.json()['detail']


def test_retry_unknown_generation_is_404(client):
    assert client.post('/api/generations/nope/retry').status_code == 404
