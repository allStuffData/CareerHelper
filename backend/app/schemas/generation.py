"""Pydantic schemas for generation endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GenerationCreateRequest(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    job_description: str = Field(min_length=1)
    template_version_id: Optional[int] = Field(default=None, ge=1)


class GenerationResponse(BaseModel):
    id: str
    company: str
    role: str
    status: str
    stage: str
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    events_url: str
    pdf_url: Optional[str] = None
    tex_url: Optional[str] = None


class GenerationListResponse(BaseModel):
    items: list[GenerationResponse]
    count: int


class ProgressEventResponse(BaseModel):
    generation_id: str
    status: str
    stage: str
    message: Optional[str] = None
    percent: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: Optional[str] = None
