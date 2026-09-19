"""Generation endpoints: submit, inspect, stream progress, download artifacts."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import get_jobs, get_runner, get_settings, get_store
from app.contracts import STAGE_COMPLETED, STAGE_FAILED
from app.models.generation import Generation, GenerationStatus
from app.schemas.generation import (
    GenerationCreateRequest,
    GenerationListResponse,
    GenerationResponse,
)
from app.services.integration import artifact_filename, build_generation_id

router = APIRouter(prefix="/api/generations", tags=["generations"])
logger = logging.getLogger(__name__)


# ── serialisation ────────────────────────────────────────────────────────
def _artifact_usable(path_str: Optional[str], settings) -> bool:
    """Non-raising predicate sibling of :func:`_resolve_artifact`.

    ``_to_response`` only advertises URLs, so it must not hand the browser a
    link that 404s or 403s on click. Reusing the resolver keeps one source of
    truth for "is this artifact servable" (exists, non-empty, allowed root).
    """
    if not path_str:
        return False
    try:
        _resolve_artifact(path_str, settings)
    except HTTPException:
        return False
    return True


def _to_response(generation: Generation, settings) -> GenerationResponse:
    base = f"/api/generations/{generation.id}"
    completed = generation.status == GenerationStatus.COMPLETED
    pdf_url = (
        f"{base}/pdf"
        if completed and _artifact_usable(generation.pdf_path, settings)
        else None
    )
    # A failed run keeps its rejected .tex on purpose (debuggability), but the
    # URL field advertises a deliverable, so it is gated like the PDF: a
    # zero-byte or out-of-root file must not look like a successful artifact.
    tex_url = (
        f"{base}/tex"
        if completed and _artifact_usable(generation.tex_path, settings)
        else None
    )
    return GenerationResponse(
        id=generation.id,
        company=generation.company,
        role=generation.role,
        status=generation.status.value,
        stage=generation.stage.value,
        model=generation.model,
        prompt_tokens=generation.prompt_tokens,
        completion_tokens=generation.completion_tokens,
        error_code=generation.error_code,
        error_message=generation.error_message,
        created_at=generation.created_at,
        started_at=generation.started_at,
        completed_at=generation.completed_at,
        events_url=f"{base}/events",
        pdf_url=pdf_url,
        tex_url=tex_url,
    )


def _get_or_404(store, generation_id: str) -> Generation:
    generation = store.get_generation(generation_id)
    if generation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generation '{generation_id}' not found",
        )
    return generation


def _unique_generation_id(store, base_id: str) -> str:
    """Return ``base_id`` or a disambiguated sibling for same-day collisions.

    Phase 1's ``build_generation_id`` is deterministic per company/role/day, so
    two requests can share it. Persistence needs a unique key; the canonical id
    is kept as-is for the common case and only suffixed on a real collision.
    """
    if store.get_generation(base_id) is None:
        return base_id
    suffix = 2
    while True:
        candidate = f"{base_id}-{suffix}"
        if store.get_generation(candidate) is None:
            return candidate
        suffix += 1


def _resolve_artifact(path_str: str, settings) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (settings.resources_dir / path).resolve()
    else:
        path = path.resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
        )
    if path.stat().st_size == 0:
        # A zero-byte .tex/.pdf means the run died before writing real content
        # (e.g. an empty model response). Serving it as 200 with an empty body
        # looks like success to the browser, so treat it as unavailable.
        logger.warning("Refusing to serve empty artifact: %s", path)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact is empty",
        )
    roots = settings.allowed_artifact_roots
    if roots and not any(path == root or root in path.parents for root in roots):
        logger.warning("Blocked artifact access outside allowed roots: %s", path)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Artifact path is outside the allowed directories",
        )
    return path


# ── endpoints ────────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_generation(
    payload: GenerationCreateRequest, request: Request
) -> GenerationResponse:
    store = get_store(request)
    if payload.template_version_id is not None:
        latex = store.get_template_version_latex(payload.template_version_id)
        if latex is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Template version '{payload.template_version_id}' not found"
                ),
            )

    generation_id = _unique_generation_id(
        store, build_generation_id(payload.company, payload.role)
    )
    generation = Generation(
        id=generation_id,
        company=payload.company,
        role=payload.role,
        job_description=payload.job_description,
        template_version_id=payload.template_version_id,
    )
    store.create_generation(generation)
    get_runner(request).submit(generation)
    return _to_response(generation, get_settings(request))


@router.get("", response_model=GenerationListResponse)
def list_generations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> GenerationListResponse:
    items = get_store(request).list_generations(limit=limit, offset=offset)
    settings = get_settings(request)
    return GenerationListResponse(
        items=[_to_response(item, settings) for item in items], count=len(items)
    )


@router.get("/{generation_id}", response_model=GenerationResponse)
def get_generation(generation_id: str, request: Request) -> GenerationResponse:
    return _to_response(
        _get_or_404(get_store(request), generation_id), get_settings(request)
    )


@router.get("/{generation_id}/events")
async def generation_events(generation_id: str, request: Request) -> StreamingResponse:
    store = get_store(request)
    jobs = get_jobs(request)
    generation = _get_or_404(store, generation_id)

    already_terminal = generation.status in (
        GenerationStatus.COMPLETED,
        GenerationStatus.FAILED,
    )

    async def _stream() -> AsyncIterator[str]:
        if already_terminal and not jobs.has_events(generation_id):
            yield _sse(_terminal_snapshot(generation))
            return
        async for event in jobs.subscribe(generation_id):
            if await request.is_disconnected():
                break
            yield _sse(event)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _terminal_snapshot(generation: Generation) -> dict:
    stage = (
        STAGE_COMPLETED
        if generation.status == GenerationStatus.COMPLETED
        else STAGE_FAILED
    )
    event = {
        "generation_id": generation.id,
        "status": generation.status.value,
        "stage": stage,
        "message": generation.error_message,
        "percent": 100,
        "error_code": generation.error_code,
        "error_message": generation.error_message,
        "timestamp": generation.completed_at,
    }
    if generation.pdf_path:
        event["pdf_path"] = generation.pdf_path
        event["pdf_filename"] = Path(generation.pdf_path).name
    if generation.tex_path:
        event["tex_path"] = generation.tex_path
        event["tex_filename"] = Path(generation.tex_path).name
    return event


def _sse(event: dict) -> str:
    return f"event: progress\ndata: {json.dumps(event)}\n\n"


@router.get("/{generation_id}/pdf")
def download_pdf(generation_id: str, request: Request) -> FileResponse:
    generation = _get_or_404(get_store(request), generation_id)
    if not generation.pdf_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF artifact is not available",
        )
    path = _resolve_artifact(generation.pdf_path, get_settings(request))
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=artifact_filename(generation.pdf_path, generation.id, "pdf"),
    )


@router.get("/{generation_id}/tex")
def download_tex(generation_id: str, request: Request) -> FileResponse:
    generation = _get_or_404(get_store(request), generation_id)
    if not generation.tex_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LaTeX artifact is not available",
        )
    path = _resolve_artifact(generation.tex_path, get_settings(request))
    return FileResponse(
        path,
        media_type="application/x-tex",
        filename=artifact_filename(generation.tex_path, generation.id, "tex"),
    )


@router.delete("/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generation(generation_id: str, request: Request) -> Response:
    store = get_store(request)
    settings = get_settings(request)
    generation = _get_or_404(store, generation_id)
    for artifact in (generation.pdf_path, generation.tex_path):
        if not artifact:
            continue
        try:
            path = _resolve_artifact(artifact, settings)
        except HTTPException:
            continue
        try:
            path.unlink()
        except OSError as exc:  # noqa: PERF203
            logger.warning("Could not delete artifact %s: %s", path, exc)
    store.delete_generation(generation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
