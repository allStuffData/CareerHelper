"""FastAPI dependencies for accessing application state."""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.services.integration import ServiceAdapter
from app.services.job_runner import GenerationRunner
from app.services.job_manager import JobManager
from app.db import GenerationStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> GenerationStore:
    return request.app.state.store


def get_jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def get_runner(request: Request) -> GenerationRunner:
    return request.app.state.runner


def get_adapter(request: Request) -> ServiceAdapter:
    return request.app.state.adapter
