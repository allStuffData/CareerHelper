"""Tests for prompt construction and section extraction."""

import unittest

from backend.app.services import prompts


class SystemPromptTests(unittest.TestCase):
    def test_contains_all_phases_and_output_format(self):
        for phase in ("PHASE 1", "PHASE 2", "PHASE 3", "PHASE 4", "PHASE 5"):
            self.assertIn(phase, prompts.SYSTEM_PROMPT)
        self.assertIn("```latex", prompts.SYSTEM_PROMPT)
        self.assertIn(r"\documentclass", prompts.SYSTEM_PROMPT)


class BuildTailoringPromptTests(unittest.TestCase):
    def test_injects_role_jd_and_template(self):
        result = prompts.build_tailoring_prompt(
            "We need a PM with AWS experience.",
            "Stripe",
            "Technical Program Manager",
            r"\documentclass{article}% TEMPLATE-BODY",
        )
        self.assertIn("Stripe", result)
        self.assertIn("Technical Program Manager", result)
        self.assertIn("We need a PM with AWS experience.", result)
        self.assertIn("TEMPLATE-BODY", result)
        self.assertIn(
            "Output the COMPLETE .tex file in a ```latex block", result
        )


class ExtractSectionTests(unittest.TestCase):
    TEX = (
        "% === HEADER\nheader content\n"
        "% === EDUCATION\neducation content\n"
        "% === TECHNICAL STACK\ntech content\n"
        "% === WORK EXPERIENCE\nwork content\n"
        "% === KEY PROJECTS\nproject content\n"
        "% === LEADERSHIP\nleadership content\n"
        "% === AWARDS\nawards content\n"
        "\\end{document}\n"
    )

    def test_extracts_named_section(self):
        section = prompts.extract_section(self.TEX, "education")
        self.assertIn("education content", section)
        self.assertNotIn("tech content", section)

    def test_awards_section_runs_to_end_document(self):
        section = prompts.extract_section(self.TEX, "awards")
        self.assertIn("awards content", section)

    def test_missing_start_anchor_returns_empty(self):
        self.assertEqual(prompts.extract_section("no anchors", "header"), "")


if __name__ == "__main__":
    unittest.main()
