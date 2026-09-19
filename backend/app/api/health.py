"""Health endpoint.

Reports the state of the local dependencies the generation pipeline needs:
the SQLite database, writable artifact storage, the LaTeX engine, and LLM
configuration. Individual failures degrade the overall status instead of
taking the API down, so the frontend can render diagnostics.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Request

from app.core import __version__
from app.api.deps import get_settings, get_store
from app.schemas.health import HealthCheck, HealthResponse
from app.services.latex import resolve_latex_engine

router = APIRouter(prefix="/api", tags=["system"])


def _check_database(store) -> HealthCheck:
    try:
        healthy = store.is_healthy()
    except Exception as exc:  # noqa: BLE001
        return HealthCheck(name="database", status="error", detail=str(exc))
    if healthy:
        return HealthCheck(name="database", status="ok", detail="SQLite reachable")
    return HealthCheck(name="database", status="error", detail="SQLite query failed")


def _check_storage(artifacts_dir: Path) -> HealthCheck:
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=artifacts_dir, prefix=".health-", delete=True
        ):
            pass
    except OSError as exc:
        return HealthCheck(name="storage", status="error", detail=str(exc))
    return HealthCheck(name="storage", status="ok", detail=str(artifacts_dir))


def _check_latex(settings) -> HealthCheck:
    resolved = resolve_latex_engine(settings=settings)
    if resolved:
        return HealthCheck(name="latex", status="ok", detail=resolved)
    return HealthCheck(
        name="latex",
        status="degraded",
        detail=(
            f"'{settings.latex_engine}' was not found on PATH or in common "
            "TeX install locations"
        ),
    )


def _check_llm(settings) -> HealthCheck:
    if settings.llm_api_key:
        return HealthCheck(
            name="llm",
            status="ok",
            detail=f"provider={settings.llm_provider} model={settings.llm_model}",
        )
    return HealthCheck(
        name="llm",
        status="degraded",
        detail=f"No API key configured for provider '{settings.llm_provider}'",
    )


def build_health(settings, store) -> HealthResponse:
    checks = [
        _check_database(store),
        _check_storage(settings.artifacts_dir),
        _check_latex(settings),
        _check_llm(settings),
    ]
    if any(check.status == "error" for check in checks):
        overall = "error"
    elif any(check.status == "degraded" for check in checks):
        overall = "degraded"
    else:
        overall = "ok"
    return HealthResponse(status=overall, version=__version__, checks=checks)


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return build_health(get_settings(request), get_store(request))
