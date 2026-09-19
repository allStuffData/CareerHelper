"""LaTeX engine resolution tests.

``pdflatex`` is often installed outside ``PATH`` (for example under
``/Library/TeX/texbin``). These tests pin the shared resolver used by both the
compile path and the health check.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app.services import latex
from backend.app.services.settings import Settings


def _make_executable(directory: Path, name: str = "pdflatex") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)
    return path


class ResolveLatexEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.settings = Settings.from_env(project_root=self.tmp, env={})

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_absolute_executable_path_is_used_as_is(self) -> None:
        exe = _make_executable(self.tmp / "bin")
        self.assertEqual(latex.resolve_latex_engine(str(exe), self.settings), str(exe))

    def test_absolute_non_executable_returns_none(self) -> None:
        plain = self.tmp / "bin" / "pdflatex"
        plain.parent.mkdir(parents=True)
        plain.write_text("not executable", encoding="utf-8")
        plain.chmod(0o644)
        self.assertIsNone(latex.resolve_latex_engine(str(plain), self.settings))

    def test_name_resolved_via_path(self) -> None:
        with mock.patch.object(
            latex.shutil, "which", return_value="/fake/bin/pdflatex"
        ) as which:
            self.assertEqual(
                latex.resolve_latex_engine("pdflatex", self.settings),
                "/fake/bin/pdflatex",
            )
            which.assert_called_once_with("pdflatex")

    def test_falls_back_to_common_install_dir(self) -> None:
        exe = _make_executable(self.tmp / "texbin")
        with mock.patch.object(latex.shutil, "which", return_value=None):
            with mock.patch.object(latex, "_COMMON_ENGINE_DIRS", (str(exe.parent),)):
                self.assertEqual(
                    latex.resolve_latex_engine("pdflatex", self.settings), str(exe)
                )

    def test_falls_back_to_versioned_texlive_glob(self) -> None:
        exe = _make_executable(
            self.tmp / "texlive" / "2026" / "bin" / "universal-darwin"
        )
        glob_base = self.tmp / "texlive" / "*" / "bin" / "*"
        with mock.patch.object(latex.shutil, "which", return_value=None):
            with mock.patch.object(latex, "_COMMON_ENGINE_DIRS", ()):
                with mock.patch.object(latex, "_ENGINE_GLOBS", (str(glob_base),)):
                    self.assertEqual(
                        latex.resolve_latex_engine("pdflatex", self.settings), str(exe)
                    )

    def test_missing_engine_returns_none(self) -> None:
        with mock.patch.object(latex.shutil, "which", return_value=None):
            with mock.patch.object(latex, "_COMMON_ENGINE_DIRS", ()):
                with mock.patch.object(latex, "_ENGINE_GLOBS", ()):
                    self.assertIsNone(
                        latex.resolve_latex_engine("pdflatex", self.settings)
                    )

    def test_env_override_accepts_absolute_path(self) -> None:
        exe = _make_executable(self.tmp / "custom")
        settings = Settings.from_env(
            project_root=self.tmp, env={"LATEX_ENGINE": str(exe)}
        )
        self.assertEqual(settings.latex_engine, str(exe))
        self.assertEqual(latex.resolve_latex_engine(settings=settings), str(exe))

    def test_env_override_accepts_name(self) -> None:
        settings = Settings.from_env(
            project_root=self.tmp, env={"LATEX_ENGINE": "xelatex"}
        )
        with mock.patch.object(
            latex.shutil, "which", return_value="/fake/bin/xelatex"
        ) as which:
            self.assertEqual(
                latex.resolve_latex_engine(settings=settings), "/fake/bin/xelatex"
            )
            which.assert_called_once_with("xelatex")

    def test_resolver_uses_settings_engine_when_arg_omitted(self) -> None:
        exe = _make_executable(self.tmp / "custom")
        settings = Settings.from_env(
            project_root=self.tmp, env={"LATEX_ENGINE": str(exe)}
        )
        self.assertEqual(latex.resolve_latex_engine(settings=settings), str(exe))


if __name__ == "__main__":
    unittest.main()
