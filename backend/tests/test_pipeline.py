"""Tests for the tailoring orchestration (prompt -> LLM -> parse -> validate)."""

import tempfile
import unittest
from pathlib import Path

from backend.app.services.latex import write_working_template
from backend.app.services.llm_client import LLMResponse
from backend.app.services.pipeline import tailor
from backend.app.services.settings import Settings

BASE_TEX = "\\documentclass{article}\n% === HEADER\nHello\n\\end{document}\n"


def make_settings(root: Path) -> Settings:
    return Settings.from_env(project_root=root, env={"LLM_PROVIDER": "opencode"})


class TailorTests(unittest.TestCase):
    def _prepare_root(self, tmp: str) -> Settings:
        settings = make_settings(Path(tmp))
        settings.base_template.parent.mkdir(parents=True, exist_ok=True)
        settings.base_template.write_text(BASE_TEX, encoding="utf-8")
        return settings

    def test_tailor_parses_fenced_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._prepare_root(tmp)
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

            result = tailor("We need AWS", "Acme", "PM", settings=settings, llm_caller=fake_caller)

            self.assertEqual(result.tex_content, BASE_TEX.strip())
            self.assertTrue(result.is_valid_latex)
            self.assertEqual(result.validation_issues, [])
            self.assertEqual(result.provider, "opencode")
            self.assertEqual(result.usage["total_tokens"], 3)
            self.assertIn("We need AWS", captured["prompt"])
            self.assertIn("Acme", captured["prompt"])
            self.assertIs(captured["cfg"], settings)

    def test_tailor_flags_invalid_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._prepare_root(tmp)

            def fake_caller(prompt, cfg):
                return LLMResponse(
                    content="Sorry, I cannot help with that.",
                    provider="opencode",
                    model="fake",
                )

            result = tailor("jd", "Acme", "PM", settings=settings, llm_caller=fake_caller)

            self.assertFalse(result.is_valid_latex)
            self.assertTrue(result.validation_issues)
            self.assertEqual(result.raw_response, "Sorry, I cannot help with that.")

    def test_write_working_template_creates_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            path = write_working_template(BASE_TEX, settings.working_template)
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), BASE_TEX)


if __name__ == "__main__":
    unittest.main()
