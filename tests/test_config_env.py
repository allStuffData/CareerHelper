"""Phase 2 configuration reads the CLI/Phase-1 env var names.

pydantic-settings uses the ``CAREERHELPER_`` prefix, and its ``env_file``
support does not populate ``os.environ``. These tests pin the fallback that
lets the same unprefixed variables (``OPENCODE_GO_API_KEY``, ``LLM_PROVIDER``,
``LLM_MODEL``, ``LATEX_ENGINE``) configure the FastAPI health/config layer, so
``/api/health`` agrees with Phase 1's ``load_settings``.
"""

from __future__ import annotations

import pytest

from app.core import config


def test_unprefixed_env_names_feed_settings(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "env-opencode-key")
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LATEX_ENGINE", "xelatex")

    settings = config.Settings()

    assert settings.opencode_go_api_key == "env-opencode-key"
    assert settings.openai_api_key == "env-openai-key"
    assert settings.llm_provider == "openai"
    assert settings.llm_api_key == "env-openai-key"
    assert settings.llm_model == "gpt-4o"
    assert settings.latex_engine == "xelatex"


def test_opencode_provider_uses_opencode_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "env-opencode-key")

    settings = config.Settings()

    assert settings.llm_provider == "opencode"
    assert settings.llm_api_key == "env-opencode-key"


def test_dotenv_loader_is_available_for_unprefixed_keys():
    # python-dotenv is an optional dependency; when present the .env file is
    # loaded so the os.getenv fallback can see the key. Without it, settings
    # still work from real environment variables.
    pytest.importorskip("dotenv")
    assert config.load_dotenv is not None


def test_default_model_matches_phase1_effective_default(monkeypatch):
    # /api/health must report the model the Phase 1 pipeline actually uses.
    monkeypatch.delenv("LLM_MODEL", raising=False)
    from app.services.settings import Settings as Phase1Settings

    phase1_model = Phase1Settings.from_env(env={}).llm_model
    assert config.Settings(_env_file=None).llm_model == phase1_model
