#!/usr/bin/env python3
"""
Resume Tailoring Pipeline — ATS-Optimized (thin CLI adapter)
=============================================================
Takes a job description, uses the configured LLM to rewrite the LaTeX resume
for maximum ATS compatibility, then compiles to PDF.

All pipeline logic lives in ``backend/app/services``; this file only handles
argument parsing, interactive prompts, console output, and exit codes.

Usage:
    python3 Scripts/tailor_resume.py --job-file jd.txt --company "Stripe" --role "TPM"
    python3 Scripts/tailor_resume.py --job "We need a PM who..." --company "Acme" --role "PM"
    python3 Scripts/tailor_resume.py --job-file jd.txt --company "Acme" --role "PM" --dry-run
    python3 Scripts/tailor_resume.py --compile-only --company "Acme" --role "PM"
"""

import argparse
import sys
from pathlib import Path

# Add the repository root to sys.path so the ``backend`` package is importable
# when this script is run directly (``python3 Scripts/tailor_resume.py``).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.latex import (
    LatexCompilationError,
    compile_latex,
    write_working_template,
)
from backend.app.services.llm_client import LLMError, MissingAPIKeyError
from backend.app.services.pipeline import tailor
from backend.app.services.settings import load_settings


# ═══════════════════════════════════════════════════════════════════════════
# INTERACTIVE INPUT
# ═══════════════════════════════════════════════════════════════════════════

def read_multiline(prompt: str) -> str:
    """Read multi-line input from the user until EOF (Ctrl+D on macOS/Linux).

    Example:
        ┌─────────────────────────────────────────┐
        │ Paste job description (Ctrl+D to finish):│
        │ We are looking for a...                  │
        │ ...more lines...                         │
        │ ^D                                       │
        └─────────────────────────────────────────┘
    """
    print(prompt)
    print("─" * 60)
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    print("─" * 60)
    return "\n".join(lines).strip()


def _print_compilation_error(error: LatexCompilationError) -> None:
    if error.log_tail:
        print(f"\n⚠️  LaTeX compilation failed. Log tail:\n{error.log_tail}")
    else:
        print(f"\n⚠️  LaTeX compilation failed:\n{error}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Tailor your LaTeX resume with the configured LLM for ATS optimization.\n\n"
            "Default (interactive): just run with no arguments — you'll be prompted\n"
            "for company, role, and the job description to paste.\n\n"
            "Scripting: pass --company, --role, and --job/--job-file to skip prompts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--job", type=str,
        help="Job description as a string (skips interactive paste)."
    )
    parser.add_argument(
        "--job-file", type=str,
        help="Path to a text file containing the job description."
    )
    parser.add_argument(
        "--company", type=str, default=None,
        help="Target company name (prompts interactively if omitted)."
    )
    parser.add_argument(
        "--role", type=str, default=None,
        help="Target role (prompts interactively if omitted)."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate tailored .tex but don't compile to PDF."
    )
    parser.add_argument(
        "--compile-only", action="store_true",
        help="Skip LLM tailoring; just compile the current RunningTemplate."
    )

    args = parser.parse_args()
    settings = load_settings()

    # ── Compile-only shortcut ────────────────────────────────────────────
    if args.compile_only:
        print("🔨 Compiling current RunningTemplate...")
        if settings.working_template.exists():
            try:
                compile_latex(
                    settings.working_template,
                    args.company or "Resume",
                    args.role or "Default",
                    settings=settings,
                )
            except LatexCompilationError as error:
                _print_compilation_error(error)
        else:
            print("❌ No working template found to compile.")
            sys.exit(1)
        return

    # ── Interactive prompts (only when flags not provided) ───────────────
    company = args.company
    role = args.role

    if not company or not role:
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║   📋  Resume Tailoring — ATS Optimizer           ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

    if not company:
        company = input("Company name: ").strip()
        if not company:
            print("❌ Company name is required.")
            sys.exit(1)

    if not role:
        role = input("Role / position: ").strip()
        if not role:
            print("❌ Role is required.")
            sys.exit(1)

    # ── Resolve job description ─────────────────────────────────────────
    if args.job:
        job_description = args.job
    elif args.job_file:
        jd_path = Path(args.job_file)
        if not jd_path.exists():
            print(f"❌ Job description file not found: {args.job_file}")
            sys.exit(1)
        job_description = jd_path.read_text()
    else:
        # Interactive: paste the JD
        print()
        job_description = read_multiline(
            "📄  Paste the job description below (Ctrl+D when done):"
        )
        if not job_description:
            print("❌ No job description provided.")
            sys.exit(1)
        print(f"   ({len(job_description)} characters received)")

    # ── Step 1: LLM tailoring ───────────────────────────────────────────
    print(f"\n📋 Tailoring resume for {role} at {company}...")
    print(f"   Provider: {settings.llm_provider}  |  Model: {settings.llm_model}")

    try:
        result = tailor(job_description, company, role, settings=settings)
    except MissingAPIKeyError as error:
        print(f"❌ {error}")
        print(f"   Make sure your .env file has: {error.env_var}=...")
        sys.exit(1)
    except LLMError as error:
        print(f"❌ {error}")
        sys.exit(1)

    if result.usage:
        print(
            f"   Tokens: prompt={result.usage['prompt_tokens']}, "
            f"completion={result.usage['completion_tokens']}, "
            f"total={result.usage['total_tokens']}"
        )

    tailored_tex = result.tex_content

    # Validate the output looks like LaTeX
    if not result.is_valid_latex:
        print(
            "⚠️  LLM output doesn't look like a complete LaTeX document "
            f"({'; '.join(result.validation_issues)}). "
            "Saving raw response for inspection..."
        )
        settings.running_template_dir.mkdir(parents=True, exist_ok=True)
        debug_path = settings.running_template_dir / "_debug_llm_response.txt"
        debug_path.write_text(result.raw_response)
        print(f"   Debug output saved to: {debug_path}")

    # Save to RunningTemplate
    write_working_template(tailored_tex, settings.working_template)
    print(f"📝 Tailored .tex written to: {settings.working_template}")

    # ── Step 2: Compile to PDF ──────────────────────────────────────────
    if not args.dry_run:
        if settings.working_template.exists():
            print(f"🔨 Compiling with {settings.latex_engine}...")
            try:
                compile_latex(
                    settings.working_template, company, role, settings=settings
                )
            except LatexCompilationError as error:
                _print_compilation_error(error)
        else:
            print("❌ No working template found to compile.")
            sys.exit(1)
    else:
        print("🏁 Dry run complete. No PDF generated.")


if __name__ == "__main__":
    main()
