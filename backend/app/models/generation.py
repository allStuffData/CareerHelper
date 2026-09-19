"""Domain models for generation records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GenerationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationStage(str, Enum):
    QUEUED = "queued"
    PREPARING_PROMPT = "preparing_prompt"
    CALLING_KIMI = "calling_kimi"
    VALIDATING_LATEX = "validating_latex"
    COMPILING_PDF = "compiling_pdf"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATUSES = {GenerationStatus.COMPLETED, GenerationStatus.FAILED}


@dataclass
class Generation:
    """A single resume-tailoring request and its lifecycle metadata."""

    id: str
    company: str
    role: str
    job_description: str
    template_version_id: Optional[int] = None
    status: GenerationStatus = GenerationStatus.QUEUED
    stage: GenerationStage = GenerationStage.QUEUED
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    tex_path: Optional[str] = None
    pdf_path: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company": self.company,
            "role": self.role,
            "job_description": self.job_description,
            "template_version_id": self.template_version_id,
            "status": self.status.value,
            "stage": self.stage.value,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "tex_path": self.tex_path,
            "pdf_path": self.pdf_path,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
