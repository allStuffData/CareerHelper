"""Tests for the tailoring service (prompt -> LLM -> parse -> validate)."""

import tempfile
import unittest
from pathlib import Path

from backend.app.services.llm import LLMResponse
from backend.app.services.settings import Settings
from backend.app.services.tailoring import tailor_resume

BASE_TEX = "\\documentclass{article}\nHello\n\\end{document}\n"


def make_settings(root: Path) -> Settings:
    return Settings.from_env(project_root=root, env={"LLM_PROVIDER": "opencode"})


class TailorResumeTests(unittest.TestCase):
    def test_parses_fenced_response_and_builds_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            captured = {}

            def fake_caller(prompt, cfg):
                captured["prompt"] = prompt
                captured["cfg"] = cfg
                return LLMResponse(
                    content="```latex\n" + BASE_TEX + "\n```",
                    provider="opencode",
                    model="fake",
                    usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                )

            result = tailor_resume(
                BASE_TEX, "We need AWS", "Acme", "PM",
                settings=settings, llm_caller=fake_caller,
            )

            self.assertEqual(result.latex_source, BASE_TEX.strip())
            self.assertTrue(result.is_valid)
            self.assertEqual(result.validation_errors, [])
            self.assertEqual(result.provider, "opencode")
            self.assertEqual(result.usage["total_tokens"], 3)
            self.assertIn("We need AWS", captured["prompt"])
            self.assertIn("Acme", captured["prompt"])
            self.assertIn("PM", captured["prompt"])
            self.assertIs(captured["cfg"], settings)

    def test_flags_invalid_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))

            def fake_caller(prompt, cfg):
                return LLMResponse(
                    content="Sorry, I cannot help with that.",
                    provider="opencode",
                    model="fake",
                )

            result = tailor_resume(
                BASE_TEX, "jd", "Acme", "PM",
                settings=settings, llm_caller=fake_caller,
            )

            self.assertFalse(result.is_valid)
            self.assertTrue(result.validation_errors)
            self.assertEqual(
                result.raw_response, "Sorry, I cannot help with that."
            )


if __name__ == "__main__":
    unittest.main()
