"""Seed a default template from the canonical LaTeX resume on disk.

The generation flow needs *some* template to exist before a user has uploaded
one, otherwise a fresh install can only fail. The canonical resume file is
gitignored (it is personal), so this is best-effort: if the file is absent the
app still starts and the user uploads a template through the UI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.db import GenerationStore
from app.models.template import Template

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_NAME = "Default resume"
DEFAULT_TEMPLATE_DESCRIPTION = (
    "Seeded from the canonical LaTeX resume found on the server."
)


def seed_default_template(
    store: GenerationStore, default_template_path: Optional[Path | str]
) -> Optional[Template]:
    """Create the default template once, if none exists and the file is usable.

    Returns the created template, or ``None`` when seeding was skipped because
    a template already exists, the canonical file is missing/unreadable, or its
    contents are blank.
    """
    try:
        if store.count_templates() > 0:
            return None
    except Exception:  # pragma: no cover - defensive
        logger.warning("could not count templates; skipping seed", exc_info=True)
        return None

    if not default_template_path:
        return None

    path = Path(default_template_path)
    if not path.is_file():
        logger.info("default template file not found at %s; skipping seed", path)
        return None

    try:
        latex_content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("could not read default template at %s", path, exc_info=True)
        return None

    if not latex_content.strip():
        logger.info("default template at %s is empty; skipping seed", path)
        return None

    template = store.create_template(
        name=DEFAULT_TEMPLATE_NAME,
        latex_content=latex_content,
        description=DEFAULT_TEMPLATE_DESCRIPTION,
        original_filename=path.name,
    )
    logger.info("seeded template %s from %s", template.id, path)
    return template
