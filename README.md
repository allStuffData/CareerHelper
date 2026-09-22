# CareerHelper — Job-Tailored Resume Generator

CareerHelper takes a canonical LaTeX resume and a target job description, asks an LLM (DeepSeek V4 Pro via OpenCode Go by default) to tailor the resume toward that role, then compiles the result into a PDF.

The tailoring prompt tells the model to extract job keywords, map them to existing experience, rewrite and reorder bullets, select the most relevant projects, and preserve factual accuracy. It must not change employers, titles, dates, degrees, awards, or invent experience.

## Web app (FastAPI + Next.js)

The browser talks only to Next.js; the FastAPI base URL and the API key stay server-side.

```bash
# 1. Python + frontend dependencies (once)
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"
(cd frontend && npm install)

# 2. Configure the project-root .env (gitignored)
#    OPENCODE_GO_API_KEY=...
#    LLM_PROVIDER=opencode        # optional
#    LLM_MODEL=deepseek-v4-pro    # optional

# 3. Put the canonical resume at
#    resources/templates/latex/GopalKumar_Resume.tex

# 4. Run both servers, then open http://localhost:3000
scripts/dev.sh
```

Run each server by hand instead:

```bash
# FastAPI on :8000
cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

# Next.js on :3000 (reads FASTAPI_BASE_URL server-side only)
cd frontend && FASTAPI_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Backend tests and frontend checks:

```bash
.venv/bin/python -m pytest tests backend/tests -q
cd frontend && npm run typecheck && npm run lint && npm run build
```

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

The same Python pipeline powers both the CLI (`scripts/`) and the web app: the reusable service layer lives in `backend/app/services/`, the FastAPI application in `backend/app/`, and the Next.js MVP in `frontend/`.

## Project structure

```text
CareerHelper/
├── scripts/
│   ├── tailor_resume.py       # Job description → Kimi K3 → tailored LaTeX → PDF
│   ├── compile_resume.py      # Compile the canonical resume without tailoring
│   ├── config.py              # Paths, model, provider, and LaTeX configuration
│   └── requirements.txt
├── backend/
│   ├── app/                   # FastAPI app: api/, core/, services/, schemas/
│   ├── tests/                 # Phase 1 service tests
│   └── data/                  # SQLite database and stored artifacts; gitignored
├── frontend/                  # Next.js App Router UI
├── tests/                     # Phase 2 API tests; OpenCode model diagnostics
├── resources/
│   ├── templates/
│   │   ├── latex/             # Canonical LaTeX resume; local and gitignored
│   │   └── source/            # Word/PDF references; local and gitignored
│   ├── workspace/             # Generated LaTeX and build files; gitignored
│   └── output/                # Generated PDFs; gitignored
├── docs/                      # Architecture and roadmap
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
LLM_MODEL=deepseek-v4-pro
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

The default model is `deepseek-v4-pro` through the OpenCode Go Chat Completions endpoint, with `temperature=0.3` and `max_tokens=32000`. The client sends the required stable `x-opencode-session` header.

Environment variables can override the defaults:

```text
LLM_MODEL=deepseek-v4-pro
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=32000
OPENCODE_GO_BASE_URL=https://opencode.ai/zen/go/v1
```

The output-token budget matters: a full tailored resume runs to roughly 7–8k
tokens, so setting `LLM_MAX_TOKENS` too low truncates the LaTeX mid-document.
When the model stops at the limit, the generation fails with
`error_code=truncated` and names the limit, instead of being misreported as a
LaTeX compile error.

## Git and private files

Git should contain source code, documentation, tests, database migrations, and empty resource-directory placeholders. It should not contain API keys, personal resumes, transcripts, Word/PDF source documents, generated LaTeX, generated PDFs, SQLite databases, build output, or generated model reports.

The initial repository commit already included personal documents. The current `.gitignore` prevents the reorganized local copies from being added again, but it does not remove them from existing GitHub history. Removing those historical copies requires a deliberate history rewrite and force push.
