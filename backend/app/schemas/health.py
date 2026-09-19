"""Pydantic schemas for health endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    name: str
    status: str = Field(description="One of: ok, degraded, error")
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = Field(description="Overall status: ok, degraded or error")
    version: str
    checks: list[HealthCheck]
