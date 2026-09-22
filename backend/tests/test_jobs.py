"""Tests for run_generation orchestration and progress reporting."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app.services import latex
from backend.app.services.jobs import GenerationRequest, run_generation
from backend.app.services.llm import LLMResponse, MissingAPIKeyError
from backend.app.services.settings import Settings

BASE_TEX = "\\documentclass{article}\nHello\n\\end{document}\n"


def make_settings(root: Path) -> Settings:
    return Settings.from_env(
        project_root=root,
        env={"LLM_PROVIDER": "opencode", "LATEX_TIMEOUT": "10"},
    )


def ok_response():
    return LLMResponse(
        content="```latex\n" + BASE_TEX + "\n```",
        provider="opencode",
        model="fake",
        usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    )


def completed(returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        args=["pdflatex"], returncode=returncode, stdout="", stderr=stderr
    )


class RunGenerationTests(unittest.TestCase):
    def _fake_run_factory(self, settings: Settings):
        def fake_run(command, **kwargs):
            tex = settings.running_template_dir / settings.working_template.name
            tex.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
            return completed()
        return fake_run

    def test_successful_generation_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            events = []
            request = GenerationRequest(
                job_description="We need AWS",
                company="Stripe",
                role="TPM",
                template=BASE_TEX,
                settings=settings,
                llm_caller=lambda prompt, cfg: ok_response(),
            )
            with mock.patch.object(
                latex.subprocess, "run", side_effect=self._fake_run_factory(settings)
            ):
                result = run_generation(request, progress_callback=events.append)

            self.assertTrue(result.success)
            self.assertIsNotNone(result.artifact)
            self.assertTrue(result.artifact.success)
            self.assertTrue(result.artifact.pdf_path.exists())
            self.assertTrue(result.artifact.filename.startswith("GopalKumar_Stripe_TPM_"))
            self.assertTrue(result.tex_path.exists())

            stages = [event.stage for event in events]
            self.assertEqual(
                stages,
                ["tailoring", "tailored", "tex_written", "compiling", "compiled", "done"],
            )

    def test_dry_run_writes_tex_without_compiling(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            events = []
            request = GenerationRequest(
                job_description="jd",
                company="Acme",
                role="PM",
                template=BASE_TEX,
                dry_run=True,
                settings=settings,
                llm_caller=lambda prompt, cfg: ok_response(),
            )
            with mock.patch.object(latex.subprocess, "run") as run_mock:
                result = run_generation(request, progress_callback=events.append)

            run_mock.assert_not_called()
            self.assertTrue(result.success)
            self.assertTrue(result.dry_run)
            self.assertIsNone(result.artifact)
            self.assertTrue(result.tex_path.exists())
            self.assertEqual(
                [event.stage for event in events],
                ["tailoring", "tailored", "tex_written", "dry_run", "done"],
            )

    def test_llm_error_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))

            def raising_caller(prompt, cfg):
                raise MissingAPIKeyError("opencode", "OPENCODE_GO_API_KEY")

            request = GenerationRequest(
                job_description="jd",
                company="Acme",
                role="PM",
                template=BASE_TEX,
                settings=settings,
                llm_caller=raising_caller,
            )
            result = run_generation(request)

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "llm")
            self.assertEqual(result.missing_env_var, "OPENCODE_GO_API_KEY")
            self.assertIsNone(result.artifact)

    def test_compilation_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            events = []
            request = GenerationRequest(
                job_description="jd",
                company="Acme",
                role="PM",
                template=BASE_TEX,
                settings=settings,
                llm_caller=lambda prompt, cfg: ok_response(),
            )
            with mock.patch.object(
                latex.subprocess, "run", return_value=completed(returncode=1)
            ):
                result = run_generation(request, progress_callback=events.append)

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "compilation")
            self.assertIsNotNone(result.artifact)
            self.assertFalse(result.artifact.success)
            self.assertIn("compilation_failed", [e.stage for e in events])

    def test_unusable_llm_output_fails_at_the_tailoring_stage(self):
        """Unparseable completions are a tailoring failure, not a compile one.

        Regression: this used to be written to disk and then rejected by the
        LaTeX validator, so the run reported ``compilation`` and pointed the
        operator at pdflatex while the real cause was the model's output.
        """
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            events = []
            request = GenerationRequest(
                job_description="jd",
                company="Acme",
                role="PM",
                template=BASE_TEX,
                settings=settings,
                llm_caller=lambda prompt, cfg: LLMResponse(
                    content="not latex", provider="opencode", model="fake"
                ),
            )
            with mock.patch.object(latex.subprocess, "run") as fake_run:
                result = run_generation(request, progress_callback=events.append)

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "tailoring")
            self.assertIsNone(result.artifact)
            self.assertIsNone(result.tex_path)
            # Rejected output must never reach the compiler or the disk, and
            # the stage sequence has to stop before compiling.
            fake_run.assert_not_called()
            stages = [event.stage for event in events]
            self.assertIn("tailoring_failed", stages)
            self.assertIn("done", stages)
            self.assertNotIn("tex_written", stages)
            self.assertNotIn("compiling", stages)

    def test_truncated_llm_output_names_the_token_limit(self):
        """A completion cut off by the token cap is reported as ``truncated``.

        This is the live failure mode that produced 8000-token completions
        labeled as compiler errors.
        """
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            request = GenerationRequest(
                job_description="jd",
                company="Acme",
                role="PM",
                template=BASE_TEX,
                settings=settings,
                llm_caller=lambda prompt, cfg: LLMResponse(
                    content="\\documentclass{article}\nHalf a document",
                    provider="opencode",
                    model="fake",
                    finish_reason="length",
                ),
            )
            result = run_generation(request)

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "truncated")
            self.assertIn("finish_reason='length'", result.error)
            self.assertIn(str(settings.llm_max_tokens), result.error)
            self.assertIsNone(result.artifact)

    def test_missing_template_fails_fast_without_calling_the_model(self):
        """A fresh clone has no resume template: fail fast, spend no tokens.

        The canonical resume is a private, gitignored asset, so a clean clone
        has no default template. This used to raise FileNotFoundError out of
        the worker thread, which the API reported as a generic
        ``unexpected_error`` instead of something the operator can act on.
        """
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            events = []
            calls = []

            def caller(prompt, cfg):
                calls.append(prompt)
                return ok_response()

            request = GenerationRequest(
                job_description="jd",
                company="Acme",
                role="PM",
                template=None,
                settings=settings,
                llm_caller=caller,
            )
            with mock.patch.object(latex.subprocess, "run") as fake_run:
                result = run_generation(request, progress_callback=events.append)

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "template")
            self.assertIn(str(settings.base_template), result.error)
            self.assertIn("Templates", result.error)
            self.assertIsNone(result.artifact)
            self.assertIsNone(result.tex_path)
            # No model spend and no compiler invocation for a missing input.
            self.assertEqual(calls, [])
            fake_run.assert_not_called()
            self.assertEqual([event.stage for event in events], ["done"])


if __name__ == "__main__":
    unittest.main()
