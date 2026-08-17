#!/usr/bin/env python3
"""
Quick LaTeX → PDF compiler for the RunningTemplate.
Usage: python compile_resume.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent / "Scripts"
sys.path.insert(0, str(SCRIPTS))

from config import WORKING_TEMPLATE, OUTPUT_DIR, LATEX_ENGINE, LATEX_RUNS

TEX = WORKING_TEMPLATE
if not TEX.exists():
    print(f"❌ No working template at {TEX}")
    sys.exit(1)

print(f"🔨 Compiling {TEX.name} with {LATEX_ENGINE}...")
for i in range(LATEX_RUNS):
    result = subprocess.run(
        [LATEX_ENGINE, "-interaction=nonstopmode", "-output-directory",
         str(TEX.parent), TEX.name],
        cwd=str(TEX.parent),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log = TEX.with_suffix(".log")
        print(f"❌ Compilation failed (pass {i+1}).")
        if log.exists():
            print(log.read_text()[-1500:])
        sys.exit(1)

pdf = TEX.with_suffix(".pdf")
if pdf.exists():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUTPUT_DIR / pdf.name
    import shutil
    shutil.copy2(pdf, dest)
    print(f"✅ PDF: {dest}")
else:
    print("❌ PDF not found.")
    sys.exit(1)
