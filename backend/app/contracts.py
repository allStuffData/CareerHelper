"""Phase 1 <-> Phase 2 service contract.

These dataclasses are the *boundary* between the FastAPI application layer
(Phase 2) and the extracted Python services (Phase 1). Phase 1 owns the real
implementations of ``tailor_resume``, ``compile_latex`` and
``run_generation``; this module only describes the shapes the app relies on.

The integration adapter in :mod:`app.services.integration` normalises whatever
Phase 1 returns into these types, so the two phases can evolve independently
and be reconciled in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# Canonical generation stages, in order. Keep in sync with the plan's state
# machine and with any Phase 1 progress events.
STAGE_QUEUED = "queued"
STAGE_PREPARING_PROMPT = "preparing_prompt"
STAGE_CALLING_KIMI = "calling_kimi"
STAGE_VALIDATING_LATEX = "validating_latex"
STAGE_COMPILING_PDF = "compiling_pdf"
STAGE_COMPLETED = "completed"
STAGE_FAILED = "failed"

GENERATION_STAGES = (
    STAGE_QUEUED,
    STAGE_PREPARING_PROMPT,
    STAGE_CALLING_KIMI,
    STAGE_VALIDATING_LATEX,
    STAGE_COMPILING_PDF,
    STAGE_COMPLETED,
    STAGE_FAILED,
)

# Map loose/legacy stage names Phase 1 might emit onto the canonical set.
# The Phase 1 ``run_generation`` (app.services.jobs) emits: tailoring,
# tailored, tex_written, dry_run, compiling, compiled, compilation_failed,
# done. Terminal stages are filtered by the job runner, which owns the real
# terminal event.
_STAGE_ALIASES = {
    "start": STAGE_QUEUED,
    "starting": STAGE_QUEUED,
    "queued": STAGE_QUEUED,
    "prompt": STAGE_PREPARING_PROMPT,
    "preparing": STAGE_PREPARING_PROMPT,
    "preparing_prompt": STAGE_PREPARING_PROMPT,
    "extracting_keywords": STAGE_PREPARING_PROMPT,
    "tailoring": STAGE_CALLING_KIMI,
    "calling_llm": STAGE_CALLING_KIMI,
    "calling_kimi": STAGE_CALLING_KIMI,
    "kimi": STAGE_CALLING_KIMI,
    "tailored": STAGE_VALIDATING_LATEX,
    "validating": STAGE_VALIDATING_LATEX,
    "validating_latex": STAGE_VALIDATING_LATEX,
    "tex_written": STAGE_VALIDATING_LATEX,
    "dry_run": STAGE_VALIDATING_LATEX,
    "compiling": STAGE_COMPILING_PDF,
    "compiled": STAGE_COMPILING_PDF,
    "compiling_pdf": STAGE_COMPILING_PDF,
    "compiling_latex": STAGE_COMPILING_PDF,
    "compilation_failed": STAGE_FAILED,
    "done": STAGE_COMPLETED,
    "completed": STAGE_COMPLETED,
    "failed": STAGE_FAILED,
    "error": STAGE_FAILED,
}


def normalize_stage(stage: Optional[str]) -> str:
    """Map an arbitrary stage label onto the canonical stage set."""
    if not stage:
        return STAGE_QUEUED
    return _STAGE_ALIASES.get(str(stage).strip().lower(), str(stage).strip())


@dataclass
class ProgressEvent:
    """A single progress update emitted by a running generation."""

    stage: str
    message: Optional[str] = None
    percent: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        self.stage = normalize_stage(self.stage)

    def to_dict(self) -> dict:
        payload = {"stage": self.stage}
        if self.message is not None:
            payload["message"] = self.message
        if self.percent is not None:
            payload["percent"] = self.percent
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        if self.error_message is not None:
            payload["error_message"] = self.error_message
        return payload


# Phase 1 calls this from its worker; it must be thread-safe. The job manager
# wraps it so events can be published from a background thread.
ProgressCallback = Callable[[ProgressEvent], None]


@dataclass
class GenerationRequest:
    """Input to ``run_generation``.

    ``template_latex`` is the canonical resume source; ``job_description``,
    ``company`` and ``role`` are the user-supplied tailoring inputs.
    """

    template_latex: str
    job_description: str
    company: str
    role: str
    generation_id: str
    template_version_id: Optional[int] = None
    model: Optional[str] = None


@dataclass
class TailoringResult:
    """Return value of ``tailor_resume`` (Phase 1)."""

    latex: str
    raw_response: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    model: Optional[str] = None


@dataclass
class ArtifactResult:
    """Return value of ``compile_latex`` (Phase 1)."""

    pdf_path: Optional[str] = None
    tex_path: Optional[str] = None
    error: Optional[str] = None
    log_excerpt: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.pdf_path is not None


@dataclass
class GenerationResult:
    """Return value of ``run_generation`` (Phase 1).

    ``status`` is intentionally a plain string so Phase 1 does not have to
    import the application's enums. The adapter normalises it.
    """

    latex: str = ""
    pdf_path: Optional[str] = None
    tex_path: Optional[str] = None
    status: str = "completed"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    model: Optional[str] = None
