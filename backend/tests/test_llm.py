"""Tests for provider dispatch and error handling in the LLM client."""

import unittest
from types import SimpleNamespace
from unittest import mock

from backend.app.services import llm
from backend.app.services.settings import Settings


def make_settings(**env) -> Settings:
    return Settings.from_env(env=env)


class FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def fake_openai_client(content="tailored", usage=(3, 5, 8)):
    choice = SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason="stop"
    )
    usage_obj = (
        SimpleNamespace(
            prompt_tokens=usage[0],
            completion_tokens=usage[1],
            total_tokens=usage[2],
        )
        if usage
        else None
    )
    response = SimpleNamespace(
        choices=[choice], usage=usage_obj, model="fake-model"
    )
    completions = FakeCompletions(response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


class MissingKeyTests(unittest.TestCase):
    def test_openai_compatible_missing_key(self):
        settings = make_settings(LLM_PROVIDER="openai")
        with self.assertRaises(llm.MissingAPIKeyError) as ctx:
            llm.call_llm("hi", settings)
        self.assertEqual(ctx.exception.env_var, "OPENAI_API_KEY")

    def test_kimi_missing_key(self):
        settings = make_settings(LLM_PROVIDER="kimi")
        with self.assertRaises(llm.MissingAPIKeyError) as ctx:
            llm.call_llm("hi", settings)
        self.assertEqual(ctx.exception.env_var, "KIMI_API_KEY")

    def test_opencode_missing_key(self):
        settings = make_settings(LLM_PROVIDER="opencode")
        with self.assertRaises(llm.MissingAPIKeyError) as ctx:
            llm.call_llm("hi", settings)
        self.assertEqual(ctx.exception.env_var, "OPENCODE_GO_API_KEY")


class UnsupportedProviderTests(unittest.TestCase):
    def test_unknown_provider_raises(self):
        settings = make_settings(LLM_PROVIDER="mystery")
        with self.assertRaises(llm.UnsupportedProviderError):
            llm.call_llm("hi", settings)


class OpenAICompatibleTests(unittest.TestCase):
    def test_kimi_call_returns_normalised_response(self):
        settings = make_settings(
            LLM_PROVIDER="kimi",
            KIMI_API_KEY="secret",
            LLM_MODEL="kimi-k2-0711-preview",
        )
        client, completions = fake_openai_client(content="tailored tex")
        with mock.patch.object(
            llm, "_build_openai_client", return_value=client
        ) as builder:
            response = llm.call_llm("prompt text", settings)

        self.assertEqual(response.content, "tailored tex")
        self.assertEqual(response.provider, "kimi")
        self.assertEqual(
            response.usage,
            {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
        )
        builder.assert_called_once_with(settings, "kimi")

        call = completions.calls[0]
        self.assertEqual(call["model"], "kimi-k2-0711-preview")
        self.assertEqual(call["temperature"], settings.llm_temperature)
        self.assertEqual(call["messages"][0]["role"], "system")
        self.assertEqual(call["messages"][1]["content"], "prompt text")

    def test_custom_system_prompt_is_used(self):
        settings = make_settings(
            LLM_PROVIDER="opencode", OPENCODE_GO_API_KEY="secret"
        )
        client, completions = fake_openai_client()
        with mock.patch.object(
            llm, "_build_openai_client", return_value=client
        ):
            llm.call_llm("hi", settings, system_prompt="CUSTOM SYSTEM")

        self.assertEqual(
            completions.calls[0]["messages"][0]["content"], "CUSTOM SYSTEM"
        )


if __name__ == "__main__":
    unittest.main()
