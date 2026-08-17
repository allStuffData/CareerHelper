"""
Configuration for the resume tailoring pipeline.
Loads API keys from the project .env file. Override via config_local.py or env vars.

Default LLM: DeepSeek V4 Pro via OpenCode Zen Go (OpenAI-compatible endpoint).
"""

import os
from pathlib import Path

# ── .env loading ───────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_ENV_PATH)
except ImportError:
    pass  # python-dotenv is optional; env vars work fine too

# ── Project Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LATEX_TEMPLATE_DIR = PROJECT_ROOT / "LatexTemplate"
RUNNING_TEMPLATE_DIR = PROJECT_ROOT / "RunningTemplate"
OUTPUT_DIR = PROJECT_ROOT / "Output"
SCRIPTS_DIR = PROJECT_ROOT / "Scripts"

# The canonical base template (never manually edited for a specific job)
BASE_TEMPLATE = LATEX_TEMPLATE_DIR / "GopalKumar_Resume.tex"

# The working copy that gets tailored per job
WORKING_TEMPLATE = RUNNING_TEMPLATE_DIR / "GopalKumar_Resume.tex"

# ── LLM Configuration ──────────────────────────────────────────────────────
# Provider: "opencode" (OpenCode Zen Go) | "openai" | "anthropic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "opencode")

# Model name (provider-specific)
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-pro")

# ── OpenCode Zen Go (default) ─────────────────────────────────────────────
# Endpoint: https://opencode.ai/zen/go/v1
# Pricing:  $0.435/M input | $0.87/M output
OPENCODE_GO_API_KEY = os.getenv("OPENCODE_GO_API_KEY", "")
OPENCODE_GO_BASE_URL = os.getenv(
    "OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1"
)

# ── OpenAI (fallback / alternative) ────────────────────────────────────────
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

# ── Anthropic (fallback / alternative) ─────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── LLM parameters ─────────────────────────────────────────────────────────
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8000"))

# ── Section Tags (used as anchors for targeted editing) ───────────────────
SECTION_MARKERS = {
    "header":       "% === HEADER",
    "education":    "% === EDUCATION",
    "tech_stack":   "% === TECHNICAL STACK",
    "experience":   "% === WORK EXPERIENCE",
    "projects":     "% === KEY PROJECTS",
    "leadership":   "% === LEADERSHIP",
    "awards":       "% === AWARDS",
}

# ── Compilation ────────────────────────────────────────────────────────────
LATEX_ENGINE = os.getenv("LATEX_ENGINE", "pdflatex")  # pdflatex|xelatex|lualatex
LATEX_RUNS = int(os.getenv("LATEX_RUNS", "2"))

# ── Local overrides (gitignored) ──────────────────────────────────────────
try:
    from config_local import *  # noqa: F401, F403
except ImportError:
    pass
