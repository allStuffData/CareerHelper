"""Application configuration.

Values are read from environment variables (optionally via a ``.env`` file at
the repository root). The prefix ``CAREERHELPER_`` keeps these settings from
colliding with the existing CLI environment (``LLM_MODEL`` etc.); the LLM keys
are read under both prefixes so Phase 1 and the CLI keep working unchanged.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings for the FastAPI application layer."""

    model_config = SettingsConfigDict(
        env_prefix="CAREERHELPER_",
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CareerHelper API"
    environment: str = "development"

    # ── Storage ──────────────────────────────────────────────────────────
    database_path: Path = Field(default=_REPO_ROOT / "backend" / "data" / "careerhelper.db")
    artifacts_dir: Path = Field(default=_REPO_ROOT / "backend" / "data" / "artifacts")
    resources_dir: Path = Field(default=_REPO_ROOT / "resources")
    templates_dir: Path = Field(default=_REPO_ROOT / "resources" / "templates" / "latex")
    default_template_path: Optional[Path] = Field(
        default=_REPO_ROOT / "resources" / "templates" / "latex" / "GopalKumar_Resume.tex"
    )

    # ── LaTeX ────────────────────────────────────────────────────────────
    latex_engine: str = "pdflatex"
    latex_runs: int = 2
    latex_timeout_seconds: int = 60

    # ── LLM / OpenCode ───────────────────────────────────────────────────
    llm_provider: str = "opencode"
    llm_model: str = "kimi-k3"
    opencode_go_base_url: str = "https://opencode.ai/zen/go/v1"
    opencode_go_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # ── Server ───────────────────────────────────────────────────────────
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)

    @field_validator(
        "database_path",
        "artifacts_dir",
        "resources_dir",
        "templates_dir",
        "default_template_path",
        mode="before",
    )
    @classmethod
    def _expand_path(cls, value: object) -> object:
        if value in (None, ""):
            return None
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = (_REPO_ROOT / path).resolve()
        return path

    @model_validator(mode="after")
    def _fallback_to_cli_env(self) -> "Settings":
        """Honour the CLI/Phase-1 env var names when prefixed ones are unset."""
        import os

        if self.opencode_go_api_key is None:
            object.__setattr__(
                self, "opencode_go_api_key", os.getenv("OPENCODE_GO_API_KEY") or None
            )
        if self.openai_api_key is None:
            object.__setattr__(
                self, "openai_api_key", os.getenv("OPENAI_API_KEY") or None
            )
        if os.getenv("LLM_MODEL") and self.llm_model == "kimi-k3":
            object.__setattr__(self, "llm_model", os.getenv("LLM_MODEL"))
        if os.getenv("LATEX_ENGINE") and self.latex_engine == "pdflatex":
            object.__setattr__(self, "latex_engine", os.getenv("LATEX_ENGINE"))
        return self

    @property
    def llm_api_key(self) -> Optional[str]:
        """Return the key for the configured provider, if any."""
        if self.llm_provider == "opencode":
            return self.opencode_go_api_key
        if self.llm_provider == "anthropic":
            import os

            return os.getenv("ANTHROPIC_API_KEY") or None
        return self.openai_api_key

    def ensure_directories(self) -> None:
        """Create the writable directories the app needs at runtime."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    @property
    def allowed_artifact_roots(self) -> tuple[Path, ...]:
        """Directories that generated artifacts are allowed to live in."""
        roots = {self.artifacts_dir.resolve()}
        if self.resources_dir is not None:
            roots.add(self.resources_dir.resolve())
        return tuple(roots)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
