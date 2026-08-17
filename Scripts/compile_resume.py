#!/usr/bin/env python3
"""
Compile the canonical LaTeX resume to PDF.

Reads the base template from LatexTemplate/, copies it to RunningTemplate/,
compiles with pdflatex, and saves the PDF to Output/.

Usage:
    python3 Scripts/compile_resume.py                    # Default output name
    python3 Scripts/compile_resume.py --open             # Open PDF after compile
    python3 Scripts/compile_resume.py --name "MyResume"  # Custom PDF filename
"""

import argparse
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
LATEX_TEMPLATE = PROJECT_ROOT / "LatexTemplate" / "GopalKumar_Resume.tex"
RUNNING_TEMPLATE = PROJECT_ROOT / "RunningTemplate" / "GopalKumar_Resume.tex"
OUTPUT_DIR = PROJECT_ROOT / "Output"

LATEX_ENGINE = "pdflatex"
LATEX_RUNS = 2


def compile_resume(output_name: str | None = None, open_pdf: bool = False) -> Path:
    """Copy template, compile, and save PDF to Output/. Returns the PDF path."""

    # 1. Validate source
    if not LATEX_TEMPLATE.exists():
        print(f"❌ Base template not found: {LATEX_TEMPLATE}")
        sys.exit(1)

    # 2. Copy to running directory
    RUNNING_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LATEX_TEMPLATE, RUNNING_TEMPLATE)
    print(f"📄 Copied: {LATEX_TEMPLATE.name} → {RUNNING_TEMPLATE}")

    # 3. Compile (2 passes for ToC, hyperlinks, etc.)
    print(f"🔨 Compiling with {LATEX_ENGINE} ({LATEX_RUNS} passes)...")
    tex_dir = RUNNING_TEMPLATE.parent
    for i in range(LATEX_RUNS):
        result = subprocess.run(
            [
                LATEX_ENGINE,
                "-interaction=nonstopmode",
                "-output-directory", str(tex_dir),
                RUNNING_TEMPLATE.name,
            ],
            cwd=str(tex_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"❌ Compilation failed on pass {i + 1}.")
            log_file = RUNNING_TEMPLATE.with_suffix(".log")
            if log_file.exists():
                # Print last ~30 lines of the log
                lines = log_file.read_text().splitlines()
                for line in lines[-30:]:
                    print(f"   {line}")
            sys.exit(1)

        # Report warnings
        warnings = [l for l in result.stderr.splitlines() if "Warning" in l]
        if warnings:
            for w in warnings:
                print(f"   ⚠️  {w.strip()}")

    # 4. Check PDF
    pdf = RUNNING_TEMPLATE.with_suffix(".pdf")
    if not pdf.exists():
        print("❌ PDF was not produced.")
        sys.exit(1)

    # 5. Copy to Output/
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_name:
        dest_name = f"{output_name}.pdf"
    else:
        today = date.today().strftime("%Y%m%d")
        dest_name = f"GopalKumar_Resume_{today}.pdf"

    dest = OUTPUT_DIR / dest_name
    shutil.copy2(pdf, dest)
    print(f"✅ PDF saved: {dest}")

    # 6. Optionally open
    if open_pdf:
        subprocess.run(["open", str(dest)])

    return dest


def main():
    parser = argparse.ArgumentParser(
        description="Compile LaTeX resume template to PDF"
    )
    parser.add_argument(
        "--name", "-n",
        type=str,
        default=None,
        help="Custom output filename (without .pdf extension)",
    )
    parser.add_argument(
        "--open", "-o",
        action="store_true",
        help="Open the PDF after compilation",
    )
    args = parser.parse_args()
    compile_resume(output_name=args.name, open_pdf=args.open)


if __name__ == "__main__":
    main()
