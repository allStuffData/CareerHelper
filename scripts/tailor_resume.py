#!/usr/bin/env python3
"""
Resume Tailoring Pipeline — ATS-Optimized (thin CLI adapter)
=============================================================
Takes a job description, uses the configured LLM to rewrite the LaTeX resume
for maximum ATS compatibility, then compiles to PDF.

All pipeline logic lives in ``backend/app/services``; this file only handles
argument parsing, interactive prompts, console output, and exit codes.

Usage:
    python3 scripts/tailor_resume.py --job-file jd.txt --company "Stripe" --role "TPM"
    python3 scripts/tailor_resume.py --job "We need a PM who..." --company "Acme" --role "PM"
    python3 scripts/tailor_resume.py --job-file jd.txt --company "Acme" --role "PM" --dry-run
    python3 scripts/tailor_resume.py --compile-only --company "Acme" --role "PM"
"""

import argparse
import sys
from pathlib import Path

# Add the repository root to sys.path so the ``backend`` package is importable
# when this script is run directly (``python3 scripts/tailor_resume.py``).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.jobs import (
    GenerationRequest,
    ProgressEvent,
    run_generation,
)
from backend.app.services.latex import compile_latex
from backend.app.services.settings import load_settings
from backend.app.services.storage import build_generation_id


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


def _print_compilation_error(error: str, log_tail: str) -> None:
    if log_tail:
        print(f"\n⚠️  LaTeX compilation failed. Log tail:\n{log_tail}")
    else:
        print(f"\n⚠️  LaTeX compilation failed:\n{error}")


# ═══════════════════════════════════════════════════════════════════════════
# PROGRESS RENDERING
# ═══════════════════════════════════════════════════════════════════════════

def _make_progress_renderer(settings):
    """Return a callback that renders service progress like the old CLI."""

    def render(event: ProgressEvent) -> None:
        if event.stage == "tailored":
            tailoring = event.tailoring
            if tailoring and tailoring.usage:
                usage = tailoring.usage
                print(
                    f"   Tokens: prompt={usage['prompt_tokens']}, "
                    f"completion={usage['completion_tokens']}, "
                    f"total={usage['total_tokens']}"
                )
            if tailoring and not tailoring.is_valid:
                reason = (
                    "the model hit the output-token limit"
                    if tailoring.was_truncated
                    else "the response was not a complete LaTeX document"
                )
                print(
                    f"⚠️  LLM output can't be compiled — {reason} "
                    f"({'; '.join(tailoring.validation_errors)}). "
                    "Saving raw response for inspection..."
                )
                settings.running_template_dir.mkdir(parents=True, exist_ok=True)
                debug_path = (
                    settings.running_template_dir / "_debug_llm_response.txt"
                )
                debug_path.write_text(tailoring.raw_response)
                print(f"   Debug output saved to: {debug_path}")
        elif event.stage == "tex_written":
            print(f"📝 Tailored .tex written to: {event.path}")
        elif event.stage == "compiling":
            print(f"🔨 Compiling with {settings.latex_engine}...")
        elif event.stage == "compiled" and event.artifact:
            print(f"✅ PDF saved to: {event.artifact.pdf_path}")
        elif event.stage == "compilation_failed" and event.artifact:
            _print_compilation_error(
                event.artifact.error or "", event.artifact.log_tail
            )
        elif event.stage == "dry_run":
            print("🏁 Dry run complete. No PDF generated.")

    return render


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
        help="Skip LLM tailoring; just compile the current working template."
    )

    args = parser.parse_args()
    settings = load_settings()

    # ── Compile-only shortcut ────────────────────────────────────────────
    if args.compile_only:
        print("🔨 Compiling current working template...")
        if not settings.working_template.exists():
            print("❌ No working template found to compile.")
            sys.exit(1)
        generation_id = build_generation_id(
            args.company or "Resume", args.role or "Default"
        )
        source = settings.working_template.read_text(encoding="utf-8")
        artifact = compile_latex(source, generation_id, settings=settings)
        if artifact.success:
            print(f"✅ PDF saved to: {artifact.pdf_path}")
        else:
            _print_compilation_error(
                artifact.error or "", artifact.log_tail
            )
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

    # ── Step 1 & 2: tailor and compile via reusable services ─────────────
    print(f"\n📋 Tailoring resume for {role} at {company}...")
    print(f"   Provider: {settings.llm_provider}  |  Model: {settings.llm_model}")

    request = GenerationRequest(
        job_description=job_description,
        company=company,
        role=role,
        dry_run=args.dry_run,
        settings=settings,
    )
    result = run_generation(
        request, progress_callback=_make_progress_renderer(settings)
    )

    if result.error_type and result.error_type != "compilation":
        # llm / tailoring / truncated: the progress callback may have printed
        # detail, but the run still failed and must not exit 0.
        print(f"❌ {result.error}")
        if result.missing_env_var:
            print(f"   Make sure your .env file has: {result.missing_env_var}=...")
        sys.exit(1)

    if result.error_type == "compilation":
        # Warning already rendered by the progress callback.
        return


if __name__ == "__main__":
    main()
