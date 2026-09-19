"""Storage (SQLite) tests."""

from __future__ import annotations

from app.models.generation import Generation, GenerationStage, GenerationStatus


def _generation(gid: str = "gen-1") -> Generation:
    return Generation(
        id=gid,
        company="Stripe",
        role="TPM",
        job_description="We need a TPM.",
    )


def test_create_and_get_generation(store):
    created = store.create_generation(_generation())
    assert created.created_at is not None

    fetched = store.get_generation("gen-1")
    assert fetched is not None
    assert fetched.company == "Stripe"
    assert fetched.status == GenerationStatus.QUEUED
    assert fetched.stage == GenerationStage.QUEUED


def test_update_generation_persists_fields(store):
    store.create_generation(_generation())
    updated = store.update_generation(
        "gen-1",
        status=GenerationStatus.COMPLETED,
        stage=GenerationStage.COMPLETED,
        pdf_path="/tmp/out.pdf",
        prompt_tokens=10,
        completion_tokens=20,
        model="kimi-k3",
    )
    assert updated is not None
    assert updated.status == GenerationStatus.COMPLETED
    assert updated.stage == GenerationStage.COMPLETED
    assert updated.pdf_path == "/tmp/out.pdf"
    assert updated.prompt_tokens == 10
    assert updated.completion_tokens == 20
    assert updated.model == "kimi-k3"


def test_update_ignores_unknown_columns(store):
    store.create_generation(_generation())
    updated = store.update_generation("gen-1", bogus="nope", model="m")
    assert updated is not None
    assert updated.model == "m"


def test_list_generations_is_newest_first(store):
    store.create_generation(_generation("gen-a"))
    store.create_generation(_generation("gen-b"))
    store.create_generation(_generation("gen-c"))
    ids = [item.id for item in store.list_generations()]
    assert ids == ["gen-c", "gen-b", "gen-a"]


def test_delete_generation(store):
    store.create_generation(_generation())
    assert store.delete_generation("gen-1") is True
    assert store.get_generation("gen-1") is None
    assert store.delete_generation("gen-1") is False


def test_template_version_lookup_returns_none_when_absent(store):
    assert store.get_template_version_latex(999) is None


def test_is_healthy(store):
    assert store.is_healthy() is True
