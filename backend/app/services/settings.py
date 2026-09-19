"""Runtime settings for the reusable CareerHelper service layer.

This module centralises project paths and provider configuration so the
services (prompt construction, LLM client, LaTeX compilation, storage) do not
have to reach into ``Scripts/config.py`` or read environment variables
themselves.

It reads the same environment variables and repo-root ``.env`` file as the
existing CLI config, so existing setups keep working unchanged:

    LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS,
    OPENCODE_GO_API_KEY, OPENCODE_GO_BASE_URL,
    KIMI_API_KEY, KIMI_BASE_URL,
    OPENAI_API_KEY, OPENAI_API_BASE,
    ANTHROPIC_API_KEY,
    LATEX_ENGINE, LATEX_RUNS
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

try:  # python-dotenv is optional; env vars work fine without it
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only without the dep
    load_dotenv = None  # type: ignore[assignment]


# backend/app/services/settings.py -> parents[3] is the repository root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Provider -> (default model, base-url env var, default base url)
_PROVIDER_DEFAULTS: Dict[str, tuple] = {
    "opencode": (
        "deepseek-v4-pro",
        "OPENCODE_GO_BASE_URL",
        "https://opencode.ai/zen/go/v1",
    ),
    "kimi": (
        "kimi-k2-0711-preview",
        "KIMI_BASE_URL",
        "https://api.moonshot.ai/v1",
    ),
    "openai": (
        "gpt-4o",
        "OPENAI_API_BASE",
        "https://api.openai.com/v1",
    ),
    "anthropic": (
        "claude-sonnet-4-20250514",
        None,
        "",
    ),
}

# Providers that speak the OpenAI-compatible chat completions protocol.
OPENAI_COMPATIBLE_PROVIDERS = frozenset({"opencode", "kimi", "openai"})


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of paths and configuration for one run."""

    project_root: Path
    latex_template_dir: Path
    running_template_dir: Path
    output_dir: Path
    base_template: Path
    working_template: Path

    llm_provider: str
    llm_model: str
    llm_temperature: float
    llm_max_tokens: int

    opencode_api_key: str
    opencode_base_url: str
    kimi_api_key: str
    kimi_base_url: str
    openai_api_key: str
    openai_base_url: str
    anthropic_api_key: str

    latex_engine: str
    latex_runs: int

    # ── Provider helpers ────────────────────────────────────────────────

    def api_key_for(self, provider: Optional[str] = None) -> str:
        """Return the configured API key for ``provider`` (or the active one)."""
        provider = (provider or self.llm_provider).lower()
        if provider == "opencode":
            return self.opencode_api_key
        if provider == "kimi":
            return self.kimi_api_key
        if provider == "openai":
            return self.openai_api_key
        if provider == "anthropic":
            return self.anthropic_api_key
        return ""

    def base_url_for(self, provider: Optional[str] = None) -> str:
        """Return the configured base URL for ``provider`` (or the active one)."""
        provider = (provider or self.llm_provider).lower()
        if provider == "opencode":
            return self.opencode_base_url
        if provider == "kimi":
            return self.kimi_base_url
        if provider == "openai":
            return self.openai_base_url
        return ""

    @classmethod
    def from_env(
        cls,
        project_root: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> "Settings":
        """Build settings from ``env`` (defaults to ``os.environ``).

        ``project_root`` defaults to the repository root inferred from this
        file's location.
        """
        env_map: Mapping[str, str] = os.environ if env is None else env
        root = Path(project_root) if project_root is not None else _PROJECT_ROOT

        latex_template_dir = root / "LatexTemplate"
        running_template_dir = root / "RunningTemplate"
        output_dir = root / "Output"

        provider = env_map.get("LLM_PROVIDER", "opencode").strip() or "opencode"

        # Resolve the model lazily so the default matches the active provider.
        default_model, _base_env, default_base = _PROVIDER_DEFAULTS.get(
            provider.lower(), _PROVIDER_DEFAULTS["opencode"]
        )
        model = env_map.get("LLM_MODEL") or default_model

        return cls(
            project_root=root,
            latex_template_dir=latex_template_dir,
            running_template_dir=running_template_dir,
            output_dir=output_dir,
            base_template=latex_template_dir / "GopalKumar_Resume.tex",
            working_template=running_template_dir / "GopalKumar_Resume.tex",
            llm_provider=provider,
            llm_model=model,
            llm_temperature=_as_float(env_map.get("LLM_TEMPERATURE"), 0.3),
            llm_max_tokens=_as_int(env_map.get("LLM_MAX_TOKENS"), 8000),
            opencode_api_key=env_map.get("OPENCODE_GO_API_KEY", ""),
            opencode_base_url=env_map.get(
                "OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1"
            ),
            kimi_api_key=env_map.get("KIMI_API_KEY", ""),
            kimi_base_url=env_map.get(
                "KIMI_BASE_URL", "https://api.moonshot.ai/v1"
            ),
            openai_api_key=env_map.get("OPENAI_API_KEY", ""),
            openai_base_url=env_map.get(
                "OPENAI_API_BASE", "https://api.openai.com/v1"
            ),
            anthropic_api_key=env_map.get("ANTHROPIC_API_KEY", ""),
            latex_engine=env_map.get("LATEX_ENGINE", "pdflatex"),
            latex_runs=_as_int(env_map.get("LATEX_RUNS"), 2),
        )


def _as_float(value: Optional[str], default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Optional[str], default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_settings(
    project_root: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Settings:
    """Load ``.env`` (if available) and return a :class:`Settings` instance.

    ``.env`` is only loaded when ``env`` is not supplied, so callers/tests can
    pass an explicit environment and get deterministic behaviour.
    """
    root = Path(project_root) if project_root is not None else _PROJECT_ROOT
    if env is None and load_dotenv is not None:
        load_dotenv(root / ".env")
    return Settings.from_env(project_root=root, env=env)
