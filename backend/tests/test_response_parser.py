"""Tests for LLM response extraction and LaTeX validation."""

import unittest

from backend.app.services.response_parser import (
    extract_latex_from_response,
    is_latex_document,
    validate_latex,
)

VALID_TEX = (
    r"\documentclass[10pt,letterpaper]{article}" + "\n"
    r"\begin{document}" + "\n"
    r"Hello" + "\n"
    r"\end{document}"
)


class ExtractLatexTests(unittest.TestCase):
    def test_extracts_latex_fenced_block(self):
        response = (
            "Here is the tailored resume:\n\n"
            "```latex\n"
            f"{VALID_TEX}\n"
            "```\n"
            "Let me know if you'd like changes."
        )
        self.assertEqual(extract_latex_from_response(response), VALID_TEX)

    def test_extracts_plain_fenced_block(self):
        response = "```\n" + VALID_TEX + "\n```"
        self.assertEqual(extract_latex_from_response(response), VALID_TEX)

    def test_fence_without_trailing_newline(self):
        response = "```latex" + VALID_TEX + "```"
        self.assertEqual(extract_latex_from_response(response), VALID_TEX)

    def test_falls_back_to_raw_response(self):
        response = "  " + VALID_TEX + "  "
        self.assertEqual(extract_latex_from_response(response), VALID_TEX)

    def test_ignores_trailing_prose_after_fence(self):
        response = "```latex\n" + VALID_TEX + "\n```\nExtra commentary ``` here"
        self.assertEqual(extract_latex_from_response(response), VALID_TEX)

    def test_empty_response(self):
        self.assertEqual(extract_latex_from_response(""), "")


class ValidateLatexTests(unittest.TestCase):
    def test_valid_document_has_no_issues(self):
        self.assertEqual(validate_latex(VALID_TEX), [])
        self.assertTrue(is_latex_document(VALID_TEX))

    def test_empty_output(self):
        issues = validate_latex("   ")
        self.assertEqual(issues, ["LaTeX output is empty."])
        self.assertFalse(is_latex_document("   "))

    def test_missing_documentclass(self):
        issues = validate_latex(r"\begin{document}hi\end{document}")
        self.assertTrue(any("documentclass" in issue for issue in issues))
        self.assertFalse(is_latex_document(r"\begin{document}hi\end{document}"))

    def test_missing_end_document(self):
        tex = r"\documentclass{article}\begin{document}hi"
        issues = validate_latex(tex)
        self.assertTrue(any("end{document}" in issue for issue in issues))
        self.assertFalse(is_latex_document(tex))


if __name__ == "__main__":
    unittest.main()
