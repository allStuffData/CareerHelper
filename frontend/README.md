# CareerHelper Frontend (Phase 3)

Next.js App Router + TypeScript frontend for the CareerHelper resume-tailoring
pipeline. It talks only to the FastAPI backend; no LLM or LaTeX logic lives
here.

## Pages

| Route | Type | Purpose |
| --- | --- | --- |
| `/` | Server + client form | Job description, company, role, template selector, Generate button, API health feedback |
| `/generate/[id]` | Server + client progress | Live SSE timeline, structured error state, embedded PDF preview, PDF/LaTeX downloads |
| `/history` | Server | Past generations with open / download / delete |
| `/templates` | Server | Template list (or a clear empty state when the API is unavailable) |

## Architecture notes

- Server Components perform page-level reads against FastAPI.
- Client Components are limited to the generation form, the SSE progress
  timeline, and PDF/browser interactions.
- The browser never talks to FastAPI directly. Same-origin Route Handlers under
  `src/app/api/generations/[id]/{events,pdf,tex}` proxy SSE and artifacts, so
  `FASTAPI_BASE_URL` stays server-side and no public API URL or credential is
  exposed.
- `src/lib/api.ts` is the single server-side HTTP client; `src/lib/types.ts`
  mirrors the backend schemas.

## Environment

```bash
cp .env.example .env.local
# FASTAPI_BASE_URL=http://localhost:8000
```

## Development

```bash
npm install
npm run dev        # http://localhost:3000
npm run typecheck  # tsc --noEmit
npm run lint
npm run build
```

Start the backend separately (from the repository root):

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```
