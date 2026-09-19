"""SQLite persistence for generations (Phase 2).

Uses the standard-library :mod:`sqlite3` module so the local-first backend has
no ORM dependency. A single connection guarded by a lock keeps the in-process
asyncio job manager simple; the schema is written to be compatible with the
data model in ``docs/nextjs-fastapi-plan.md`` and can later move to PostgreSQL
without changing the API layer.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.generation import Generation, GenerationStage, GenerationStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    description       TEXT,
    original_filename TEXT,
    active_version_id INTEGER,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS template_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id   INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    version       INTEGER NOT NULL,
    latex_content TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generations (
    id                  TEXT PRIMARY KEY,
    template_version_id INTEGER REFERENCES template_versions(id) ON DELETE SET NULL,
    company             TEXT NOT NULL,
    role                TEXT NOT NULL,
    job_description     TEXT NOT NULL,
    status              TEXT NOT NULL,
    stage               TEXT NOT NULL,
    model               TEXT,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    error_code          TEXT,
    error_message       TEXT,
    tex_path            TEXT,
    pdf_path            TEXT,
    created_at          TEXT NOT NULL,
    started_at          TEXT,
    completed_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_generations_created_at
    ON generations(created_at);
CREATE INDEX IF NOT EXISTS idx_generations_status
    ON generations(status);
CREATE INDEX IF NOT EXISTS idx_template_versions_template_id
    ON template_versions(template_id);
"""

_GENERATION_COLUMNS = (
    "id",
    "template_version_id",
    "company",
    "role",
    "job_description",
    "status",
    "stage",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "error_code",
    "error_message",
    "tex_path",
    "pdf_path",
    "created_at",
    "started_at",
    "completed_at",
)

# Columns that may be updated after creation.
_MUTABLE_COLUMNS = frozenset(_GENERATION_COLUMNS) - {"id", "company", "role", "created_at"}


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _enum_value(value: object, enum_cls) -> object:
    if isinstance(value, enum_cls):
        return value.value
    return value


class GenerationStore:
    """CRUD operations for generation records and template lookup."""

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.database_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ── lifecycle ────────────────────────────────────────────────────────
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── health ───────────────────────────────────────────────────────────
    def is_healthy(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    # ── generations ──────────────────────────────────────────────────────
    def create_generation(self, generation: Generation) -> Generation:
        if generation.created_at is None:
            generation.created_at = utcnow_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO generations (
                    id, template_version_id, company, role, job_description,
                    status, stage, model, prompt_tokens, completion_tokens,
                    error_code, error_message, tex_path, pdf_path,
                    created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generation.id,
                    generation.template_version_id,
                    generation.company,
                    generation.role,
                    generation.job_description,
                    _enum_value(generation.status, GenerationStatus),
                    _enum_value(generation.stage, GenerationStage),
                    generation.model,
                    generation.prompt_tokens,
                    generation.completion_tokens,
                    generation.error_code,
                    generation.error_message,
                    generation.tex_path,
                    generation.pdf_path,
                    generation.created_at,
                    generation.started_at,
                    generation.completed_at,
                ),
            )
            self._conn.commit()
        return generation

    def update_generation(self, generation_id: str, **fields: object) -> Optional[Generation]:
        updates = {k: v for k, v in fields.items() if k in _MUTABLE_COLUMNS}
        if not updates:
            return self.get_generation(generation_id)
        for key in ("status", "stage"):
            if key in updates and isinstance(updates[key], (GenerationStatus, GenerationStage)):
                updates[key] = updates[key].value
        assignments = ", ".join(f"{column} = ?" for column in updates)
        values = [*updates.values(), generation_id]
        with self._lock:
            cursor = self._conn.execute(
                f"UPDATE generations SET {assignments} WHERE id = ?", values
            )
            self._conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_generation(generation_id)

    def get_generation(self, generation_id: str) -> Optional[Generation]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM generations WHERE id = ?", (generation_id,)
            ).fetchone()
        return self._row_to_generation(row) if row is not None else None

    def list_generations(
        self, limit: int = 50, offset: int = 0
    ) -> list[Generation]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM generations ORDER BY created_at DESC, id DESC "
                "LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_generation(row) for row in rows]

    def delete_generation(self, generation_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM generations WHERE id = ?", (generation_id,)
            )
            self._conn.commit()
        return cursor.rowcount > 0

    # ── template lookup (read-only; CRUD arrives in Phase 4) ─────────────
    def get_template_version_latex(self, version_id: int) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT latex_content FROM template_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        return row["latex_content"] if row is not None else None

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _row_to_generation(row: sqlite3.Row) -> Generation:
        def _get(name: str):
            return row[name] if name in row.keys() else None

        return Generation(
            id=row["id"],
            company=row["company"],
            role=row["role"],
            job_description=row["job_description"],
            template_version_id=_get("template_version_id"),
            status=GenerationStatus(row["status"]),
            stage=GenerationStage(row["stage"]),
            model=_get("model"),
            prompt_tokens=_get("prompt_tokens"),
            completion_tokens=_get("completion_tokens"),
            error_code=_get("error_code"),
            error_message=_get("error_message"),
            tex_path=_get("tex_path"),
            pdf_path=_get("pdf_path"),
            created_at=_get("created_at"),
            started_at=_get("started_at"),
            completed_at=_get("completed_at"),
        )
