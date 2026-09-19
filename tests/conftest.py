"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

# The OpenCode model diagnostics are standalone scripts, not pytest suites;
# they require network access and an API key, so keep pytest from importing
# or collecting them (see also ``__test__ = False`` in each file).
collect_ignore = ["test_all_opencode_models.py", "test_deepseek_v4.py"]

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.contracts import (
    STAGE_CALLING_KIMI,
    STAGE_COMPILING_PDF,
    STAGE_COMPLETED,
    STAGE_FAILED,
    STAGE_PREPARING_PROMPT,
    GenerationResult,
    ProgressEvent,
)
from app.core.config import Settings
from app.main import create_app
from app.services.job_manager import JobManager
from app.db import GenerationStore

MINIMAL_TEX = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "Hello resume\n"
    "\\end{document}\n"
)


class FakeAdapter:
    """Stand-in for the Phase 1 service adapter.

    Writes fake artifacts and emits a realistic sequence of progress events,
    so tests exercise storage, jobs, SSE, and downloads without any external
    LLM or ``pdflatex`` process.
    """

    def __init__(
        self,
        artifacts_dir: Path,
        *,
        fail: bool = False,
        fail_code: str = "compile_failed",
        pdf_bytes: bytes = b"%PDF-1.4\n% fake pdf\n",
    ) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.fail = fail
        self.fail_code = fail_code
        self.pdf_bytes = pdf_bytes
        self.calls: list = []
        self.source = "fake"

    @property
    def available(self) -> bool:
        return True

    @property
    def missing(self) -> list[str]:
        return []

    def run(self, request, progress_callback=None):
        self.calls.append(request)
        if progress_callback is not None:
            progress_callback(ProgressEvent(stage=STAGE_PREPARING_PROMPT, message="prep"))
            progress_callback({"stage": "extracting_keywords", "message": "keywords"})
            progress_callback(ProgressEvent(stage=STAGE_CALLING_KIMI, message="kimi"))
            progress_callback(ProgressEvent(stage=STAGE_COMPILING_PDF, message="compile"))

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        tex_path = self.artifacts_dir / f"{request.generation_id}.tex"
        tex_path.write_text(request.template_latex, encoding="utf-8")

        if self.fail:
            return GenerationResult(
                latex=request.template_latex,
                tex_path=str(tex_path),
                status=STAGE_FAILED,
                error_code=self.fail_code,
                error_message="LaTeX compilation failed: undefined control sequence",
                model="fake-model",
            )

        pdf_path = self.artifacts_dir / f"{request.generation_id}.pdf"
        pdf_path.write_bytes(self.pdf_bytes)
        return GenerationResult(
            latex=request.template_latex,
            pdf_path=str(pdf_path),
            tex_path=str(tex_path),
            status=STAGE_COMPLETED,
            prompt_tokens=123,
            completion_tokens=456,
            model="fake-model",
        )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    resources = tmp_path / "resources"
    templates = resources / "templates" / "latex"
    templates.mkdir(parents=True, exist_ok=True)
    default_template = templates / "resume.tex"
    default_template.write_text(MINIMAL_TEX, encoding="utf-8")
    return Settings(
        database_path=tmp_path / "careerhelper.db",
        artifacts_dir=tmp_path / "artifacts",
        resources_dir=resources,
        templates_dir=templates,
        default_template_path=default_template,
        phase1_output_dir=resources / "output",
        phase1_workspace_dir=resources / "workspace",
        opencode_go_api_key="test-key",
        llm_model="kimi-k3",
        latex_engine="pdflatex",
    )


@pytest.fixture
def store(settings: Settings) -> GenerationStore:
    store = GenerationStore(settings.database_path)
    yield store
    store.close()


@pytest.fixture
def jobs() -> JobManager:
    return JobManager()


@pytest.fixture
def adapter(settings: Settings) -> FakeAdapter:
    return FakeAdapter(settings.artifacts_dir)


@pytest.fixture
def app(settings, store, jobs, adapter):
    return create_app(settings=settings, store=store, jobs=jobs, adapter=adapter)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def wait_for_status(client: TestClient, generation_id: str, timeout: float = 5.0) -> dict:
    """Poll a generation until it reaches a terminal state."""
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/generations/{generation_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in ("completed", "failed"):
            return last
        time.sleep(0.02)
    raise AssertionError(f"Generation did not finish in time: {last}")
