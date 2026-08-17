# CareerHelper — ATS-Optimized Resume Pipeline

> One LaTeX template. One command. A resume tailored to any job in seconds.

## What this does

You paste a job description. DeepSeek V4 Pro rewrites your LaTeX resume to maximize
keyword matches against the job description — reordering bullet points, weaving in
JD terminology, and pruning irrelevant content — then compiles it to a clean,
one-page PDF. All without ever changing where you worked or what you did.

```
$ python3 Scripts/tailor_resume.py

╔══════════════════════════════════════════════════╗
║   📋  Resume Tailoring — ATS Optimizer           ║
╚══════════════════════════════════════════════════╝

Company name: Stripe
Role / position: Technical Program Manager

📄  Paste the job description below (Ctrl+D when done):
────────────────────────────────────────────────────────────
[ you paste the JD here — as many lines as you want ]
[ Ctrl+D when done ]
────────────────────────────────────────────────────────────

📋 Tailoring resume for Technical Program Manager at Stripe...
🔨 Compiling with pdflatex...
✅ PDF saved to: Output/GopalKumar_Stripe_TechnicalProgramManager_20260809.pdf
```

## Project structure

```
CareerHelper/
├── LatexTemplate/              # Canonical base resume — never hand-edited per job
│   └── GopalKumar_Resume.tex
├── RunningTemplate/            # Working copy — gets overwritten by the LLM pipeline
│   └── GopalKumar_Resume.tex
├── Output/                     # Tailored PDFs land here
├── Scripts/
│   ├── tailor_resume.py        # Interactive pipeline: paste JD → LLM → LaTeX → PDF
│   ├── config.py               # Paths, LLM provider, LaTeX engine settings
│   └── requirements.txt        # openai, anthropic, python-dotenv
├── WordTemplates/              # Archive of original Word/PDF resumes
├── docs/                       # Project context, roadmap, implementation checklist
├── compile_resume.py           # Standalone LaTeX → PDF compiler (no LLM)
└── .env                        # API keys (gitignored)
```

## Setup

```bash
# 1. Install Python dependencies
pip install -r Scripts/requirements.txt

# 2. Add your API key to the .env file
echo 'OPENCODE_GO_API_KEY=sk-...' > .env

# 3. (macOS) Make sure LaTeX is installed
#    Already included if you have MacTeX. Otherwise:
#    brew install --cask mactex

# 4. Run it
python3 Scripts/tailor_resume.py
```

## How it works

The pipeline has three stages:

1. **LLM Tailoring** — DeepSeek V4 Pro (via OpenCode Zen Go) receives a 5-phase
   ATS-optimization system prompt. It extracts keywords from the JD, maps them to
   your experience, rewrites bullet points for maximum keyword density, reorders
   content by relevance, and outputs the complete `.tex` file.

2. **LaTeX Compilation** — `pdflatex` compiles the `.tex` to PDF. The template is
   tuned to always produce exactly one page.

3. **Output** — The PDF is saved to `Output/GopalKumar_{Company}_{Role}_{Date}.pdf`.

## LLM providers

| Provider | Default model | Config |
|----------|--------------|--------|
| OpenCode Zen Go (default) | `deepseek-v4-pro` | `OPENCODE_GO_API_KEY` in `.env` |
| OpenAI | `gpt-4o` | `OPENAI_API_KEY` in `.env` + `--provider openai` |
| Anthropic | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` in `.env` + `--provider anthropic` |

## CLI reference

```bash
# Interactive mode (default)
python3 Scripts/tailor_resume.py

# Scripting mode (skip prompts)
python3 Scripts/tailor_resume.py --company "Stripe" --role "TPM" --job-file jd.txt

# Preview without compiling
python3 Scripts/tailor_resume.py --dry-run

# Just recompile the current RunningTemplate
python3 Scripts/tailor_resume.py --compile-only

# Standalone compiler (no LLM)
python3 compile_resume.py
```

## Future: Rust frontend

See [`docs/project_context.md`](docs/project_context.md) for the full architecture
and [`docs/project_checklist.md`](docs/project_checklist.md) for the implementation roadmap.

The vision is a clean, minimal web UI where users can:

- Upload resumes (PDF, Word, Markdown, HTML) and extract structured templates
- Maintain multiple template variants for different role types
- Paste a job description and get a tailored PDF in seconds
- All powered by the same LaTeX pipeline, wrapped in a fast Rust backend

---
