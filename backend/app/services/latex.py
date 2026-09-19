"""LaTeX compilation boundary.

``compile_latex(latex_source, generation_id)`` is the public entry point used
by the generation job runner and the CLI adapter. It writes the source to a
bounded working path, runs the configured engine with shell escape disabled
and a timeout, and returns an :class:`ArtifactResult` describing what
happened. Expected failures (bad source, engine missing, non-zero exit,
timeout, no PDF) are reported in the result rather than raised so callers can
surface them without crashing.

Security notes:
  * The engine is always invoked with ``-no-shell-escape``.
  * Every run is bounded by ``settings.latex_timeout`` seconds.
  * Only a bounded tail of the LaTeX log is retained (never the full source).
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .response_parser import validate_latex
from .settings import Settings, load_settings
from .storage import store_artifact, write_working_template

_LOG_TAIL_LIMIT = 2000

# Common TeX install locations, searched when the engine is not on PATH.
_COMMON_ENGINE_DIRS = (
    "/Library/TeX/texbin",
    "/opt/homebrew/bin",
    "/usr/bin",
)
# Versioned TeX Live trees (newest first when sorted).
_ENGINE_GLOBS = ("/usr/local/texlive/*/bin/*",)


def resolve_latex_engine(
    engine: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> Optional[str]:
    """Resolve a LaTeX engine name/path to an executable absolute path.

    ``LATEX_ENGINE`` may be a bare name (``pdflatex``) or an absolute path.
    Resolution order:

    1. an absolute, executable path is used as-is;
    2. ``shutil.which`` on ``PATH``;
    3. common install locations (``/Library/TeX/texbin``,
       ``/usr/local/texlive/*/bin/*``, ``/opt/homebrew/bin``, ``/usr/bin``).

    Returns ``None`` when no executable can be found. Callers keep their
    public signatures; this is a shared helper for the compile path and the
    health check so both report the same resolution.
    """
    settings = settings or load_settings()
    requested = (engine if engine is not None else settings.latex_engine) or ""
    requested = requested.strip() or "pdflatex"

    candidate = Path(requested)
    if candidate.is_absolute():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None

    found = shutil.which(requested)
    if found:
        return found

    for directory in _COMMON_ENGINE_DIRS:
        candidate = Path(directory) / requested
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    for pattern in _ENGINE_GLOBS:
        for match in sorted(glob.glob(f"{pattern}/{requested}"), reverse=True):
            if os.access(match, os.X_OK):
                return match

    return None



@dataclass
class ArtifactResult:
    """Outcome of a compilation attempt and (on success) the stored PDF."""

    generation_id: str
    success: bool
    filename: Optional[str] = None
    pdf_path: Optional[Path] = None
    tex_path: Optional[Path] = None
    error: Optional[str] = None
    log_tail: str = field(default="", repr=False)


def read_log_tail(log_path: Path, limit: int = _LOG_TAIL_LIMIT) -> str:
    """Return the last ``limit`` characters of a LaTeX log file, if present."""
    try:
        if log_path.exists():
            return log_path.read_text(errors="replace")[-limit:]
    except OSError:
        return ""
    return ""


def compile_latex(
    latex_source: str,
    generation_id: str,
    settings: Optional[Settings] = None,
    work_dir: Optional[Path] = None,
) -> ArtifactResult:
    """Compile ``latex_source`` and store the PDF under ``generation_id``.

    ``generation_id`` is sanitised before use as the output artifact name; it
    should be built with :func:`backend.app.services.storage.build_generation_id`
    when a human-readable legacy filename is desired.
    """
    settings = settings or load_settings()
    work_dir = Path(work_dir) if work_dir is not None else settings.running_template_dir
    tex_path = work_dir / settings.working_template.name

    issues = validate_latex(latex_source)
    if issues:
        return ArtifactResult(
            generation_id=generation_id,
            success=False,
            tex_path=tex_path,
            error="LaTeX source failed validation: " + "; ".join(issues),
        )

    try:
        write_working_template(latex_source, tex_path)
    except OSError as exc:
        return ArtifactResult(
            generation_id=generation_id,
            success=False,
            error=f"Could not write LaTeX source: {exc}",
        )

    # Resolve the engine to an absolute executable so installs that are not on
    # PATH (e.g. TeX Live under /Library/TeX/texbin) still compile.
    engine = resolve_latex_engine(settings=settings) or settings.latex_engine
    runs = max(1, settings.latex_runs)
    timeout = settings.latex_timeout if settings.latex_timeout > 0 else None
    command = [
        engine,
        "-interaction=nonstopmode",
        "-no-shell-escape",
        "-output-directory",
        str(tex_path.parent),
        tex_path.name,
    ]

    for _ in range(runs):
        try:
            result = subprocess.run(
                command,
                cwd=str(tex_path.parent),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            return ArtifactResult(
                generation_id=generation_id,
                success=False,
                tex_path=tex_path,
                error=f"Could not run LaTeX engine {engine!r}: {exc}",
            )
        except subprocess.TimeoutExpired:
            return ArtifactResult(
                generation_id=generation_id,
                success=False,
                tex_path=tex_path,
                error=f"LaTeX compilation timed out after {settings.latex_timeout}s.",
                log_tail=read_log_tail(tex_path.with_suffix(".log")),
            )

        if result.returncode != 0:
            log_tail = read_log_tail(tex_path.with_suffix(".log"))
            if not log_tail:
                log_tail = (result.stderr or "")[-1000:]
            return ArtifactResult(
                generation_id=generation_id,
                success=False,
                tex_path=tex_path,
                error=f"LaTeX compilation failed (exit {result.returncode}).",
                log_tail=log_tail,
            )

    pdf = tex_path.with_suffix(".pdf")
    if not pdf.exists():
        return ArtifactResult(
            generation_id=generation_id,
            success=False,
            tex_path=tex_path,
            error="PDF not found after compilation.",
        )

    try:
        destination = store_artifact(pdf, settings.output_dir, generation_id)
    except OSError as exc:
        return ArtifactResult(
            generation_id=generation_id,
            success=False,
            tex_path=tex_path,
            error=f"Could not store PDF artifact: {exc}",
        )

    return ArtifactResult(
        generation_id=generation_id,
        success=True,
        filename=destination.name,
        pdf_path=destination,
        tex_path=tex_path,
    )
