"""Pydantic schemas for template endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    original_filename: Optional[str] = Field(default=None, max_length=255)
    latex_content: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()

    @field_validator("latex_content")
    @classmethod
    def _latex_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("latex_content must not be blank")
        return value


class TemplateVersionCreateRequest(BaseModel):
    latex_content: str = Field(min_length=1)

    @field_validator("latex_content")
    @classmethod
    def _latex_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("latex_content must not be blank")
        return value


class TemplateVersionResponse(BaseModel):
    id: int
    template_id: int
    version: int
    created_at: Optional[str] = None
    # Only populated on template detail, so a UI can preview a revision
    # without shipping every version body in list responses.
    latex_content: Optional[str] = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    original_filename: Optional[str] = None
    active_version_id: Optional[int] = None
    active_version: Optional[int] = None
    version_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TemplateDetailResponse(TemplateResponse):
    versions: list[TemplateVersionResponse] = Field(default_factory=list)


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]
    count: int
