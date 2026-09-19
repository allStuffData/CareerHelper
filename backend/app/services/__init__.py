"""Reusable CareerHelper service layer (Phase 1).

Public entry points, grouped by concern:

    settings         — Settings, load_settings
    prompts          — SYSTEM_PROMPT, build_tailoring_prompt, extract_section
    llm_client       — call_llm, LLMResponse, LLMError, MissingAPIKeyError
    response_parser  — extract_latex_from_response, validate_latex
    latex            — compile_latex, store_pdf, build_output_path,
                       sanitize_filename_component, LatexCompilationError
    pipeline         — tailor, compile_tailored, TailoringResult
"""

from .latex import (
    LatexCompilationError,
    StorageBoundaryError,
    build_output_filename,
    build_output_path,
    compile_latex,
    ensure_within_directory,
    sanitize_filename_component,
    store_pdf,
    write_working_template,
)
from .llm_client import (
    LLMError,
    LLMResponse,
    MissingAPIKeyError,
    UnsupportedProviderError,
    call_llm,
)
from .pipeline import TailoringResult, compile_tailored, tailor
from .prompts import (
    SYSTEM_PROMPT,
    build_tailoring_prompt,
    extract_section,
)
from .response_parser import (
    extract_latex_from_response,
    is_latex_document,
    validate_latex,
)
from .settings import Settings, load_settings

__all__ = [
    "Settings",
    "load_settings",
    "SYSTEM_PROMPT",
    "build_tailoring_prompt",
    "extract_section",
    "call_llm",
    "LLMResponse",
    "LLMError",
    "MissingAPIKeyError",
    "UnsupportedProviderError",
    "extract_latex_from_response",
    "validate_latex",
    "is_latex_document",
    "compile_latex",
    "compile_tailored",
    "tailor",
    "TailoringResult",
    "store_pdf",
    "build_output_path",
    "build_output_filename",
    "sanitize_filename_component",
    "ensure_within_directory",
    "write_working_template",
    "LatexCompilationError",
    "StorageBoundaryError",
]
