"""Provider-agnostic LLM client for resume tailoring.

Supports:
  * OpenCode Zen Go (``opencode``) — OpenAI-compatible chat completions.
  * Kimi / Moonshot (``kimi``) — OpenAI-compatible chat completions.
  * OpenAI (``openai``) — OpenAI-compatible chat completions.
  * Anthropic (``anthropic``) — native Messages API.

Unlike the original CLI helper, this module raises typed exceptions instead of
calling ``sys.exit``; the CLI adapter maps those to user-facing messages and
exit codes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .prompts import SYSTEM_PROMPT
from .settings import OPENAI_COMPATIBLE_PROVIDERS, Settings, load_settings


class LLMError(RuntimeError):
    """Base class for LLM client failures."""


class MissingAPIKeyError(LLMError):
    """Raised when the selected provider has no API key configured."""

    def __init__(self, provider: str, env_var: str) -> None:
        self.provider = provider
        self.env_var = env_var
        super().__init__(
            f"{env_var} is not set for provider '{provider}'."
        )


class UnsupportedProviderError(LLMError):
    """Raised when ``LLM_PROVIDER`` is not a known provider."""


@dataclass
class LLMResponse:
    """Normalised response from any provider."""

    content: str
    provider: str
    model: str
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None
    raw: Any = field(default=None, repr=False)


_KEY_ENV_VARS = {
    "opencode": "OPENCODE_GO_API_KEY",
    "kimi": "KIMI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _require_api_key(settings: Settings, provider: str) -> str:
    api_key = settings.api_key_for(provider)
    if not api_key:
        env_var = _KEY_ENV_VARS.get(provider, "API_KEY")
        raise MissingAPIKeyError(provider, env_var)
    return api_key


def _build_openai_client(settings: Settings, provider: str) -> Any:
    """Create an ``openai.OpenAI`` client. Imported lazily on purpose."""
    api_key = _require_api_key(settings, provider)
    from openai import OpenAI

    base_url = settings.base_url_for(provider) or None
    return OpenAI(api_key=api_key, base_url=base_url)


def _usage_from_openai(usage: Any) -> Optional[Dict[str, int]]:
    if usage is None:
        return None
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }


def _call_openai_compatible(
    prompt: str, settings: Settings, provider: str, system_prompt: str
) -> LLMResponse:
    client = _build_openai_client(settings, provider)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    choice = response.choices[0]
    return LLMResponse(
        content=choice.message.content,
        provider=provider,
        model=getattr(response, "model", settings.llm_model),
        usage=_usage_from_openai(getattr(response, "usage", None)),
        finish_reason=getattr(choice, "finish_reason", None),
        raw=response,
    )


def _call_anthropic(
    prompt: str, settings: Settings, system_prompt: str
) -> LLMResponse:
    from anthropic import Anthropic

    api_key = _require_api_key(settings, "anthropic")
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=settings.llm_model,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    text_parts = [
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    ]
    usage = getattr(response, "usage", None)
    usage_dict = None
    if usage is not None:
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        usage_dict = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    return LLMResponse(
        content="".join(text_parts),
        provider="anthropic",
        model=getattr(response, "model", settings.llm_model),
        usage=usage_dict,
        finish_reason=getattr(response, "stop_reason", None),
        raw=response,
    )


def call_llm(
    prompt: str,
    settings: Optional[Settings] = None,
    system_prompt: Optional[str] = None,
) -> LLMResponse:
    """Dispatch ``prompt`` to the configured provider and return a response.

    Raises :class:`MissingAPIKeyError` when the provider key is missing and
    :class:`UnsupportedProviderError` for unknown providers.
    """
    settings = settings or load_settings()
    system_prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    provider = settings.llm_provider.lower()

    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return _call_openai_compatible(
            prompt, settings, provider, system_prompt
        )
    if provider == "anthropic":
        return _call_anthropic(prompt, settings, system_prompt)
    raise UnsupportedProviderError(
        f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}"
    )
