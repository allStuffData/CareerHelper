"""Runs a generation job: store <-> job manager <-> Phase 1 adapter.

Phase 2 owns persistence and progress broadcasting; Phase 1 owns the actual
tailoring/compilation. This runner is the glue, keeping the two concerns
separate so either side can be replaced.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from app.contracts import (
    STAGE_CALLING_KIMI,
    STAGE_COMPILING_PDF,
    STAGE_COMPLETED,
    STAGE_FAILED,
    STAGE_PREPARING_PROMPT,
    STAGE_QUEUED,
    STAGE_VALIDATING_LATEX,
    GenerationRequest,
    GenerationResult,
    ProgressEvent,
)
from app.models.generation import Generation, GenerationStage, GenerationStatus
from app.services.integration import ServiceAdapter, normalize_progress
from app.services.job_manager import TERMINAL_STAGES, JobManager

logger = logging.getLogger(__name__)

STAGE_PERCENT = {
    STAGE_QUEUED: 0,
    STAGE_PREPARING_PROMPT: 10,
    STAGE_CALLING_KIMI: 35,
    STAGE_VALIDATING_LATEX: 70,
    STAGE_COMPILING_PDF: 80,
    STAGE_COMPLETED: 100,
    STAGE_FAILED: 100,
}


class GenerationRunner:
    """Submit and execute generation jobs for the API layer."""

    def __init__(
        self,
        store,
        jobs: JobManager,
        adapter: ServiceAdapter,
        default_template_path: Optional[Path] = None,
    ) -> None:
        self.store = store
        self.jobs = jobs
        self.adapter = adapter
        self.default_template_path = default_template_path

    # ── submission ───────────────────────────────────────────────────────
    def submit(self, generation: Generation) -> asyncio.Task:
        self.jobs.open_channel(generation.id)
        self._publish(
            generation.id,
            STAGE_QUEUED,
            status=GenerationStatus.QUEUED,
            message="Queued",
        )
        return self.jobs.submit(generation.id, lambda: self._run(generation))

    async def _run(self, generation: Generation) -> None:
        self.store.update_generation(
            generation.id,
            status=GenerationStatus.RUNNING,
            stage=GenerationStage.PREPARING_PROMPT,
            started_at=from_now(),
        )
        self._publish(
            generation.id,
            STAGE_PREPARING_PROMPT,
            status=GenerationStatus.RUNNING,
            message="Preparing prompt",
        )
        try:
            result = await asyncio.to_thread(self._execute, generation)
        except asyncio.CancelledError:
            self._fail(generation.id, "cancelled", "Generation was cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            logger.exception("Generation %s failed", generation.id)
            self._fail(generation.id, "unexpected_error", str(exc))
            return

        if result.status == STAGE_FAILED or result.error_message:
            self._fail(
                generation.id,
                result.error_code or "generation_failed",
                result.error_message or "Generation failed",
                result=result,
            )
            return
        if not result.pdf_path:
            self._fail(
                generation.id,
                "missing_artifact",
                "Generation finished without a PDF artifact",
                result=result,
            )
            return
        self._complete(generation.id, result)

    # ── worker-thread body ───────────────────────────────────────────────
    def _execute(self, generation: Generation) -> GenerationResult:
        template_latex = self._load_template(generation)
        request = GenerationRequest(
            template_latex=template_latex,
            job_description=generation.job_description,
            company=generation.company,
            role=generation.role,
            generation_id=generation.id,
            template_version_id=generation.template_version_id,
            model=generation.model,
        )

        def on_progress(event: ProgressEvent) -> None:
            self._on_progress(generation.id, event)

        return self.adapter.run(request, on_progress)

    def _load_template(self, generation: Generation) -> str:
        if generation.template_version_id is not None:
            latex = self.store.get_template_version_latex(
                generation.template_version_id
            )
            if latex:
                return latex
        if self.default_template_path is not None:
            path = Path(self.default_template_path)
            if path.exists():
                return path.read_text(encoding="utf-8")
        return ""

    # ── progress ─────────────────────────────────────────────────────────
    def _on_progress(self, generation_id: str, event: ProgressEvent) -> None:
        normalized = normalize_progress(event)
        if normalized is None:
            return
        # Phase 1 emits "done"/"compilation_failed" itself; the runner is the
        # single authority on terminal state, so filter those out here.
        if normalized.stage in TERMINAL_STAGES:
            return
        stage = normalized.stage
        self.store.update_generation(generation_id, stage=stage)
        self._publish(
            generation_id,
            stage,
            status=GenerationStatus.RUNNING,
            message=normalized.message,
            percent=normalized.percent,
        )

    def _publish(
        self,
        generation_id: str,
        stage: str,
        *,
        status: GenerationStatus,
        message: Optional[str] = None,
        percent: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        self.jobs.publish(
            generation_id,
            {
                "generation_id": generation_id,
                "status": status.value,
                "stage": stage,
                "message": message,
                "percent": percent if percent is not None else STAGE_PERCENT.get(stage),
                "error_code": error_code,
                "error_message": error_message,
                "timestamp": from_now(),
            },
        )

    # ── terminals ────────────────────────────────────────────────────────
    def _complete(self, generation_id: str, result: GenerationResult) -> None:
        self.store.update_generation(
            generation_id,
            status=GenerationStatus.COMPLETED,
            stage=GenerationStage.COMPLETED,
            pdf_path=result.pdf_path,
            tex_path=result.tex_path,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            model=result.model,
            completed_at=from_now(),
        )
        self._publish(
            generation_id,
            STAGE_COMPLETED,
            status=GenerationStatus.COMPLETED,
            message="Completed",
        )

    def _fail(
        self,
        generation_id: str,
        error_code: str,
        error_message: str,
        result: Optional[GenerationResult] = None,
    ) -> None:
        fields = {
            "status": GenerationStatus.FAILED,
            "stage": GenerationStage.FAILED,
            "error_code": error_code,
            "error_message": error_message,
            "completed_at": from_now(),
        }
        if result is not None:
            fields.update(
                {
                    "pdf_path": result.pdf_path,
                    "tex_path": result.tex_path,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "model": result.model,
                }
            )
        self.store.update_generation(generation_id, **fields)
        self._publish(
            generation_id,
            STAGE_FAILED,
            status=GenerationStatus.FAILED,
            message=error_message,
            error_code=error_code,
            error_message=error_message,
        )


def from_now() -> str:
    """Local import indirection keeps storage as the timestamp source."""
    from app.db import utcnow_iso

    return utcnow_iso()
