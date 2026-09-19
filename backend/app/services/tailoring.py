"""Resume tailoring service.

``tailor_resume(template, job_description, company, role)`` builds the
ATS-optimisation prompt, calls the configured LLM, extracts the LaTeX from the
response, and validates it. It performs no I/O of its own and performs no
logging of template/JD/prompt contents.

The optional ``settings`` / ``llm_caller`` keyword arguments exist purely for
dependency injection (tests, future FastAPI wiring) and do not change the
public call shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import prompts
from .llm import LLMResponse, call_llm
from .response_parser import extract_latex_from_response, validate_latex
from .settings import Settings, load_settings

LLMCaller = Callable[[str, Settings], LLMResponse]


@dataclass
class TailoringResult:
    """Result of an LLM tailoring pass."""

    latex_source: str
    raw_response: str
    prompt: str
    is_valid: bool
    validation_errors: List[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None

    @property
    def was_truncated(self) -> bool:
        """True when the provider stopped at the output-token limit.

        ``finish_reason='length'`` means the completion was cut off, so an
        unusable ``latex_source`` is a token-budget problem rather than a
        prompt or model-quality problem. Callers use this to report the right
        failure instead of blaming the LaTeX compile step.
        """
        return self.finish_reason == "length"

    @property
    def is_valid_latex(self) -> bool:
        """Backwards-compatible alias for :attr:`is_valid`."""
        return self.is_valid


def tailor_resume(
    template: str,
    job_description: str,
    company: str,
    role: str,
    settings: Optional[Settings] = None,
    llm_caller: Optional[LLMCaller] = None,
) -> TailoringResult:
    """Tailor ``template`` for ``role`` at ``company`` from ``job_description``.

    ``template`` is the full LaTeX source of the base resume. Returns the
    parsed LaTeX plus validation metadata. Raises :class:`LLMError` subclasses
    on missing keys or provider failures.
    """
    settings = settings or load_settings()
    caller: LLMCaller = llm_caller or call_llm

    prompt = prompts.build_tailoring_prompt(
        job_description, company, role, template
    )
    response = caller(prompt, settings)
    latex_source = extract_latex_from_response(response.content)
    issues = validate_latex(latex_source)

    return TailoringResult(
        latex_source=latex_source,
        raw_response=response.content,
        prompt=prompt,
        is_valid=not issues,
        validation_errors=issues,
        provider=response.provider,
        model=response.model,
        usage=response.usage,
        finish_reason=response.finish_reason,
    )
