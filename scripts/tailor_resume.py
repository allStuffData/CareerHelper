#!/usr/bin/env python3
"""
Resume Tailoring Pipeline — ATS-Optimized
==========================================
Takes a job description, uses Kimi K3 (via OpenCode Zen Go) to rewrite
the LaTeX resume for maximum ATS compatibility, then compiles to PDF.

Usage:
    python3 scripts/tailor_resume.py --job-file jd.txt --company "Stripe" --role "TPM"
    python3 scripts/tailor_resume.py --job "We need a PM who..." --company "Acme" --role "PM"
    python3 scripts/tailor_resume.py --job-file jd.txt --company "Acme" --role "PM" --dry-run
    python3 scripts/tailor_resume.py --compile-only --company "Acme" --role "PM"
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import uuid
from datetime import datetime
from pathlib import Path

# Add scripts dir to path so config imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    PROJECT_ROOT,
    BASE_TEMPLATE,
    WORKING_TEMPLATE,
    OUTPUT_DIR,
    RUNNING_TEMPLATE_DIR,
    LATEX_ENGINE,
    LATEX_RUNS,
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_API_KEY,
    LLM_API_BASE,
    OPENCODE_GO_API_KEY,
    OPENCODE_GO_BASE_URL,
    ANTHROPIC_API_KEY,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
)


# ═══════════════════════════════════════════════════════════════════════════
# ATS-OPTIMIZED SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = textwrap.dedent("""\
You are an expert ATS (Applicant Tracking System) optimization engine. Your job is to
rewrite a LaTeX resume so it scores maximum keyword matches against a target job
description, while remaining truthful, readable, and professionally compelling.

──────────────────────────────────────────────────────────────────────────────
YOUR PROCESS — execute these phases in order:
──────────────────────────────────────────────────────────────────────────────

PHASE 1 — KEYWORD EXTRACTION
Parse the job description and extract EVERY distinct skill, tool, methodology,
certification, domain concept, and qualification phrase. Group them into:
  • Hard skills:  languages, frameworks, tools, platforms, protocols
  • Soft skills:  leadership, communication, stakeholder management, etc.
  • Domain terms: industry jargon, methodologies (Agile, Scrum, Six Sigma),
                  compliance terms (SOX, GDPR), product terms
  • Action verbs: the specific verbs the JD uses to describe what the role does
  • Nice-to-haves:  preferred qualifications, bonus skills

PHASE 2 — KEYWORD MAPPING
For each bullet point in the candidate's resume, identify which JD keywords can
be NATURALLY woven in without fabricating experience. A keyword must fit
organically — never force a term that would raise suspicion in an interview.
Map: "JD keyword → which resume bullet/line it can appear in"

PHASE 3 — REWRITING (the core task)
Rewrite each resume bullet point to:
  a) START with a strong, varied action verb (avoid repeating the same verb)
     Use: Spearheaded, Engineered, Orchestrated, Drove, Architected, Championed,
     Scaled, Optimized, Automated, Designed, Delivered, Owned, Influenced, etc.
  b) Include AT LEAST ONE quantified result per bullet where the original had
     any metric (% improvement, $ amount, hours saved, team size, project count).
     If the original bullet implies impact but lacks a number, add a reasonable
     qualifier (e.g., "significantly reduced," "substantially improved").
  c) Naturally incorporate 1-3 JD keywords per bullet — no keyword stuffing.
  d) Use the JD's OWN TERMINOLOGY. If the JD says "cross-functional collaboration"
     and the resume says "worked across teams," use the JD's phrase.
  e) Keep each bullet to 1-2 lines max. Tight, punchy, scannable.

PHASE 4 — REORDERING & SELECTION
  • Reorder bullet points within each role so the most keyword-dense, relevant
    ones appear FIRST.
  • Select ONLY the 3-4 most relevant projects from the Key Projects section.
    DELETE less relevant projects entirely (including their LaTeX markup).
  • If a project has multiple bullet points, keep only the most relevant one.
  • Adjust the "Interests" line in Technical Stack to mirror keywords from the JD.

PHASE 5 — SKILLS ALIGNMENT
  • The Technical Stack section must reflect the JD's skills taxonomy.
  • If the JD emphasizes "AWS, Kubernetes, Terraform" but the resume has "Cloud,"
    expand to use the JD's exact terms (if the candidate genuinely has those skills).
  • DO NOT add skills the candidate doesn't have. DO expand vague categories into
    JD-aligned specifics when the candidate's experience supports it.

──────────────────────────────────────────────────────────────────────────────
ABSOLUTE CONSTRAINTS — never violate these:
──────────────────────────────────────────────────────────────────────────────
  1. NEVER change: company names, job titles, employment dates, degree names,
     university names, award names, or award amounts.
  2. NEVER invent experience, projects, or skills the candidate doesn't have.
  3. NEVER change or remove LaTeX commands, formatting macros, section headers,
     or the overall document structure. The .tex must compile without errors.
  4. NEVER drop entire sections (Education, Experience, etc.) — only condense
     content WITHIN sections.
  5. NEVER introduce LaTeX syntax errors.
  6. The resume MUST fit on ONE PAGE. If content overflows, shorten the LEAST
     relevant bullet points. Remove filler words. Combine short bullets.
  7. Factual integrity above all. It is better to leave a bullet unchanged than
     to exaggerate or fabricate.

──────────────────────────────────────────────────────────────────────────────
OUTPUT FORMAT
──────────────────────────────────────────────────────────────────────────────
Output the COMPLETE modified .tex file — every single line from \\documentclass
to \\end{document}. Wrap the entire .tex content in a ```latex code block:

```latex
\\documentclass[10pt,letterpaper]{article}
... (complete file) ...
\\end{document}
```

Do NOT summarize, truncate, or describe the changes. Output the FULL file.
""")

OPENCODE_SESSION_ID = str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════════
# SECTION ANCHORS (must match the comment markers in the .tex file)
# ═══════════════════════════════════════════════════════════════════════════

SECTION_START = {
    "header":     r"% === HEADER",
    "education":  r"% === EDUCATION",
    "tech_stack": r"% === TECHNICAL STACK",
    "experience": r"% === WORK EXPERIENCE",
    "projects":   r"% === KEY PROJECTS",
    "leadership": r"% === LEADERSHIP",
    "awards":     r"% === AWARDS",
}

SECTION_END = {
    "header":     r"% === EDUCATION",
    "education":  r"% === TECHNICAL STACK",
    "tech_stack": r"% === WORK EXPERIENCE",
    "experience": r"% === KEY PROJECTS",
    "projects":   r"% === LEADERSHIP",
    "leadership": r"% === AWARDS",
    "awards":     r"\end{document}",
}


# ═══════════════════════════════════════════════════════════════════════════
# LLM CLIENT
# ═══════════════════════════════════════════════════════════════════════════

def _get_client():
    """Return an OpenAI-compatible client for the configured provider."""
    from openai import OpenAI

    if LLM_PROVIDER == "opencode":
        api_key = OPENCODE_GO_API_KEY
        base_url = OPENCODE_GO_BASE_URL
        if not api_key:
            print("❌ OPENCODE_GO_API_KEY is not set.")
            print("   Make sure your .env file has: OPENCODE_GO_API_KEY=sk-...")
            sys.exit(1)
    elif LLM_PROVIDER == "anthropic":
        # Anthropic uses its own client, handled in _call_anthropic
        return None
    else:
        # Default: standard OpenAI
        api_key = LLM_API_KEY
        base_url = LLM_API_BASE
        if not api_key:
            print("❌ OPENAI_API_KEY is not set.")
            sys.exit(1)

    if LLM_PROVIDER == "opencode":
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "User-Agent": "careerhelper-resume-tailor/1.0",
                "x-opencode-session": OPENCODE_SESSION_ID,
            },
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def _call_openai_compatible(prompt: str) -> str:
    """Call any OpenAI-compatible API (OpenCode, standard OpenAI, etc.)."""
    client = _get_client()
    request_options = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
    }
    if LLM_PROVIDER == "opencode" and LLM_MODEL.startswith("kimi-"):
        request_options["top_p"] = 0.95

    response = client.chat.completions.create(**request_options)
    content = response.choices[0].message.content
    usage = response.usage
    if usage:
        print(f"   Tokens: prompt={usage.prompt_tokens}, "
              f"completion={usage.completion_tokens}, "
              f"total={usage.total_tokens}")
    return content


def _call_anthropic(prompt: str) -> str:
    """Call Anthropic Claude API."""
    from anthropic import Anthropic

    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY is not set.")
        sys.exit(1)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=LLM_MODEL,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )
    usage = response.usage
    if usage:
        print(f"   Tokens: input={usage.input_tokens}, "
              f"output={usage.output_tokens}")
    return response.content[0].text


def call_llm(prompt: str) -> str:
    """Dispatch to the configured LLM provider."""
    print(f"   Provider: {LLM_PROVIDER}  |  Model: {LLM_MODEL}")

    if LLM_PROVIDER == "anthropic":
        return _call_anthropic(prompt)
    else:
        # "opencode" and "openai" both use the OpenAI-compatible client
        return _call_openai_compatible(prompt)


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE PARSING
# ═══════════════════════════════════════════════════════════════════════════

def read_template(path: Path) -> str:
    """Read the full .tex template."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_section(tex: str, section: str) -> str:
    """Extract a named section from the LaTeX source."""
    start_tag = SECTION_START[section]
    end_tag = SECTION_END[section]
    start_idx = tex.find(start_tag)
    if start_idx == -1:
        return ""
    end_idx = tex.find(end_tag, start_idx + len(start_tag))
    if end_idx == -1:
        return tex[start_idx:]
    return tex[start_idx:end_idx].rstrip()


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════

def build_tailoring_prompt(
    job_description: str, company: str, role: str
) -> str:
    """Build the user prompt with job description and resume template."""

    tex = read_template(BASE_TEMPLATE)

    prompt = textwrap.dedent(f"""\
    ─── TARGET ROLE ───
    Company:  {company}
    Role:     {role}

    ─── JOB DESCRIPTION ───
    {job_description}

    ─── CURRENT LATEX RESUME ───
    {tex}

    ─── INSTRUCTIONS ───
    Follow your system prompt process exactly:
      1. Extract all keywords from the JD above
      2. Map them to the resume content
      3. Rewrite bullet points for ATS optimization
      4. Reorder and select the most relevant content
      5. Output the COMPLETE .tex file in a ```latex block

    Remember: factual integrity first. Never fabricate experience.
    """)
    return prompt


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE PARSING
# ═══════════════════════════════════════════════════════════════════════════

def extract_latex_from_response(response: str) -> str:
    """Extract LaTeX content from the LLM's response."""
    # Try ```latex ... ```
    if "```latex" in response:
        start = response.find("```latex") + len("```latex")
        if response[start] == "\n":
            start += 1
        end = response.find("```", start)
        if end != -1:
            return response[start:end].strip()

    # Try ``` ... ``` (no language tag)
    if "```" in response:
        start = response.find("```") + 3
        if response[start] == "\n":
            start += 1
        end = response.find("```", start)
        if end != -1:
            return response[start:end].strip()

    # Fallback: raw response
    return response.strip()


# ═══════════════════════════════════════════════════════════════════════════
# LATEX COMPILATION
# ═══════════════════════════════════════════════════════════════════════════

def compile_latex(tex_path: Path, company: str, role: str) -> Path | None:
    """Compile a .tex file to PDF. Returns the path to the output PDF."""
    tex_dir = tex_path.parent
    tex_name = tex_path.name

    for _ in range(LATEX_RUNS):
        result = subprocess.run(
            [LATEX_ENGINE, "-interaction=nonstopmode",
             "-output-directory", str(tex_dir), tex_name],
            cwd=str(tex_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log_file = tex_path.with_suffix(".log")
            if log_file.exists():
                log_tail = log_file.read_text()[-2000:]
                print(f"\n⚠️  LaTeX compilation failed. Log tail:\n{log_tail}")
            else:
                print(f"\n⚠️  LaTeX compilation failed:\n"
                      f"{result.stderr[-1000:]}")
            return None

    pdf = tex_path.with_suffix(".pdf")
    if not pdf.exists():
        print("⚠️  PDF not found after compilation.")
        return None

    # Copy to resources/output/ with a clean filename
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    safe_company = re.sub(r'[^a-zA-Z0-9_\- ]', '', company)[:30].strip()
    safe_role = re.sub(r'[^a-zA-Z0-9_\- ]', '', role)[:30].strip()
    output_pdf = OUTPUT_DIR / (
        f"GopalKumar_{safe_company}_{safe_role}_{date_str}.pdf"
    )
    shutil.copy2(pdf, output_pdf)
    print(f"✅ PDF saved to: {output_pdf}")
    return output_pdf


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


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Tailor your LaTeX resume with Kimi K3 for ATS optimization.\n\n"
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
        help="Skip LLM tailoring; just compile the current workspace template."
    )

    args = parser.parse_args()

    # ── Compile-only shortcut ────────────────────────────────────────────
    if args.compile_only:
        print("🔨 Compiling current workspace template...")
        if WORKING_TEMPLATE.exists():
            compile_latex(WORKING_TEMPLATE,
                          args.company or "Resume",
                          args.role or "Default")
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
    prompt = build_tailoring_prompt(job_description, company, role)
    response = call_llm(prompt)
    tailored_tex = extract_latex_from_response(response)

    # Validate the output looks like LaTeX
    if not tailored_tex.startswith(r"\documentclass"):
        print("⚠️  LLM output doesn't start with \\documentclass. "
              "Saving raw response for inspection...")
        debug_path = RUNNING_TEMPLATE_DIR / "_debug_llm_response.txt"
        debug_path.write_text(response)
        print(f"   Debug output saved to: {debug_path}")

    # Save to resources/workspace
    WORKING_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    WORKING_TEMPLATE.write_text(tailored_tex)
    print(f"📝 Tailored .tex written to: {WORKING_TEMPLATE}")

    # ── Step 2: Compile to PDF ──────────────────────────────────────────
    if not args.dry_run:
        if WORKING_TEMPLATE.exists():
            print(f"🔨 Compiling with {LATEX_ENGINE}...")
            compile_latex(WORKING_TEMPLATE, company, role)
        else:
            print("❌ No working template found to compile.")
            sys.exit(1)
    else:
        print("🏁 Dry run complete. No PDF generated.")


if __name__ == "__main__":
    main()
