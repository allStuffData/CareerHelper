"""Tests for the LaTeX compilation boundary and its error reporting."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app.services import latex
from backend.app.services.settings import Settings

VALID_TEX = (
    "\\documentclass{article}\n"
    "\\begin{document}\nHello\n\\end{document}\n"
)


def make_settings(root: Path, engine: str = "pdflatex", runs: int = 2,
                  timeout: int = 30) -> Settings:
    return Settings.from_env(
        project_root=root,
        env={
            "LATEX_ENGINE": engine,
            "LATEX_RUNS": str(runs),
            "LATEX_TIMEOUT": str(timeout),
        },
    )


def completed(returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        args=["pdflatex"], returncode=returncode, stdout="", stderr=stderr
    )


class ValidationTests(unittest.TestCase):
    def test_invalid_source_is_rejected_without_running_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            with mock.patch.object(latex.subprocess, "run") as run_mock:
                result = latex.compile_latex(
                    "just prose, not latex", "gen-1", settings=settings
                )

            self.assertFalse(result.success)
            self.assertIn("failed validation", result.error)
            run_mock.assert_not_called()


class CompilationErrorTests(unittest.TestCase):
    def test_missing_engine_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), engine="no-such-engine-xyz")
            result = latex.compile_latex(VALID_TEX, "gen-1", settings=settings)

            self.assertFalse(result.success)
            self.assertIn("Could not run LaTeX engine", result.error)

    def test_nonzero_exit_uses_log_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            failure = completed(returncode=1, stderr="engine boom")
            with mock.patch.object(latex.subprocess, "run", return_value=failure):
                # Pre-seed a log file that the source write would otherwise create.
                log_path = settings.working_template.with_suffix(".log")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    "! Undefined control sequence.\n", encoding="utf-8"
                )
                result = latex.compile_latex(VALID_TEX, "gen-1", settings=settings)

            self.assertFalse(result.success)
            self.assertEqual(result.error, "LaTeX compilation failed (exit 1).")
            self.assertIn("Undefined control sequence", result.log_tail)

    def test_nonzero_exit_falls_back_to_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            failure = completed(returncode=2, stderr="missing package manager")
            with mock.patch.object(latex.subprocess, "run", return_value=failure):
                result = latex.compile_latex(VALID_TEX, "gen-1", settings=settings)

            self.assertFalse(result.success)
            self.assertIn("missing package manager", result.log_tail)

    def test_timeout_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), timeout=5)
            expired = subprocess.TimeoutExpired(cmd="pdflatex", timeout=5)
            with mock.patch.object(latex.subprocess, "run", side_effect=expired):
                result = latex.compile_latex(VALID_TEX, "gen-1", settings=settings)

            self.assertFalse(result.success)
            self.assertIn("timed out", result.error)

    def test_missing_pdf_after_success_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            with mock.patch.object(latex.subprocess, "run", return_value=completed()):
                result = latex.compile_latex(VALID_TEX, "gen-1", settings=settings)

            self.assertFalse(result.success)
            self.assertIn("PDF not found", result.error)


class CompilationSecurityTests(unittest.TestCase):
    def test_engine_runs_without_shell_escape_and_with_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), timeout=17)
            with mock.patch.object(
                latex.subprocess, "run", return_value=completed()
            ) as run_mock:
                latex.compile_latex(VALID_TEX, "gen-1", settings=settings)

            args, kwargs = run_mock.call_args
            command = args[0]
            self.assertIn("-no-shell-escape", command)
            self.assertIn("-interaction=nonstopmode", command)
            self.assertEqual(kwargs["timeout"], 17)

    def test_runs_engine_configured_number_of_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), runs=3)
            with mock.patch.object(
                latex.subprocess, "run", return_value=completed()
            ) as run_mock:
                latex.compile_latex(VALID_TEX, "gen-1", settings=settings)

            self.assertEqual(run_mock.call_count, 3)


class CompilationSuccessTests(unittest.TestCase):
    def test_successful_compile_stores_safe_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))

            def fake_run(command, **kwargs):
                # Simulate the engine producing a PDF next to the .tex file.
                tex = settings.running_template_dir / settings.working_template.name
                tex.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
                return completed()

            with mock.patch.object(latex.subprocess, "run", side_effect=fake_run):
                result = latex.compile_latex(
                    VALID_TEX, "GopalKumar_Stripe_TPM_20260809",
                    settings=settings,
                )

            self.assertTrue(result.success)
            self.assertIsNotNone(result.pdf_path)
            self.assertTrue(result.pdf_path.exists())
            self.assertEqual(
                result.filename, "GopalKumar_Stripe_TPM_20260809.pdf"
            )
            self.assertEqual(result.pdf_path.parent, settings.output_dir.resolve())
            self.assertTrue(result.tex_path.exists())


if __name__ == "__main__":
    unittest.main()
