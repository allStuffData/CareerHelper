"""Template endpoints: list, create, inspect, and version LaTeX templates."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import get_store
from app.models.template import Template, TemplateVersion
from app.schemas.template import (
    TemplateCreateRequest,
    TemplateDetailResponse,
    TemplateListResponse,
    TemplateResponse,
    TemplateVersionCreateRequest,
    TemplateVersionResponse,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])
logger = logging.getLogger(__name__)


# ── serialisation ────────────────────────────────────────────────────────
def _to_response(template: Template) -> TemplateResponse:
    return TemplateResponse(**template.to_dict())


def _version_to_response(
    version: TemplateVersion, include_content: bool = False
) -> TemplateVersionResponse:
    payload = version.to_dict(include_content=include_content)
    return TemplateVersionResponse(**payload)


def _get_or_404(store, template_id: int) -> Template:
    template = store.get_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template '%s' not found" % template_id,
        )
    return template


# ── endpoints ────────────────────────────────────────────────────────────
@router.get("", response_model=TemplateListResponse)
def list_templates(request: Request) -> TemplateListResponse:
    """List every template with its active version number."""
    store = get_store(request)
    items = [_to_response(t) for t in store.list_templates()]
    return TemplateListResponse(items=items, count=len(items))


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateCreateRequest, request: Request
) -> TemplateResponse:
    """Create a template and activate its first version."""
    store = get_store(request)
    template = store.create_template(
        name=payload.name,
        latex_content=payload.latex_content,
        description=payload.description,
        original_filename=payload.original_filename,
    )
    logger.info("template %s created (name=%r)", template.id, template.name)
    return _to_response(template)


@router.get("/{template_id}", response_model=TemplateDetailResponse)
def get_template(template_id: int, request: Request) -> TemplateDetailResponse:
    """Template detail including its version history (newest first)."""
    store = get_store(request)
    template = _get_or_404(store, template_id)
    versions = [
        _version_to_response(v, include_content=True)
        for v in store.list_template_versions(template_id)
    ]
    return TemplateDetailResponse(
        **_to_response(template).model_dump(), versions=versions
    )


@router.post(
    "/{template_id}/versions",
    response_model=TemplateVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_template_version(
    template_id: int, payload: TemplateVersionCreateRequest, request: Request
) -> TemplateVersionResponse:
    """Append an immutable version and make it the active one."""
    store = get_store(request)
    _get_or_404(store, template_id)
    version: Optional[TemplateVersion] = store.add_template_version(
        template_id, payload.latex_content, set_active=True
    )
    if version is None:  # pragma: no cover - guarded by _get_or_404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template '%s' not found" % template_id,
        )
    logger.info("template %s version %s created", template_id, version.version)
    return _version_to_response(version)
