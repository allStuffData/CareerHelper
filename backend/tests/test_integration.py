"""Integration-adapter tests (Phase 1 <-> Phase 2 boundary)."""

from __future__ import annotations

import pytest

from app.contracts import (
    STAGE_CALLING_KIMI,
    STAGE_COMPILING_PDF,
    STAGE_COMPLETED,
    STAGE_FAILED,
    STAGE_PREPARING_PROMPT,
    GenerationRequest,
    TailoringResult,
    ProgressEvent,
    normalize_stage,
)
from app.services.integration import (
    ServiceAdapter,
    ServiceIntegrationError,
    normalize_artifact,
    normalize_generation,
    normalize_progress,
    normalize_tailoring,
)


def _request() -> GenerationRequest:
    return GenerationRequest(
        template_latex="\\documentclass{article}",
        job_description="JD text",
        company="Acme",
        role="PM",
        generation_id="gen-1",
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"stage": "extracting_keywords"}, STAGE_PREPARING_PROMPT),
        ({"stage": "compiling"}, STAGE_COMPILING_PDF),
        ({"stage": "done"}, STAGE_COMPLETED),
        ({"stage": "error"}, STAGE_FAILED),
        ("calling_llm", STAGE_CALLING_KIMI),
        (None, None),
    ],
)
def test_normalize_progress_maps_stage_aliases(raw, expected):
    event = normalize_progress(raw)
    if expected is None:
        assert event is None
    else:
        assert event is not None
        assert event.stage == expected


def test_normalize_stage_passthrough():
    assert normalize_stage("custom_stage") == "custom_stage"
    assert normalize_stage(None) == "queued"


def test_normalize_tailoring_from_object_and_dict():
    from_object = normalize_tailoring(
        TailoringResult(latex="abc", prompt_tokens=1, completion_tokens=2)
    )
    assert from_object.latex == "abc"
    assert from_object.prompt_tokens == 1

    from_dict = normalize_tailoring(
        {"tex_content": "xyz", "input_tokens": 5, "output_tokens": 6, "model": "m"}
    )
    assert from_dict.latex == "xyz"
    assert from_dict.prompt_tokens == 5
    assert from_dict.completion_tokens == 6
    assert from_dict.model == "m"


def test_normalize_artifact_marks_failure():
    artifact = normalize_artifact({"error": "boom"})
    assert artifact.ok is False
    assert artifact.error == "boom"

    ok = normalize_artifact({"pdf_path": "/tmp/a.pdf", "tex_path": "/tmp/a.tex"})
    assert ok.ok is True


def test_normalize_generation_defaults_to_completed():
    result = normalize_generation({"latex": "x", "pdf_path": "/tmp/a.pdf"})
    assert result.status == STAGE_COMPLETED
    assert result.pdf_path == "/tmp/a.pdf"


def test_adapter_prefers_run_generation():
    calls = {}

    def run_generation(request, progress_callback):
        calls["request"] = request
        progress_callback(ProgressEvent(stage=STAGE_CALLING_KIMI))
        return {"latex": "x", "pdf_path": "/tmp/a.pdf", "status": "completed"}

    adapter = ServiceAdapter(run_generation=run_generation, source="run_generation")
    progress: list[ProgressEvent] = []
    result = adapter.run(_request(), progress.append)

    assert adapter.available is True
    assert result.status == STAGE_COMPLETED
    assert calls["request"].company == "Acme"
    assert [event.stage for event in progress] == [STAGE_CALLING_KIMI]


def test_adapter_composes_when_run_generation_absent():
    order: list[str] = []

    def tailor_resume(template, job_description, company, role):
        order.append("tailor")
        return TailoringResult(latex="\\documentclass{article}", prompt_tokens=7)

    def compile_latex(latex_source, generation_id):
        order.append("compile")
        return {"pdf_path": "/tmp/out.pdf", "tex_path": "/tmp/out.tex"}

    adapter = ServiceAdapter(
        tailor_resume=tailor_resume,
        compile_latex=compile_latex,
        source="compose",
    )
    progress: list[ProgressEvent] = []
    result = adapter.run(_request(), progress.append)

    assert order == ["tailor", "compile"]
    assert result.status == STAGE_COMPLETED
    assert result.pdf_path == "/tmp/out.pdf"
    assert result.prompt_tokens == 7
    stages = [event.stage for event in progress]
    assert STAGE_CALLING_KIMI in stages
    assert STAGE_COMPILING_PDF in stages


def test_adapter_reports_missing_tailoring_latex_as_failure():
    adapter = ServiceAdapter(
        tailor_resume=lambda *a: TailoringResult(latex=""),
        compile_latex=lambda *a: {"pdf_path": "/tmp/out.pdf"},
    )
    result = adapter.run(_request())
    assert result.status == STAGE_FAILED
    assert result.error_code == "empty_tailoring"


def test_adapter_unavailable_raises():
    adapter = ServiceAdapter()
    assert adapter.available is False
    assert set(adapter.missing) == {"tailor_resume", "compile_latex"}
    with pytest.raises(ServiceIntegrationError):
        adapter.run(_request())


# ── real Phase 1 dataclass shapes ─────────────────────────────────────────
# Phase 1 owns GenerationResult/TailoringResult/ArtifactResult/ProgressEvent
# in app.services.{jobs,tailoring,latex}. These tests pin the normalisation
# of their real fields without importing Phase 1 or running an LLM/pdflatex.


class _Phase1Artifact:
    def __init__(self, *, success: bool, pdf=None, tex=None, error=None) -> None:
        self.generation_id = "gen-1"
        self.success = success
        self.filename = "gen-1.pdf" if pdf else None
        self.pdf_path = pdf
        self.tex_path = tex
        self.error = error
        self.log_tail = ""


class _Phase1Tailoring:
    def __init__(self) -> None:
        self.latex_source = "\\documentclass{article}"
        self.raw_response = "```latex\n\\documentclass{article}\n```"
        self.prompt = "prompt"
        self.is_valid = True
        self.validation_errors = []
        self.provider = "opencode"
        self.model = "kimi-k3"
        self.usage = {"prompt_tokens": 11, "completion_tokens": 22}


class _Phase1Result:
    def __init__(self, *, success: bool, artifact, tailoring=None, error=None) -> None:
        self.generation_id = "gen-1"
        self.company = "Acme"
        self.role = "PM"
        self.success = success
        self.dry_run = False
        self.latex_source = "\\documentclass{article}"
        self.tailoring = tailoring
        self.artifact = artifact
        self.tex_path = artifact.tex_path
        self.error = error
        self.error_type = None if success else "compilation"
        self.missing_env_var = None


def test_normalize_generation_reads_real_phase1_success_shape(tmp_path):
    pdf = tmp_path / "gen-1.pdf"
    tex = tmp_path / "working.tex"
    artifact = _Phase1Artifact(success=True, pdf=pdf, tex=tex)

    result = normalize_generation(
        _Phase1Result(success=True, artifact=artifact, tailoring=_Phase1Tailoring())
    )

    assert result.status == STAGE_COMPLETED
    assert result.pdf_path == str(pdf)
    assert result.tex_path == str(tex)
    assert result.latex == "\\documentclass{article}"
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 22
    assert result.model == "kimi-k3"
    assert result.error_code is None


def test_normalize_generation_reads_real_phase1_failure_shape():
    artifact = _Phase1Artifact(
        success=False, error="LaTeX source failed validation"
    )
    result = normalize_generation(
        _Phase1Result(
            success=False,
            artifact=artifact,
            error="LaTeX source failed validation",
        )
    )
    assert result.status == STAGE_FAILED
    assert result.error_code == "compilation"
    assert result.pdf_path is None
    assert "validation" in result.error_message


def test_normalize_progress_reads_real_phase1_event_shape():
    from types import SimpleNamespace

    event = normalize_progress(SimpleNamespace(stage="tailoring", message="working"))
    assert event is not None
    assert event.stage == STAGE_CALLING_KIMI
    assert event.message == "working"

    assert normalize_progress(SimpleNamespace(stage="done")).stage == STAGE_COMPLETED
    assert (
        normalize_progress(SimpleNamespace(stage="compilation_failed")).stage
        == STAGE_FAILED
    )


def test_normalize_artifact_reads_real_phase1_shape(tmp_path):
    pdf = tmp_path / "gen-1.pdf"
    artifact = normalize_artifact(
        _Phase1Artifact(success=True, pdf=pdf, tex=tmp_path / "w.tex")
    )
    assert artifact.ok is True
    assert artifact.pdf_path == str(pdf)

    failed = normalize_artifact(
        _Phase1Artifact(success=False, error="LaTeX compilation failed (exit 1).")
    )
    assert failed.ok is False
    assert failed.error


def test_adapter_builds_phase1_request_when_available(monkeypatch):
    """When Phase 1's GenerationRequest is importable, the adapter uses it."""
    import types

    created = {}

    class _Phase1Request:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            created["request"] = self

    fake_jobs = types.ModuleType("app.services.jobs")
    fake_jobs.GenerationRequest = _Phase1Request

    import sys

    monkeypatch.setitem(sys.modules, "app.services.jobs", fake_jobs)

    def run_generation(request, progress_callback):
        return {"success": True, "latex_source": "x", "artifact": None}

    adapter = ServiceAdapter(run_generation=run_generation)
    adapter.run(_request())

    assert created["request"].company == "Acme"
    assert created["request"].template == "\\documentclass{article}"
    assert created["request"].generation_id == "gen-1"
