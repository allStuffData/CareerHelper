"""Prompt construction for ATS-optimised resume tailoring.

The system prompt and user-prompt assembly are extracted from the original
interactive CLI (``Scripts/tailor_resume.py``) unchanged, so the LLM sees the
exact same instructions as before.
"""

from __future__ import annotations

import textwrap

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


def extract_section(tex: str, section: str) -> str:
    """Extract a named section from LaTeX source using the section anchors.

    Returns an empty string when the start anchor is absent, and the rest of
    the document when the end anchor is absent (matches legacy behaviour).
    """
    start_tag = SECTION_START[section]
    end_tag = SECTION_END[section]
    start_idx = tex.find(start_tag)
    if start_idx == -1:
        return ""
    end_idx = tex.find(end_tag, start_idx + len(start_tag))
    if end_idx == -1:
        return tex[start_idx:]
    return tex[start_idx:end_idx].rstrip()


def build_tailoring_prompt(
    job_description: str, company: str, role: str, tex: str
) -> str:
    """Build the user prompt from the target role, JD, and current template.

    ``tex`` is the full contents of the base LaTeX template. Passing it in
    (instead of reading a file here) keeps this function pure and easy to test.
    """
    return textwrap.dedent(f"""\
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
