"""Integration adapter between the FastAPI layer and the Phase 1 services.

Phase 1's authoritative contracts (``backend/app/services``) are:

* ``tailor_resume(template, job_description, company, role) -> TailoringResult``
  (:mod:`app.services.tailoring`)
* ``compile_latex(latex_source, generation_id) -> ArtifactResult``
  (:mod:`app.services.latex`)
* ``run_generation(request, progress_callback) -> GenerationResult``
  (:mod:`app.services.jobs`)

with ``GenerationRequest`` / ``ProgressEvent`` / ``GenerationResult`` owned by
``app.services.jobs``.

This module resolves those callables at call time (so Phase 2 does not
hard-depend on Phase 1 landing order or module layout) and normalises their
outputs into the dataclasses in :mod:`app.contracts`. Every Phase 1 assumption
lives here, so the two phases can be reconciled in one place: if the real
module paths change, update the ``_*_MODULES`` tuples below.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
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
# order. Phase 1 commit 63d3a10 implements ``run_generation`` in
# ``app.services.jobs`` (the earlier ``pipeline.py`` orchestrator was folded
# into it); ``app.services`` is the package re-export surface. There is no
# ``app.services.generation`` module, so it is deliberately not searched.
_RUN_GENERATION_MODULES = (
    "app.services.jobs",
    "app.services.pipeline",
    "app.services",
)
_TAILOR_RESUME_MODULES = (
    "app.services.tailoring",
    "app.services",
)
_COMPILE_LATEX_MODULES = (
    "app.services.latex",
    "app.services",
)
_BUILD_GENERATION_ID_MODULES = (
    "app.services.storage",
    "app.services",
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


def build_generation_id(company: str, role: str, when: Any = None) -> str:
    """Return the canonical, legacy-compatible generation id.

    Phase 1 owns this naming contract via
    ``app.services.storage.build_generation_id(company, role)``. The API must
    use its output verbatim for persistence, artifact paths, download
    responses, and SSE metadata -- it must never invent an id or filename.

    A compatibility shim reproduces the documented
    ``GopalKumar_<company>_<role>_<YYYYMMDD>`` shape only when Phase 1 is not
    importable (for example in an isolated worktree or the test suite).
    """
    builder = _resolve(_BUILD_GENERATION_ID_MODULES, "build_generation_id")
    if builder is not None:
        try:
            return builder(company, role)
        except TypeError:
            return builder(company, role, when=when)
    return _fallback_generation_id(company, role, when)


def _sanitize_component(value: str, max_length: int = 30) -> str:
    import re

    cleaned = re.sub(r"[^a-zA-Z0-9_\- ]", "", value or "")
    return cleaned[:max_length].strip()


def _fallback_generation_id(company: str, role: str, when: Any = None) -> str:
    from datetime import datetime

    date_str = (when or datetime.now()).strftime("%Y%m%d")
    return (
        f"GopalKumar_{_sanitize_component(company)}_"
        f"{_sanitize_component(role)}_{date_str}"
    )


def artifact_filename(path: Any, generation_id: str, extension: str) -> str:
    """Return the artifact's server-generated filename.

    Prefers the actual stored path name (which Phase 1 already derived from the
    generation id), so the API never recomputes filenames from company/role.
    """
    if path:
        name = Path(str(path)).name
        if name:
            return name
    return f"{generation_id}.{extension.lstrip('.')}"


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


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, Path):
        return str(value)
    return str(value)


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
        error_code=_field(event, "error_code", "code", "error_type"),
        error_message=_field(event, "error_message", "error"),
    )


def normalize_tailoring(result: Any) -> TailoringResult:
    """Normalise Phase 1's ``TailoringResult`` (or a mapping) into ours."""
    if isinstance(result, TailoringResult):
        return result
    return TailoringResult(
        latex=_field(
            result,
            "latex_source",
            "latex",
            "tex",
            "tex_content",
            "content",
            default="",
        )
        or "",
        raw_response=_field(result, "raw_response", "response"),
        prompt_tokens=_field(result, "prompt_tokens", "input_tokens"),
        completion_tokens=_field(result, "completion_tokens", "output_tokens"),
        model=_field(result, "model"),
    )


def normalize_artifact(result: Any) -> ArtifactResult:
    """Normalise Phase 1's ``ArtifactResult`` (or a mapping) into ours."""
    if isinstance(result, ArtifactResult):
        return result
    if result is None:
        return ArtifactResult(error="compile_latex returned no result")
    success = _field(result, "success")
    pdf_path = _as_str(_field(result, "pdf_path", "pdf", "output_pdf"))
    error = _field(result, "error", "error_message")
    if success is False and error is None:
        error = "LaTeX compilation failed"
    return ArtifactResult(
        pdf_path=pdf_path,
        tex_path=_as_str(_field(result, "tex_path", "tex", "output_tex")),
        error=error,
        log_excerpt=_field(result, "log_tail", "log_excerpt", "log"),
    )


def _tokens_from(usage: Any) -> tuple[Optional[int], Optional[int]]:
    if not usage:
        return None, None
    get = usage.get if isinstance(usage, dict) else lambda key, default=None: getattr(
        usage, key, default
    )
    return (
        get("prompt_tokens") or get("input_tokens"),
        get("completion_tokens") or get("output_tokens"),
    )


def normalize_generation(result: Any) -> GenerationResult:
    """Normalise Phase 1's ``GenerationResult`` (or a mapping) into ours."""
    if isinstance(result, GenerationResult):
        return result
    if result is None:
        return GenerationResult(
            status=STAGE_FAILED,
            error_code="empty_result",
            error_message="run_generation returned no result",
        )

    artifact = _field(result, "artifact")
    tailoring = _field(result, "tailoring")
    usage = _field(tailoring, "usage")
    usage_prompt, usage_completion = _tokens_from(usage)

    success = _field(result, "success")
    if success is not None:
        status = STAGE_COMPLETED if success else STAGE_FAILED
    else:
        status = str(_field(result, "status", default=STAGE_COMPLETED))

    pdf_path = _field(result, "pdf_path", "pdf", "output_pdf")
    if pdf_path is None and artifact is not None:
        pdf_path = _field(artifact, "pdf_path")
    tex_path = _field(result, "tex_path", "output_tex")
    if tex_path is None and artifact is not None:
        tex_path = _field(artifact, "tex_path")

    latex = _field(
        result, "latex_source", "latex", "tex", "tex_content", default=""
    )

    return GenerationResult(
        latex=latex or "",
        pdf_path=_as_str(pdf_path),
        tex_path=_as_str(tex_path),
        status=status,
        error_code=_field(result, "error_code", "error_type", "code"),
        error_message=_field(result, "error_message", "error"),
        prompt_tokens=_field(result, "prompt_tokens", "input_tokens")
        or usage_prompt,
        completion_tokens=_field(result, "completion_tokens", "output_tokens")
        or usage_completion,
        model=_field(result, "model") or _field(tailoring, "model"),
    )


def _build_phase1_request(request: GenerationRequest) -> Any:
    """Translate our request into Phase 1's ``GenerationRequest`` if present.

    Falls back to our own request object when Phase 1 is not importable (for
    example in isolation or in tests), so injected callables keep working.
    """
    try:
        from app.services.jobs import (  # type: ignore[import-not-found]
            GenerationRequest as Phase1GenerationRequest,
        )
    except Exception:  # noqa: BLE001 - Phase 1 not installed yet
        return request
    return Phase1GenerationRequest(
        job_description=request.job_description,
        company=request.company,
        role=request.role,
        template=request.template_latex or None,
        generation_id=request.generation_id,
        dry_run=False,
    )


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
            result = self.run_generation(_build_phase1_request(request), emit)
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
