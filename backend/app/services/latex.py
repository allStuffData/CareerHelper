"""LaTeX compilation, validation, filename sanitisation, and storage.

This module owns three concerns that the FastAPI backend (and the thin CLI
adapter) share:

  * **Compilation** — run the configured engine, capture log output, and raise
    a typed :class:`LatexCompilationError` on failure.
  * **Filename sanitisation** — turn arbitrary company/role strings into safe
    filesystem components.
  * **Storage boundaries** — write the working ``.tex`` and the final PDF only
    inside the configured directories, rejecting path traversal.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from .settings import Settings, load_settings

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9_\- ]")
_ILLEGAL_PATH_PARTS = ("/", "\\", "\x00")


class LatexCompilationError(RuntimeError):
    """Raised when a LaTeX engine fails or produces no PDF."""

    def __init__(
        self,
        message: str,
        log_tail: str = "",
        returncode: Optional[int] = None,
        engine: Optional[str] = None,
    ) -> None:
        self.log_tail = log_tail
        self.returncode = returncode
        self.engine = engine
        super().__init__(message)


class StorageBoundaryError(ValueError):
    """Raised when a path would escape its allowed directory."""


# ── Filenames ───────────────────────────────────────────────────────────────


def sanitize_filename_component(value: str, max_length: int = 30) -> str:
    """Return a filesystem-safe component derived from ``value``.

    Mirrors the original behaviour: strip every character that is not
    ``[a-zA-Z0-9_- ]``, truncate to ``max_length``, then trim surrounding
    whitespace.
    """
    cleaned = _SAFE_FILENAME_RE.sub("", value or "")
    return cleaned[:max_length].strip()


def build_output_filename(
    company: str,
    role: str,
    when: Optional[datetime] = None,
    prefix: str = "GopalKumar",
) -> str:
    """Build the canonical ``<prefix>_<company>_<role>_<date>.pdf`` filename."""
    date_str = (when or datetime.now()).strftime("%Y%m%d")
    safe_company = sanitize_filename_component(company)
    safe_role = sanitize_filename_component(role)
    return f"{prefix}_{safe_company}_{safe_role}_{date_str}.pdf"


# ── Storage boundaries ──────────────────────────────────────────────────────


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


def build_output_path(
    output_dir: Path,
    company: str,
    role: str,
    when: Optional[datetime] = None,
) -> Path:
    """Return a safe PDF destination path inside ``output_dir``."""
    filename = build_output_filename(company, role, when=when)
    if any(part in filename for part in _ILLEGAL_PATH_PARTS):
        raise StorageBoundaryError(f"Illegal characters in filename: {filename!r}")
    return ensure_within_directory(
        Path(output_dir) / Path(filename).name, output_dir
    )


def write_working_template(tex: str, working_template: Path) -> Path:
    """Write the tailored ``.tex``, creating the directory if needed."""
    working_template = Path(working_template)
    working_template.parent.mkdir(parents=True, exist_ok=True)
    working_template.write_text(tex, encoding="utf-8")
    return working_template


# ── Compilation ───────────────────────────────────────────────────────────


def read_log_tail(log_path: Path, limit: int = 2000) -> str:
    """Return the last ``limit`` characters of a LaTeX log file, if present."""
    try:
        if log_path.exists():
            return log_path.read_text(errors="replace")[-limit:]
    except OSError:
        return ""
    return ""


def compile_latex(
    tex_path: Path,
    company: str,
    role: str,
    settings: Optional[Settings] = None,
    when: Optional[datetime] = None,
) -> Path:
    """Compile ``tex_path`` to PDF and copy it into the ``Output`` directory.

    Returns the destination PDF path. Raises :class:`LatexCompilationError`
    when the engine fails or produces no PDF.
    """
    settings = settings or load_settings()
    tex_path = Path(tex_path)
    tex_dir = tex_path.parent
    tex_name = tex_path.name
    engine = settings.latex_engine
    runs = max(1, settings.latex_runs)

    for _ in range(runs):
        try:
            result = subprocess.run(
                [
                    engine,
                    "-interaction=nonstopmode",
                    "-output-directory",
                    str(tex_dir),
                    tex_name,
                ],
                cwd=str(tex_dir),
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            # e.g. the engine binary is not installed / not on PATH.
            raise LatexCompilationError(
                f"Could not run LaTeX engine {engine!r}: {exc}",
                returncode=None,
                engine=engine,
            ) from exc
        if result.returncode != 0:
            log_tail = read_log_tail(tex_path.with_suffix(".log"))
            if not log_tail:
                log_tail = (result.stderr or "")[-1000:]
            raise LatexCompilationError(
                f"LaTeX compilation failed (exit {result.returncode}).",
                log_tail=log_tail,
                returncode=result.returncode,
                engine=engine,
            )

    pdf = tex_path.with_suffix(".pdf")
    if not pdf.exists():
        raise LatexCompilationError(
            "PDF not found after compilation.",
            returncode=0,
            engine=engine,
        )

    return store_pdf(pdf, settings.output_dir, company, role, when=when)


def store_pdf(
    pdf_path: Path,
    output_dir: Path,
    company: str,
    role: str,
    when: Optional[datetime] = None,
) -> Path:
    """Copy ``pdf_path`` into ``output_dir`` with a sanitised name."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = build_output_path(output_dir, company, role, when=when)
    shutil.copy2(pdf_path, destination)
    return destination
