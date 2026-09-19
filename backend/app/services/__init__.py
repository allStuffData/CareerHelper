"""Reusable CareerHelper service layer (Phase 1).

Public entry points:

    settings         — Settings, load_settings
    prompts          — SYSTEM_PROMPT, build_tailoring_prompt, extract_section
    llm              — call_llm, LLMResponse, LLMError, MissingAPIKeyError
    response_parser  — extract_latex_from_response, validate_latex
    tailoring        — tailor_resume, TailoringResult
    latex            — compile_latex, ArtifactResult
    storage          — safe names, boundaries, working/artifact writes
    jobs             — run_generation, GenerationRequest/Result, ProgressEvent
"""

from .jobs import (
    GenerationRequest,
    GenerationResult,
    ProgressCallback,
    ProgressEvent,
    run_generation,
)
from .latex import ArtifactResult, compile_latex
from .llm import (
    LLMError,
    LLMResponse,
    MissingAPIKeyError,
    UnsupportedProviderError,
    call_llm,
)
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
from .storage import (
    StorageBoundaryError,
    build_artifact_filename,
    build_artifact_path,
    build_generation_id,
    ensure_within_directory,
    sanitize_filename_component,
    store_artifact,
    write_working_template,
)
from .tailoring import TailoringResult, tailor_resume

__all__ = [
    # settings
    "Settings",
    "load_settings",
    # prompts
    "SYSTEM_PROMPT",
    "build_tailoring_prompt",
    "extract_section",
    # llm
    "call_llm",
    "LLMResponse",
    "LLMError",
    "MissingAPIKeyError",
    "UnsupportedProviderError",
    # response parsing
    "extract_latex_from_response",
    "validate_latex",
    "is_latex_document",
    # tailoring
    "tailor_resume",
    "TailoringResult",
    # latex
    "compile_latex",
    "ArtifactResult",
    # storage
    "sanitize_filename_component",
    "build_generation_id",
    "build_artifact_filename",
    "build_artifact_path",
    "ensure_within_directory",
    "write_working_template",
    "store_artifact",
    "StorageBoundaryError",
    # jobs
    "run_generation",
    "GenerationRequest",
    "GenerationResult",
    "ProgressEvent",
    "ProgressCallback",
]
