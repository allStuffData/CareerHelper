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
