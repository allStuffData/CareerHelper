"""Extraction and validation of LaTeX documents from LLM responses.

The LLM is instructed to wrap the full ``.tex`` file in a ```latex fenced code
block, but responses vary (plain fences, raw text, trailing prose). These
helpers keep the tolerant parsing behaviour of the original CLI while making it
reusable and testable.
"""

from __future__ import annotations

from typing import List

_LATEX_FENCE = "```latex"
_PLAIN_FENCE = "```"
_DOCUMENT_START = r"\documentclass"
_DOCUMENT_END = r"\end{document}"


def extract_latex_from_response(response: str) -> str:
    """Extract LaTeX content from an LLM response.

    Order of preference:
      1. A ```latex ... ``` fenced block.
      2. Any ``` ... ``` fenced block.
      3. The raw (stripped) response as a fallback.
    """
    if _LATEX_FENCE in response:
        start = response.find(_LATEX_FENCE) + len(_LATEX_FENCE)
        if start < len(response) and response[start] == "\n":
            start += 1
        end = response.find(_PLAIN_FENCE, start)
        if end != -1:
            return response[start:end].strip()

    if _PLAIN_FENCE in response:
        start = response.find(_PLAIN_FENCE) + len(_PLAIN_FENCE)
        if start < len(response) and response[start] == "\n":
            start += 1
        end = response.find(_PLAIN_FENCE, start)
        if end != -1:
            return response[start:end].strip()

    return response.strip()


def validate_latex(tex: str) -> List[str]:
    """Return a list of human-readable issues with ``tex`` (empty if valid).

    This is a lightweight structural check, not a full LaTeX parse: it catches
    the common failure mode where the LLM returns prose or a truncated file.
    """
    issues: List[str] = []
    stripped = tex.strip()

    if not stripped:
        issues.append("LaTeX output is empty.")
        return issues

    if not stripped.startswith(_DOCUMENT_START):
        issues.append(
            r"LaTeX output does not start with \documentclass."
        )

    if _DOCUMENT_END not in stripped:
        issues.append(r"LaTeX output does not contain \end{document}.")

    return issues


def is_latex_document(tex: str) -> bool:
    """Return ``True`` when ``tex`` passes :func:`validate_latex`."""
    return not validate_latex(tex)
