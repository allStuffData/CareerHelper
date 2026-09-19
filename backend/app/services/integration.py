"""Integration adapter between the FastAPI layer and the Phase 1 services.

Phase 1 extracts the resume pipeline into reusable functions:

* ``tailor_resume(template, job_description, company, role) -> TailoringResult``
* ``compile_latex(latex_source, generation_id) -> ArtifactResult``
* ``run_generation(request, progress_callback) -> GenerationResult``

This module resolves those callables from the ``app.services`` package at call
time (so Phase 2 does not hard-depend on Phase 1 landing order) and normalises
their outputs into the dataclasses in :mod:`app.contracts`. Keeping every
Phase 1 assumption here means the two phases can be reconciled in one place.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.contracts import (
    STAGE_CALLING_KIMI,
    STAGE_COMPILING_PDF,
    STAGE_COMPLETED,
    STAGE_FAILED,
    STAGE_PREPARING_PROMPT,
    STAGE_VALIDATING_LATEX,
    ArtifactResult,
    GenerationRequest,
    GenerationResult,
    ProgressCallback,
    ProgressEvent,
    TailoringResult,
)

# Candidate module paths searched for each Phase 1 callable, in priority
# order. Add new locations here when reconciling with the Phase 1 branch.
_RUN_GENERATION_MODULES = (
    "app.services.generation",
    "app.services.pipeline",
    "app.services.tailoring",
)
_TAILOR_RESUME_MODULES = (
    "app.services.tailoring",
    "app.services.generation",
)
_COMPILE_LATEX_MODULES = (
    "app.services.latex",
    "app.services.generation",
)


class ServiceIntegrationError(RuntimeError):
    """Raised when a required Phase 1 callable cannot be resolved."""


def _resolve(modules: tuple[str, ...], attribute: str) -> Optional[Callable]:
    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        func = getattr(module, attribute, None)
        if callable(func):
            return func
    return None


def _field(source: Any, *names: str, default: Any = None) -> Any:
    """Read a field from a dataclass, dict, or object attribute."""
    if source is None:
        return default
    if isinstance(source, dict):
        for name in names:
            if name in source:
                return source[name]
        return default
    for name in names:
        if hasattr(source, name):
            return getattr(source, name)
    return default


def normalize_progress(event: Any) -> Optional[ProgressEvent]:
    """Normalise whatever Phase 1 emits into a :class:`ProgressEvent`."""
    if event is None:
        return None
    if isinstance(event, ProgressEvent):
        return event
    if isinstance(event, str):
        return ProgressEvent(stage=event)
    stage = _field(event, "stage", "state", default="")
    if not stage:
        return None
    return ProgressEvent(
        stage=str(stage),
        message=_field(event, "message", "detail"),
        percent=_field(event, "percent", "progress"),
        error_code=_field(event, "error_code", "code"),
        error_message=_field(event, "error_message", "error"),
    )


def normalize_tailoring(result: Any) -> TailoringResult:
    if isinstance(result, TailoringResult):
        return result
    return TailoringResult(
        latex=_field(result, "latex", "tex", "tex_content", "content", default="") or "",
        raw_response=_field(result, "raw_response", "response"),
        prompt_tokens=_field(result, "prompt_tokens", "input_tokens"),
        completion_tokens=_field(result, "completion_tokens", "output_tokens"),
        model=_field(result, "model"),
    )


def normalize_artifact(result: Any) -> ArtifactResult:
    if isinstance(result, ArtifactResult):
        return result
    if result is None:
        return ArtifactResult(error="compile_latex returned no result")
    return ArtifactResult(
        pdf_path=_as_str(_field(result, "pdf_path", "pdf", "output_pdf")),
        tex_path=_as_str(_field(result, "tex_path", "tex", "output_tex")),
        error=_field(result, "error", "error_message"),
        log_excerpt=_field(result, "log_excerpt", "log"),
    )


def normalize_generation(result: Any) -> GenerationResult:
    if isinstance(result, GenerationResult):
        return result
    if result is None:
        return GenerationResult(
            status=STAGE_FAILED,
            error_code="empty_result",
            error_message="run_generation returned no result",
        )
    status = _field(result, "status", default=STAGE_COMPLETED)
    return GenerationResult(
        latex=_field(result, "latex", "tex", "tex_content", default="") or "",
        pdf_path=_as_str(_field(result, "pdf_path", "pdf", "output_pdf")),
        tex_path=_as_str(_field(result, "tex_path", "tex", "output_tex")),
        status=str(status),
        error_code=_field(result, "error_code", "code"),
        error_message=_field(result, "error_message", "error"),
        prompt_tokens=_field(result, "prompt_tokens", "input_tokens"),
        completion_tokens=_field(result, "completion_tokens", "output_tokens"),
        model=_field(result, "model"),
    )


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


@dataclass
class ServiceAdapter:
    """Resolved Phase 1 callables plus a tolerant ``run`` entry point."""

    tailor_resume: Optional[Callable] = None
    compile_latex: Optional[Callable] = None
    run_generation: Optional[Callable] = None
    source: str = "unresolved"

    @classmethod
    def resolve(cls) -> "ServiceAdapter":
        tailor = _resolve(_TAILOR_RESUME_MODULES, "tailor_resume")
        compile_fn = _resolve(_COMPILE_LATEX_MODULES, "compile_latex")
        run_fn = _resolve(_RUN_GENERATION_MODULES, "run_generation")
        if run_fn is not None:
            source = "run_generation"
        elif tailor is not None or compile_fn is not None:
            source = "compose"
        else:
            source = "unresolved"
        return cls(
            tailor_resume=tailor,
            compile_latex=compile_fn,
            run_generation=run_fn,
            source=source,
        )

    @property
    def available(self) -> bool:
        return self.run_generation is not None or (
            self.tailor_resume is not None and self.compile_latex is not None
        )

    @property
    def missing(self) -> list[str]:
        missing = []
        if self.run_generation is None:
            if self.tailor_resume is None:
                missing.append("tailor_resume")
            if self.compile_latex is None:
                missing.append("compile_latex")
        return missing

    def run(
        self,
        request: GenerationRequest,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> GenerationResult:
        """Execute a generation through the best available Phase 1 entry."""
        if not self.available:
            raise ServiceIntegrationError(
                "Phase 1 services are not available; missing: "
                + ", ".join(self.missing or ["run_generation"])
            )

        emit = _CallbackShim(progress_callback)

        if self.run_generation is not None:
            result = self.run_generation(request, emit)
            return normalize_generation(result)

        return self._compose(request, emit)

    # ── composition fallback ─────────────────────────────────────────────
    def _compose(
        self, request: GenerationRequest, emit: "_CallbackShim"
    ) -> GenerationResult:
        emit(ProgressEvent(stage=STAGE_PREPARING_PROMPT, message="Building prompt"))
        emit(ProgressEvent(stage=STAGE_CALLING_KIMI, message="Tailoring resume"))
        tailoring = normalize_tailoring(
            self.tailor_resume(
                request.template_latex,
                request.job_description,
                request.company,
                request.role,
            )
        )
        if not tailoring.latex.strip():
            return GenerationResult(
                status=STAGE_FAILED,
                error_code="empty_tailoring",
                error_message="tailor_resume returned empty LaTeX",
            )

        emit(ProgressEvent(stage=STAGE_VALIDATING_LATEX, message="Validating LaTeX"))
        emit(ProgressEvent(stage=STAGE_COMPILING_PDF, message="Compiling PDF"))
        artifact = normalize_artifact(
            self.compile_latex(tailoring.latex, request.generation_id)
        )
        if not artifact.ok:
            return GenerationResult(
                status=STAGE_FAILED,
                error_code="compile_failed",
                error_message=artifact.error or "LaTeX compilation failed",
                latex=tailoring.latex,
                tex_path=artifact.tex_path,
                prompt_tokens=tailoring.prompt_tokens,
                completion_tokens=tailoring.completion_tokens,
                model=tailoring.model or request.model,
            )

        return GenerationResult(
            latex=tailoring.latex,
            pdf_path=artifact.pdf_path,
            tex_path=artifact.tex_path,
            status=STAGE_COMPLETED,
            prompt_tokens=tailoring.prompt_tokens,
            completion_tokens=tailoring.completion_tokens,
            model=tailoring.model or request.model,
        )


class _CallbackShim:
    """Wrap a progress callback, normalising Phase 1's event shapes."""

    def __init__(self, callback: Optional[ProgressCallback]):
        self._callback = callback

    def __call__(self, event: Any) -> None:
        if self._callback is None:
            return
        normalized = normalize_progress(event)
        if normalized is not None:
            self._callback(normalized)


def resolve_services() -> ServiceAdapter:
    """Resolve the current Phase 1 service bindings."""
    return ServiceAdapter.resolve()
