"""Settings path mapping to the reorganized resources/ layout.

Phase 1 used to read/write ``LatexTemplate/``, ``RunningTemplate/`` and
``Output/`` at the repository root. The repository reorganization moved those
to ``resources/`` (gitignored, .gitkeep-tracked), so these tests pin the new
mapping without changing the public ``Settings``/``load_settings`` shape.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.app.services.settings import Settings, load_settings


class SettingsPathTests(unittest.TestCase):
    def test_from_env_maps_to_resources_layout(self) -> None:
        root = Path("/tmp/careerhelper-repo")
        settings = Settings.from_env(project_root=root, env={})

        self.assertEqual(
            settings.latex_template_dir,
            root / "resources" / "templates" / "latex",
        )
        self.assertEqual(
            settings.running_template_dir,
            root / "resources" / "workspace",
        )
        self.assertEqual(settings.output_dir, root / "resources" / "output")
        self.assertEqual(
            settings.base_template,
            root / "resources" / "templates" / "latex" / "GopalKumar_Resume.tex",
        )
        self.assertEqual(
            settings.working_template,
            root / "resources" / "workspace" / "GopalKumar_Resume.tex",
        )

    def test_from_env_still_reads_provider_and_latex_env(self) -> None:
        settings = Settings.from_env(
            project_root=Path("/tmp/careerhelper-repo"),
            env={
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "gpt-4o",
                "OPENAI_API_KEY": "test",
                "LATEX_ENGINE": "xelatex",
                "LATEX_RUNS": "3",
                "LATEX_TIMEOUT": "15",
            },
        )

        self.assertEqual(settings.llm_provider, "openai")
        self.assertEqual(settings.llm_model, "gpt-4o")
        self.assertEqual(settings.api_key_for(), "test")
        self.assertEqual(settings.latex_engine, "xelatex")
        self.assertEqual(settings.latex_runs, 3)
        self.assertEqual(settings.latex_timeout, 15)

    def test_load_settings_accepts_explicit_env_and_root(self) -> None:
        settings = load_settings(
            project_root=Path("/tmp/careerhelper-repo"), env={"LATEX_RUNS": "1"}
        )
        self.assertEqual(settings.latex_runs, 1)
        self.assertTrue(str(settings.output_dir).endswith("resources/output"))


if __name__ == "__main__":
    unittest.main()
