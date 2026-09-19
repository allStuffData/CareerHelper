"""Filesystem storage boundaries and safe artifact naming.

Owns everything that touches the filesystem so the LLM/LaTeX services stay
pure and testable:

  * ``sanitize_filename_component`` / ``build_generation_id`` /
    ``build_artifact_filename`` — safe, deterministic names.
  * ``ensure_within_directory`` — reject path traversal (including ``..`` and
    symlink escapes) before writing.
  * ``write_working_template`` / ``store_artifact`` — bounded writes.

Generated artifacts must never be committed; see ``.gitignore``.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9_\- ]")


class StorageBoundaryError(ValueError):
    """Raised when a path would escape its allowed directory."""


def sanitize_filename_component(value: str, max_length: int = 30) -> str:
    """Return a filesystem-safe component derived from ``value``.

    Mirrors the original behaviour: strip every character that is not
    ``[a-zA-Z0-9_- ]``, truncate to ``max_length``, then trim surrounding
    whitespace.
    """
    cleaned = _SAFE_FILENAME_RE.sub("", value or "")
    return cleaned[:max_length].strip()


def build_generation_id(
    company: str,
    role: str,
    when: Optional[datetime] = None,
    prefix: str = "GopalKumar",
) -> str:
    """Build the canonical, filesystem-safe generation id / artifact stem.

    Produces the legacy ``<prefix>_<company>_<role>_<date>`` shape so the CLI
    keeps emitting ``Output/GopalKumar_Company_Role_Date.pdf``.
    """
    date_str = (when or datetime.now()).strftime("%Y%m%d")
    safe_company = sanitize_filename_component(company)
    safe_role = sanitize_filename_component(role)
    return f"{prefix}_{safe_company}_{safe_role}_{date_str}"


def build_artifact_filename(generation_id: str, extension: str = "pdf") -> str:
    """Return a safe artifact filename for ``generation_id``."""
    safe_id = sanitize_filename_component(generation_id, max_length=120)
    if not safe_id:
        safe_id = "resume"
    extension = sanitize_filename_component(extension, max_length=10).lstrip(".")
    if not extension:
        extension = "pdf"
    return f"{safe_id}.{extension}"


def ensure_within_directory(path: Path, directory: Path) -> Path:
    """Return ``path`` if it lives inside ``directory``, else raise.

    Both paths are resolved first, so ``..`` segments and symlinks cannot be
    used to escape the target directory.
    """
    resolved_path = Path(path).resolve()
    resolved_dir = Path(directory).resolve()
    try:
        resolved_path.relative_to(resolved_dir)
    except ValueError as exc:
        raise StorageBoundaryError(
            f"Refusing to write outside {resolved_dir}: {resolved_path}"
        ) from exc
    return resolved_path


def build_artifact_path(
    output_dir: Path,
    generation_id: str,
    extension: str = "pdf",
) -> Path:
    """Return a safe artifact destination inside ``output_dir``."""
    filename = build_artifact_filename(generation_id, extension=extension)
    return ensure_within_directory(Path(output_dir) / filename, output_dir)


def write_working_template(tex: str, working_template: Path) -> Path:
    """Write LaTeX source to the working path, creating its directory."""
    working_template = Path(working_template)
    working_template.parent.mkdir(parents=True, exist_ok=True)
    working_template.write_text(tex, encoding="utf-8")
    return working_template


def store_artifact(
    source_path: Path,
    output_dir: Path,
    generation_id: str,
    extension: Optional[str] = None,
) -> Path:
    """Copy ``source_path`` into ``output_dir`` under a safe artifact name.

    Returns the destination path. Never follows ``..`` outside ``output_dir``.
    """
    import shutil

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = extension or Path(source_path).suffix.lstrip(".") or "pdf"
    destination = build_artifact_path(output_dir, generation_id, extension=ext)
    shutil.copy2(source_path, destination)
    return destination
