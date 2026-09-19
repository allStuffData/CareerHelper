"""FastAPI application factory for the CareerHelper backend (Phase 2).

Run with::

    uvicorn app.main:app --reload --port 8000

The app owns health checks, generation orchestration, SQLite persistence, SSE
progress, and PDF/LaTeX artifact downloads. The resume pipeline itself lives in
the Phase 1 services resolved by :mod:`app.services.integration`.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import generations, health
from app.core.config import Settings, get_settings
from app.services.integration import ServiceAdapter, resolve_services
from app.services.job_runner import GenerationRunner
from app.services.jobs import JobManager
from app.services.storage import GenerationStore

logger = logging.getLogger(__name__)


def create_app(
    settings: Optional[Settings] = None,
    store: Optional[GenerationStore] = None,
    jobs: Optional[JobManager] = None,
    adapter: Optional[ServiceAdapter] = None,
) -> FastAPI:
    """Build a configured FastAPI application.

    Dependencies can be injected so tests can supply an in-memory store, a
    fake job manager, or a stubbed Phase 1 adapter.
    """
    settings = settings or get_settings()
    settings.ensure_directories()

    store = store or GenerationStore(settings.database_path)
    jobs = jobs or JobManager()
    adapter = adapter or resolve_services()
    runner = GenerationRunner(
        store=store,
        jobs=jobs,
        adapter=adapter,
        default_template_path=settings.default_template_path,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        jobs.bind_loop(asyncio.get_running_loop())
        if not adapter.available:
            logger.warning(
                "Phase 1 services are not available (missing: %s); "
                "generation requests will fail until they land.",
                ", ".join(adapter.missing) or "run_generation",
            )
        try:
            yield
        finally:
            await jobs.shutdown()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.store = store
    app.state.jobs = jobs
    app.state.adapter = adapter
    app.state.runner = runner

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(generations.router)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": "/api/health",
        }

    return app


app = create_app()
