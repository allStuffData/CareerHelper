"""Domain models for resume templates and their versions.

A :class:`Template` is a named resume with a stable identity; its LaTeX lives in
:class:`TemplateVersion` rows so editing a resume never destroys the exact source
a past generation was built from. ``active_version_id`` is the version new
generations use unless a caller pins a specific one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Template:
    """A named resume template plus summary fields for list responses."""

    id: int
    name: str
    description: Optional[str] = None
    original_filename: Optional[str] = None
    active_version_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Derived: the version *number* of the active version, and how many exist.
    active_version: Optional[int] = None
    version_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "original_filename": self.original_filename,
            "active_version_id": self.active_version_id,
            "active_version": self.active_version,
            "version_count": self.version_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class TemplateVersion:
    """One immutable revision of a template's LaTeX source."""

    id: int
    template_id: int
    version: int
    latex_content: str
    created_at: Optional[str] = None

    def to_dict(self, include_content: bool = False) -> dict:
        payload = {
            "id": self.id,
            "template_id": self.template_id,
            "version": self.version,
            "created_at": self.created_at,
        }
        if include_content:
            payload["latex_content"] = self.latex_content
        return payload
