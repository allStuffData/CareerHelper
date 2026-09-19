"""Generation job orchestration.

``run_generation(request, progress_callback)`` is the composition entry point
used by the CLI adapter (and, later, the FastAPI layer). It wires the reusable
services together:

    tailor_resume -> write working .tex -> compile_latex -> store artifact

Progress is reported through an optional callback receiving
:class:`ProgressEvent` objects, so callers can render live status without the
services printing anything themselves.

Privacy: this module never logs resumes, job descriptions, prompts, or
secrets. LLM failures are reported by type/message only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .latex import ArtifactResult, compile_latex
from .llm import LLMError
from .storage import build_generation_id, write_working_template
from .tailoring import LLMCaller, TailoringResult, tailor_resume
from .settings import Settings, load_settings


@dataclass
class GenerationRequest:
    """Inputs for one resume generation run."""

    job_description: str
    company: str
    role: str
    template: Optional[str] = None
    generation_id: Optional[str] = None
    dry_run: bool = False
    when: Optional[datetime] = None
    settings: Optional[Settings] = None
    llm_caller: Optional[LLMCaller] = field(default=None, repr=False)


@dataclass
class ProgressEvent:
    """A single progress notification emitted by :func:`run_generation`."""

    stage: str
    message: str = ""
    path: Optional[Path] = None
    tailoring: Optional[TailoringResult] = field(default=None, repr=False)
    artifact: Optional[ArtifactResult] = field(default=None, repr=False)


ProgressCallback = Callable[[ProgressEvent], None]


@dataclass
class GenerationResult:
    """Outcome of :func:`run_generation`."""

    generation_id: str
    company: str
    role: str
    success: bool
    dry_run: bool = False
    latex_source: str = ""
    tailoring: Optional[TailoringResult] = field(default=None, repr=False)
    artifact: Optional[ArtifactResult] = field(default=None, repr=False)
    tex_path: Optional[Path] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    missing_env_var: Optional[str] = None


def _noop(_event: ProgressEvent) -> None:
    return None


def run_generation(
    request: GenerationRequest,
    progress_callback: Optional[ProgressCallback] = None,
) -> GenerationResult:
    """Run tailoring + compilation for ``request`` and return the result.

    Raises nothing for expected LLM/compilation failures: configuration errors
    (missing key, unsupported provider) are reported via ``error_type='llm'``
    and compilation failures via ``error_type='compilation'`` plus the
    :class:`ArtifactResult`.
    """
    emit = progress_callback or _noop
    settings = request.settings or load_settings()
    template = (
        request.template
        if request.template is not None
        else settings.base_template.read_text(encoding="utf-8")
    )
    generation_id = request.generation_id or build_generation_id(
        request.company, request.role, when=request.when
    )

    emit(ProgressEvent(stage="tailoring"))

    try:
        tailoring = tailor_resume(
            template,
            request.job_description,
            request.company,
            request.role,
            settings=settings,
            llm_caller=request.llm_caller,
        )
    except LLMError as exc:
        emit(ProgressEvent(stage="done", message=str(exc)))
        return GenerationResult(
            generation_id=generation_id,
            company=request.company,
            role=request.role,
            success=False,
            error=str(exc),
            error_type="llm",
            missing_env_var=getattr(exc, "env_var", None),
        )

    emit(ProgressEvent(stage="tailored", tailoring=tailoring))

    tex_path = write_working_template(tailoring.latex_source, settings.working_template)
    emit(ProgressEvent(stage="tex_written", path=tex_path))

    if request.dry_run:
        emit(ProgressEvent(stage="dry_run", path=tex_path))
        emit(ProgressEvent(stage="done"))
        return GenerationResult(
            generation_id=generation_id,
            company=request.company,
            role=request.role,
            success=True,
            dry_run=True,
            latex_source=tailoring.latex_source,
            tailoring=tailoring,
            tex_path=tex_path,
        )

    emit(ProgressEvent(stage="compiling"))
    artifact = compile_latex(
        tailoring.latex_source, generation_id, settings=settings
    )
    emit(
        ProgressEvent(
            stage="compiled" if artifact.success else "compilation_failed",
            artifact=artifact,
            path=artifact.pdf_path,
        )
    )
    emit(ProgressEvent(stage="done"))

    return GenerationResult(
        generation_id=generation_id,
        company=request.company,
        role=request.role,
        success=artifact.success,
        latex_source=tailoring.latex_source,
        tailoring=tailoring,
        artifact=artifact,
        tex_path=tex_path,
        error=None if artifact.success else artifact.error,
        error_type=None if artifact.success else "compilation",
    )
