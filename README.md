# CareerHelper — Job-Tailored Resume Generator

CareerHelper takes a canonical LaTeX resume and a target job description, asks Kimi K3 to tailor the resume toward that role, then compiles the result into a PDF.

The tailoring prompt tells the model to extract job keywords, map them to existing experience, rewrite and reorder bullets, select the most relevant projects, and preserve factual accuracy. It must not change employers, titles, dates, degrees, awards, or invent experience.

## How the pipeline works

```text
Canonical LaTeX resume + job description
                  │
                  ▼
        scripts/tailor_resume.py
                  │
                  ▼
       Kimi K3 through OpenCode Go
                  │
                  ▼
      resources/workspace/*.tex
                  │
                  ▼
              pdflatex
                  │
                  ▼
        resources/output/*.pdf
```

The working implementation is the Python pipeline. The Rust application in `web/` is an unfinished browser frontend scaffold and does not yet run the complete generation flow. The planned replacement is a Next.js frontend backed by FastAPI; see [docs/nextjs-fastapi-plan.md](docs/nextjs-fastapi-plan.md).

## Project structure

```text
CareerHelper/
├── scripts/
│   ├── tailor_resume.py       # Job description → Kimi K3 → tailored LaTeX → PDF
│   ├── compile_resume.py      # Compile the canonical resume without tailoring
│   ├── config.py              # Paths, model, provider, and LaTeX configuration
│   └── requirements.txt
├── tests/
│   ├── test_all_opencode_models.py
│   └── test_deepseek_v4.py
├── resources/
│   ├── templates/
│   │   ├── latex/             # Canonical LaTeX resume; local and gitignored
│   │   └── source/            # Word/PDF references; local and gitignored
│   ├── workspace/             # Generated LaTeX and build files; gitignored
│   └── output/                # Generated PDFs; gitignored
├── docs/                      # Architecture and roadmap
├── web/                       # Rust/Axum frontend scaffold
├── .env                       # API keys and local overrides; gitignored
└── .gitignore
```

## Setup

```bash
pip install -r scripts/requirements.txt
```

Create `.env` in the project root:

```text
OPENCODE_GO_API_KEY=your-key
LLM_PROVIDER=opencode
LLM_MODEL=kimi-k3
```

Place the canonical resume at:

```text
resources/templates/latex/GopalKumar_Resume.tex
```

Install a LaTeX distribution that provides `pdflatex`.

## Usage

Interactive mode:

```bash
python3 scripts/tailor_resume.py
```

Pass a job-description file directly:

```bash
python3 scripts/tailor_resume.py \
  --company "Stripe" \
  --role "Technical Program Manager" \
  --job-file job-description.txt
```

Generate LaTeX without compiling a PDF:

```bash
python3 scripts/tailor_resume.py --dry-run
```

Compile the canonical resume without LLM tailoring:

```bash
python3 scripts/compile_resume.py
```

Refresh the OpenCode Go model availability report:

```bash
python3 tests/test_all_opencode_models.py
```

## Model configuration

The default model is `kimi-k3` through the OpenCode Go Chat Completions endpoint. The client sends the required stable `x-opencode-session` header and uses `temperature=1.0` with `top_p=0.95`.

Environment variables can override the defaults:

```text
LLM_MODEL=kimi-k3
LLM_TEMPERATURE=1.0
LLM_MAX_TOKENS=8000
OPENCODE_GO_BASE_URL=https://opencode.ai/zen/go/v1
```

## Git and private files

Git should contain source code, documentation, tests, database migrations, and empty resource-directory placeholders. It should not contain API keys, personal resumes, transcripts, Word/PDF source documents, generated LaTeX, generated PDFs, SQLite databases, build output, or generated model reports.

The initial repository commit already included personal documents. The current `.gitignore` prevents the reorganized local copies from being added again, but it does not remove them from existing GitHub history. Removing those historical copies requires a deliberate history rewrite and force push.
