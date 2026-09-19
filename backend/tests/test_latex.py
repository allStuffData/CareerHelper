"""Tests for filename sanitisation, storage boundaries, and compilation errors."""

import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from backend.app.services import latex
from backend.app.services.settings import Settings

FIXED_DATE = datetime(2026, 8, 9)


def make_settings(root: Path, engine: str = "pdflatex", runs: int = 2) -> Settings:
    return Settings.from_env(
        project_root=root,
        env={"LATEX_ENGINE": engine, "LATEX_RUNS": str(runs)},
    )


class SanitizeFilenameTests(unittest.TestCase):
    def test_removes_illegal_characters(self):
        self.assertEqual(
            latex.sanitize_filename_component("Acme/Corp: Inc!"),
            "AcmeCorp Inc",
        )

    def test_keeps_spaces_underscores_and_hyphens(self):
        self.assertEqual(
            latex.sanitize_filename_component("Senior_Dev-Ops Lead"),
            "Senior_Dev-Ops Lead",
        )

    def test_truncates_to_max_length(self):
        value = "a" * 50
        self.assertEqual(len(latex.sanitize_filename_component(value)), 30)
        self.assertEqual(
            latex.sanitize_filename_component(value, max_length=5), "aaaaa"
        )

    def test_truncation_then_strip(self):
        self.assertEqual(
            latex.sanitize_filename_component("abcde   ghij", max_length=8),
            "abcde",
        )

    def test_empty_and_none_like_values(self):
        self.assertEqual(latex.sanitize_filename_component(""), "")
        self.assertEqual(latex.sanitize_filename_component(None), "")


class OutputPathTests(unittest.TestCase):
    def test_build_output_filename(self):
        filename = latex.build_output_filename(
            "Stripe", "Technical Program Manager", when=FIXED_DATE
        )
        self.assertEqual(
            filename,
            "GopalKumar_Stripe_Technical Program Manager_20260809.pdf",
        )

    def test_build_output_filename_sanitizes_components(self):
        filename = latex.build_output_filename(
            "Acme/Inc", "Sr. PM!!", when=FIXED_DATE
        )
        self.assertEqual(filename, "GopalKumar_AcmeInc_Sr PM_20260809.pdf")

    def test_build_output_path_stays_inside_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "Output"
            path = latex.build_output_path(
                output_dir, "Stripe", "TPM", when=FIXED_DATE
            )
            self.assertEqual(path.parent, output_dir.resolve())
            self.assertEqual(
                path.name, "GopalKumar_Stripe_TPM_20260809.pdf"
            )

    def test_ensure_within_directory_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "Output"
            output_dir.mkdir()
            with self.assertRaises(latex.StorageBoundaryError):
                latex.ensure_within_directory(
                    output_dir / ".." / "escape.pdf", output_dir
                )

    def test_ensure_within_directory_accepts_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "Output"
            child = output_dir / "nested" / "file.pdf"
            resolved = latex.ensure_within_directory(child, output_dir)
            self.assertEqual(resolved, child.resolve())


class CompilationTests(unittest.TestCase):
    def _write_tex(self, settings: Settings, content: str = "\\documentclass{article}") -> Path:
        tex_path = settings.working_template
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text(content, encoding="utf-8")
        return tex_path

    def test_compilation_failure_raises_with_log_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            tex_path = self._write_tex(settings)
            tex_path.with_suffix(".log").write_text(
                "some build output\n! Undefined control sequence.\n",
                encoding="utf-8",
            )
            failure = subprocess.CompletedProcess(
                args=["pdflatex"], returncode=1, stdout="", stderr="engine boom"
            )
            with mock.patch.object(latex.subprocess, "run", return_value=failure):
                with self.assertRaises(latex.LatexCompilationError) as ctx:
                    latex.compile_latex(tex_path, "Acme", "PM", settings=settings)

            self.assertEqual(ctx.exception.returncode, 1)
            self.assertIn("Undefined control sequence", ctx.exception.log_tail)

    def test_compilation_failure_uses_stderr_when_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            tex_path = self._write_tex(settings)
            failure = subprocess.CompletedProcess(
                args=["pdflatex"], returncode=2, stdout="", stderr="missing engine"
            )
            with mock.patch.object(latex.subprocess, "run", return_value=failure):
                with self.assertRaises(latex.LatexCompilationError) as ctx:
                    latex.compile_latex(tex_path, "Acme", "PM", settings=settings)

            self.assertIn("missing engine", ctx.exception.log_tail)

    def test_missing_pdf_after_success_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            tex_path = self._write_tex(settings)
            success = subprocess.CompletedProcess(
                args=["pdflatex"], returncode=0, stdout="", stderr=""
            )
            with mock.patch.object(latex.subprocess, "run", return_value=success):
                with self.assertRaises(latex.LatexCompilationError) as ctx:
                    latex.compile_latex(tex_path, "Acme", "PM", settings=settings)

            self.assertIn("PDF not found", str(ctx.exception))

    def test_missing_engine_raises_compilation_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), engine="no-such-latex-engine-xyz")
            tex_path = self._write_tex(settings)
            with self.assertRaises(latex.LatexCompilationError) as ctx:
                latex.compile_latex(tex_path, "Acme", "PM", settings=settings)

            self.assertIn("Could not run LaTeX engine", str(ctx.exception))

    def test_successful_compilation_stores_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            tex_path = self._write_tex(settings)
            tex_path.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
            success = subprocess.CompletedProcess(
                args=["pdflatex"], returncode=0, stdout="", stderr=""
            )
            with mock.patch.object(latex.subprocess, "run", return_value=success):
                result = latex.compile_latex(
                    tex_path, "Stripe", "TPM", settings=settings, when=FIXED_DATE
                )

            self.assertTrue(result.exists())
            self.assertEqual(result.parent, settings.output_dir.resolve())
            self.assertEqual(
                result.name, "GopalKumar_Stripe_TPM_20260809.pdf"
            )

    def test_runs_engine_configured_number_of_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), runs=3)
            tex_path = self._write_tex(settings)
            tex_path.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
            success = subprocess.CompletedProcess(
                args=["pdflatex"], returncode=0, stdout="", stderr=""
            )
            with mock.patch.object(
                latex.subprocess, "run", return_value=success
            ) as run_mock:
                latex.compile_latex(tex_path, "A", "B", settings=settings)

            self.assertEqual(run_mock.call_count, 3)


if __name__ == "__main__":
    unittest.main()
