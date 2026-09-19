"""End-to-end tailoring orchestration shared by the CLI adapter and backend.

``tailor`` performs the LLM half of the pipeline (read template → build prompt
→ call LLM → parse → validate). Compilation is a separate step so callers can
support dry runs and compile-only flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import prompts
from .latex import compile_latex
from .llm_client import LLMResponse, call_llm
from .response_parser import extract_latex_from_response, validate_latex
from .settings import Settings, load_settings

LLMCaller = Callable[[str, Settings], LLMResponse]


@dataclass
class TailoringResult:
    """Outcome of the LLM tailoring step."""

    prompt: str
    raw_response: str
    tex_content: str
    is_valid_latex: bool
    validation_issues: List[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    usage: Optional[Dict[str, int]] = None


def tailor(
    job_description: str,
    company: str,
    role: str,
    settings: Optional[Settings] = None,
    llm_caller: Optional[LLMCaller] = None,
) -> TailoringResult:
    """Run the LLM tailoring step and return the parsed LaTeX.

    ``llm_caller`` is injectable for testing; it defaults to
    :func:`backend.app.services.llm_client.call_llm` and receives the prompt
    plus the resolved settings.
    """
    settings = settings or load_settings()
    caller: LLMCaller = llm_caller or call_llm

    template_tex = settings.base_template.read_text(encoding="utf-8")
    prompt = prompts.build_tailoring_prompt(
        job_description, company, role, template_tex
    )
    response = caller(prompt, settings)
    tex_content = extract_latex_from_response(response.content)
    issues = validate_latex(tex_content)

    return TailoringResult(
        prompt=prompt,
        raw_response=response.content,
        tex_content=tex_content,
        is_valid_latex=not issues,
        validation_issues=issues,
        provider=response.provider,
        model=response.model,
        usage=response.usage,
    )


def compile_tailored(
    tex_path,
    company: str,
    role: str,
    settings: Optional[Settings] = None,
):
    """Compile a tailored ``.tex`` file to a PDF in the output directory."""
    settings = settings or load_settings()
    return compile_latex(tex_path, company, role, settings=settings)
