# Project Context — CareerHelper

Architecture, design principles, and technology decisions for CareerHelper.
This document describes the **current** implementation: a local-first Next.js
frontend over a FastAPI backend that wraps the original Python/LaTeX pipeline.
For the phase-by-phase plan and roadmap see
[nextjs-fastapi-plan.md](nextjs-fastapi-plan.md).

---

## 1. Vision

A clean, minimal web application where the resume is defined once as a canonical
LaTeX template, and any job description can be turned into an ATS-optimized,
truthfully-tailored PDF in seconds. No accounts. No clutter. Paste a JD, get a PDF.

## 2. Architecture Overview

```text
Browser
  │
  ▼
Next.js App Router (frontend/)
  /            /generate/[id]      /history     /templates
  │  same-origin only: Server Actions + Route Handler proxies
  ▼
FastAPI backend (backend/app/)
  api/health   api/generations   api/templates
  services/job_manager   services/job_runner   services/integration
  db.py (SQLite, WAL)
  │  in-process Python calls
  ▼
Phase 1 pipeline services (backend/app/services/)
  tailoring → llm (OpenCode Go) → response_parser
  → latex (pdflatex) → storage
  │
  ▼
resources/templates/latex/   resources/workspace/   resources/output/
```

The browser never talks to FastAPI directly and never sees the API key or the
backend base URL. Every credential, prompt, and LaTeX concern stays server-side.

## 3. Technology Stack

- **Frontend** — Next.js (App Router) + TypeScript. Server Components by
  default; Client Components only for the form, SSE progress, and PDF
  interactions. Styling is Tailwind. No LLM or LaTeX logic lives here.
- **Backend** — FastAPI + Pydantic v2, run with Uvicorn.
- **Business logic** — plain Python service modules shared by the CLI
  (`scripts/`) and the API. Neither is a fork of the other.
- **Persistence** — SQLite (WAL, foreign keys on) plus local files under
  `backend/data/artifacts/`. Local-first by design.
- **LLM** — OpenCode Go chat-completions endpoint, `deepseek-v4-pro` by default.
- **PDF** — `pdflatex` from a local TeX distribution, resolved automatically
  (PATH, then common install locations such as `/Library/TeX/texbin`).

Deferred to a hosted multi-user phase: auth/ownership, PostgreSQL, object
storage, a durable worker queue, Docker, and CI. See Phase 5 of the plan.

## 4. Design Principles

### Visual language

```text
Theme:       Light blueish — calm, professional, minimal
Primary:     #3B82F6  (blue-500)      — buttons, links, accents
Primary bg:  #EFF6FF  (blue-50)       — cards, panels, selected states
Surface:     #FFFFFF  (white)         — page background
Text:        #1E293B  (slate-800)     — body text
Muted:       #64748B  (slate-500)     — secondary text, placeholders
Success:     #10B981  (emerald-500)   — completion states
Border:      #E2E8F0  (slate-200)     — dividers, input borders
```

### UX principles

- **Zero friction** — the landing page *is* the JD paste area. No signup, no
  navigation required for the core action.
- **Progressive disclosure** — template management lives on a secondary page.
- **Instant feedback** — the Generate button opens a live progress timeline
  driven by server-sent events, stage by stage.
- **Truthful tailoring** — the prompt may reorder, rephrase, and emphasize, but
  it must never change employers, titles, dates, degrees, or awards, and must
  never invent experience.

## 5. Data Model

```text
templates(id, name, description, original_filename,
          active_version_id, created_at, updated_at)
    │ 1:N
    ▼
template_versions(id, template_id → templates ON DELETE CASCADE,
                  version, latex_content, created_at)

generations(id, company, role, job_description, status, progress,
            template_version_id → template_versions ON DELETE SET NULL,
            tex_path, pdf_path, error_code, error_message,
            prompt_tokens, completion_tokens, model, created_at, updated_at)
```

`templates.active_version_id` is the version a new generation picks up by
default. A generation stores the version it actually used, so later edits to a
template never rewrite history.

## 6. Key Flows

### Flow 1: Generate a tailored resume

```text
User pastes a job description, picks company/role/template, clicks Generate
  → Server Action POSTs /api/generations (same-origin)
  → backend enqueues the generation and returns its id
  → browser opens /generate/{id} and subscribes to /api/generations/{id}/events
  → backend, stage by stage:
      1. loads the selected template's LaTeX
      2. constructs the ATS-optimization prompt
      3. calls the LLM through OpenCode Go
      4. parses and validates the returned LaTeX
      5. writes the working .tex to resources/workspace/
      6. runs pdflatex, copies the PDF to resources/output/
      7. persists the generation record and emits the terminal event
  → frontend shows the progress timeline, PDF preview, and downloads
```

### Flow 2: First-time setup

```text
Clone → install Python and frontend dependencies → create .env with the
API key → drop the canonical resume at
resources/templates/latex/GopalKumar_Resume.tex → scripts/dev.sh
```

The canonical `.tex` is personal and gitignored, so a fresh clone must supply it.

### Flow 3: Template management

```text
User opens /templates → sees stored templates with their active version
  → can create a template (paste or upload .tex) or add a new version
  → the active version is what new generations use
```

## 7. Repository Layout

```text
CareerHelper/
├── backend/
│   ├── app/
│   │   ├── api/            # health, generations, templates routers
│   │   ├── core/           # settings
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # pipeline + job manager/runner/integration
│   │   ├── db.py           # SQLite schema and store
│   │   └── main.py         # app factory and lifespan
│   └── tests/              # Phase 1 service tests
├── frontend/               # Next.js App Router UI
├── scripts/                # CLI entry points (tailor_resume.py, dev.sh)
├── tests/                  # Phase 2 API tests
├── resources/              # templates, workspace, output (gitignored contents)
└── docs/
```

## 8. Security Notes

- The API key is read from the environment (or the gitignored `.env`) and is
  never sent to the browser.
- Services never log resume content, job descriptions, or prompts.
- LaTeX runs with shell escape disabled and under a timeout.
- Artifact names are sanitized and boundary-checked; only files under the
  configured artifact roots are ever served.

## See also

- [nextjs-fastapi-plan.md](nextjs-fastapi-plan.md) — phases, exit conditions, roadmap
- [job_search_feature.md](job_search_feature.md) — research notes for a future
  job-discovery subsystem
- [README.md](../README.md) — setup and run instructions
