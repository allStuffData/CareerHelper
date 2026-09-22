# Next.js + FastAPI Migration Plan

## Objective

Build a polished resume-tailoring application without duplicating the existing Python pipeline.

The application accepts a canonical resume and a job description, asks Kimi K3 to tailor the resume truthfully toward the role, compiles the resulting LaTeX, and returns a previewable and downloadable PDF.

## Architecture decision

- **Next.js App Router** owns pages, forms, progress UI, PDF preview, and generation history.
- **FastAPI** owns resume files, prompts, Kimi K3 calls, LaTeX validation and compilation, persistence, and downloads.
- **Python service modules** contain the business logic. CLI scripts and FastAPI call the same functions.
- **SQLite and local files** are used for the local-first version.
- **PostgreSQL, object storage, and a durable worker** are deferred until hosted multi-user deployment.
- The Rust frontend that once lived in `web/` was removed after the Next.js app reached parity; the repository no longer carries a second frontend.

## Request flow

```text
Browser
  │
  ▼
Next.js frontend
  │  POST generation request
  ▼
FastAPI
  ├── load canonical LaTeX resume
  ├── construct ATS prompt
  ├── call Kimi K3 through OpenCode Go
  ├── validate returned LaTeX
  ├── compile with pdflatex
  ├── save generation record and artifacts
  └── publish progress events
  │
  ▼
Next.js result page
  ├── progress timeline
  ├── PDF preview
  ├── PDF download
  └── LaTeX download
```

## Proposed repository structure

```text
CareerHelper/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── templates.py
│   │   │   └── generations.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   │       ├── llm.py
│   │       ├── tailoring.py
│   │       ├── latex.py
│   │       ├── storage.py
│   │       └── jobs.py
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   ├── generate/[id]/page.tsx
│   │   │   ├── history/page.tsx
│   │   │   └── templates/page.tsx
│   │   ├── components/
│   │   └── lib/
│   │       ├── api.ts
│   │       └── types.ts
│   ├── public/
│   └── package.json
├── scripts/                   # Thin CLI wrappers around backend services
├── resources/                 # Local and gitignored personal artifacts
├── tests/                     # OpenCode model diagnostics
├── docs/
└── docker-compose.yml         # Added when both applications are ready
```

## FastAPI endpoints

### System

- `GET /api/health` — checks API, database, writable storage, `pdflatex`, and configuration.

### Resume templates

- `GET /api/templates` — list saved resume templates.
- `POST /api/templates` — upload or create a template.
- `GET /api/templates/{id}` — retrieve template metadata.
- `PUT /api/templates/{id}` — create a new template version.
- `DELETE /api/templates/{id}` — remove or archive a template.

### Generations

- `POST /api/generations` — submit company, role, job description, and template ID; return a generation ID immediately.
- `GET /api/generations/{id}` — return status, metadata, errors, and artifact links.
- `GET /api/generations/{id}/events` — Server-Sent Events stream for progress.
- `GET /api/generations/{id}/pdf` — download or preview the PDF.
- `GET /api/generations/{id}/tex` — download the tailored LaTeX.
- `GET /api/generations` — list generation history.
- `DELETE /api/generations/{id}` — delete a generation and its artifacts.

## Generation states

```text
queued
  → preparing_prompt
  → calling_kimi
  → validating_latex
  → compiling_pdf
  → completed

Any state may transition to failed with a structured error.
```

FastAPI should return quickly from `POST /api/generations`. The frontend follows progress through SSE and fetches the completed generation when the terminal event arrives.

For the local MVP, an in-process asyncio job manager is sufficient. Before multi-instance hosting, replace it with a durable Redis-backed worker so jobs survive process restarts.

## Frontend pages

### `/`

- Job-description textarea
- Company and role fields
- Resume-template selector
- Generate button
- Validation and API health feedback

### `/generate/[id]`

- Live progress timeline
- Structured error state
- Embedded PDF preview after completion
- Download PDF and LaTeX actions
- Link to start another generation

### `/history`

- Company, role, status, template, and generation date
- Open, download, retry, and delete actions

### `/templates`

- Upload and select canonical resumes
- Template metadata and version history
- LaTeX source inspection for advanced use

## Next.js implementation rules

- Use the App Router and TypeScript.
- Default to Server Components for page-level reads.
- Use Client Components only for forms, SSE progress, PDF interactions, and browser state.
- Keep OpenCode credentials out of Next.js and the browser.
- Call FastAPI for every resume and generation business operation.
- Do not recreate Kimi or LaTeX logic in Next.js Route Handlers.
- Use the default Node.js runtime; no Edge runtime is needed.
- Keep the backend address in `FASTAPI_BASE_URL` for server-side access and expose a public API address only when direct browser access is required.

## Backend refactor before UI work

Extract the current `scripts/tailor_resume.py` implementation into reusable functions:

```text
tailor_resume(template, job_description, company, role) -> TailoringResult
compile_latex(latex_source, generation_id) -> ArtifactResult
run_generation(request, progress_callback) -> GenerationResult
```

The CLI becomes an adapter that gathers terminal input and calls these functions. FastAPI becomes another adapter. This prevents the web and CLI behavior from drifting apart.

## Data model

### Template

- ID
- Name
- Original filename
- Active version
- Created and updated timestamps

### Template version

- ID
- Template ID
- LaTeX source path or content
- Version number
- Created timestamp

### Generation

- ID
- Template-version ID
- Company
- Role
- Job description
- Status and current stage
- Model name
- Prompt and completion token counts
- Error code and message
- LaTeX and PDF artifact paths
- Created, started, and completed timestamps

Do not expose the complete prompt, API keys, or private resume files through public logs.

## Security requirements

- Store the OpenCode key only in the FastAPI environment.
- Validate file type, extension, MIME type, and upload size.
- Generate server-side artifact names; never trust uploaded filenames as paths.
- Run LaTeX with shell escape disabled and a time limit.
- Restrict every generation and download to its owner before enabling multiple users.
- Keep personal resources and generated artifacts outside Git.
- Avoid logging complete resumes, job descriptions, or LLM prompts in production.

## Migration phases

### Status

Phases 1–4 have met their exit conditions and are verified on `main`:

- **Phase 1 — done.** `scripts/tailor_resume.py` is a thin adapter over `backend/app/services/`; CLI flags, output naming, and exit codes are unchanged.
- **Phase 2 — done.** A live run produced `queued → preparing_prompt → calling_kimi → validating_latex → compiling_pdf → completed`, and `/api/generations/{id}/pdf` served a real compiled PDF.
- **Phase 3 — done.** The whole flow works in the browser: `/` form → `/generate/[id]` with live SSE progress, embedded preview, and PDF/LaTeX downloads.
- **Phase 4 — done.** Template upload/versioning, history, retry, and delete are wired in the UI, so daily use no longer needs a terminal.
- **Phase 5 — partial.** Shipped: CI (`.github/workflows/ci.yml` runs the backend suite plus frontend typecheck/lint/build on push and PR) and startup reconciliation of interrupted jobs (`GenerationStore.reap_interrupted`). Not built: authentication/ownership, PostgreSQL, object storage, a Redis-backed durable worker, and containerization — all of which are multi-user or hosted-deployment concerns. The current design is deliberately local-first: one process, SQLite, artifacts on local disk, loopback binding.

Restated honestly, the Phase 5 exit condition is not met yet. "Jobs survive restarts" holds only in the weak sense — an interrupted job is marked failed on the next start rather than resumed. "Private artifacts are protected per user" does not hold: with a single local user there is no ownership model, and the API is protected only by being bound to loopback.

### Phase 1 — Python service extraction

- Create `backend/app/services` modules.
- Move prompt construction, OpenCode client, response parsing, and LaTeX compilation out of the CLI.
- Keep `scripts/tailor_resume.py` working as a thin wrapper.
- Add focused tests for response parsing, filename sanitization, and compilation errors.

**Exit condition:** CLI output is unchanged but all core work runs through reusable services.

### Phase 2 — FastAPI MVP

- Add health and generation endpoints.
- Add SQLite generation storage.
- Add an in-process job manager and SSE progress.
- Add PDF and LaTeX download endpoints.

**Exit condition:** A request made with API documentation or `curl` produces a downloadable PDF.

### Phase 3 — Next.js MVP

- Scaffold the App Router frontend in `frontend/`.
- Build the generation form and result page.
- Connect SSE progress updates.
- Add PDF preview and downloads.
- Add loading, empty, and error states.

**Exit condition:** The complete resume-tailoring flow works in the browser.

### Phase 4 — Templates and history

- Add template upload and versioning.
- Add generation history, retry, and deletion.
- Add responsive styling and accessibility checks.

**Exit condition:** Daily use no longer requires terminal commands.

### Phase 5 — Production readiness

- Add authentication and ownership checks.
- Move SQLite to PostgreSQL if multiple users are needed.
- Move artifacts to object storage.
- Add a durable worker and Redis queue.
- Containerize FastAPI with `pdflatex` and Next.js with standalone output.
- Add CI for Python tests, frontend lint/type checks, and production builds.

**Exit condition:** Jobs survive restarts and private artifacts are protected per user.

## Deployment recommendation

Start with Docker Compose on one machine:

- Next.js on port `3000`
- FastAPI on port `8000`
- SQLite and artifacts mounted into backend-only volumes
- A reverse proxy exposes only the required web and API routes

For a hosted split deployment, Next.js may run on Vercel, but FastAPI must run in a container or VM that includes LaTeX and supports longer generation jobs. The browser must never receive the OpenCode API key.

## First implementation milestone

Implement Phase 1 and Phase 2 before building much frontend UI. The first vertical slice should support:

1. Submit a job description through FastAPI.
2. Run the existing DeepSeek V4 Pro tailoring pipeline.
3. Stream five meaningful progress states.
4. Compile the PDF.
5. Download the result.

Once that API contract is stable, the Next.js frontend becomes straightforward and does not need to duplicate backend behavior.
