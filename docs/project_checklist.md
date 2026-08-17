# Project Checklist — Rust Frontend

> Implementation roadmap for the CareerHelper web application.
> Each phase is ordered by dependency. Checkboxes track progress.

---

## Phase 0 — Project Scaffold

- [x] **0.1** Initialize Rust project
  - `cargo init careerhelper-web` → created as `web/` subdirectory
  - Set up `Cargo.toml` with all dependencies (axum, tokio, sqlx, askama, reqwest, tower-http, etc.)
  - Configure `.env` loading via `dotenvy` → loads from parent `../.env`

- [x] **0.2** Set up Tailwind CSS
  - Downloaded Tailwind v4 standalone CLI (`tailwindcss-macos-arm64`)
  - Created `input.css` with `@import "tailwindcss"` (v4 CSS-first config)
  - **Dev mode**: uses CDN `<script src="https://cdn.tailwindcss.com">` in `base.html`
  - **Production**: `./tailwindcss-macos-arm64 -i input.css -o static/tailwind.css --minify`

- [x] **0.3** Set up SQLite + SQLx
  - Created migration `001_initial.sql`: `templates`, `template_versions`, `generations` tables
  - Added indexes on `generations.created_at` and `template_versions.template_id`
  - SQLx macros enabled for compile-time query checking

- [x] **0.4** Set up Askama templates
  - Created `templates/base.html` layout (navbar, content block, footer, CDN scripts)
  - Created `templates/index.html` landing page (JD textarea, company/role inputs, template selector, Generate button)
  - Askama `with-axum` feature enabled for Axum integration
  - Static file serving wired via `ServeDir`

- [x] **0.5** Set up Axum router
  - `GET /` → landing page (Askama-rendered index template)
  - `GET /health` → JSON health check (pdflatex detection)
  - Middleware: `TraceLayer`, `CompressionLayer`, `CorsLayer::permissive()`
  - Config loaded from `.env` via `dotenvy`

**Gate:** `cargo run` → browser shows styled landing page at `http://localhost:3000` ✅

---

## Phase 1 — Document Parsing

- [ ] **1.1** PDF text extraction
  - Integrate `pdf-extract` or `lopdf` crate
  - Handle multi-column PDFs (common in resumes)
  - Extract: name, contact info, sections (Education, Experience, Skills)
  - Return raw text or structured JSON

- [ ] **1.2** DOCX text extraction
  - Integrate `docx-rs` or shell out to `pandoc` as a fallback
  - Extract headings, bullet lists, bold text (structural hints)
  - Return structured text

- [ ] **1.3** Markdown / HTML parsing
  - Markdown: convert to plain text, preserve heading hierarchy
  - HTML: strip tags, extract text blocks
  - Both can use `pandoc` as a reliable fallback

- [ ] **1.4** Content-to-LaTeX mapper
  - Given structured content from any parser, render it into the base LaTeX template
  - Map: Name → `\textbf{Gopal Kumar}`, Experience items → `\resumeItem{...}`, etc.
  - Preserve section ordering and LaTeX structure
  - Handle edge cases: missing sections, very long bullet points

- [ ] **1.5** Upload endpoint
  - `POST /api/upload` — accepts multipart file upload
  - Detects file type (PDF, DOCX, MD, HTML, TXT)
  - Routes to correct parser, returns parsed content as JSON
  - Displays a preview in the browser before saving as template

**Gate:** Upload a PDF resume → see parsed content preview in the browser

---

## Phase 2 — Template Management

- [ ] **2.1** Template CRUD API
  - `GET /api/templates` → list all templates
  - `POST /api/templates` → create new template (name + LaTeX content)
  - `GET /api/templates/:id` → get template with latest version
  - `PUT /api/templates/:id` → update (creates new version)
  - `DELETE /api/templates/:id` → soft-delete

- [ ] **2.2** Template list UI
  - Card grid showing template name, description, version count, last used date
  - Each card: [Use] [Edit] [Duplicate] [Delete] actions
  - Empty state: "No templates yet. Upload a resume to create your first template."
  - HTMX-powered: delete removes card without page reload

- [ ] **2.3** Template editor
  - Full-page LaTeX editor with syntax highlighting
  - Live preview toggle (compile .tex → render PDF snippet)
  - Version history: list of previous versions with timestamps
  - "Save as new version" vs "Overwrite current"

- [ ] **2.4** Predefined templates
  - Ship 2–3 clean base templates (different visual styles):
    - Modern (current style — dark section headers, accent rule)
    - Classic (serif fonts, more traditional)
    - Compact (ultra-dense, for cramming more content)
  - These are read-only; user duplicates to customize

- [ ] **2.5** Template selector on landing page
  - Dropdown or pill selector to choose active template
  - Shows template name + short description
  - Defaults to most recently used

**Gate:** Create, edit, duplicate, and delete templates — all persisted in SQLite

---

## Phase 3 — Generation Pipeline

- [ ] **3.1** LLM client service
  - Generic trait for LLM providers
  - OpenCode Zen Go implementation (DeepSeek V4 Pro)
  - OpenAI fallback implementation
  - Configurable: model, temperature, max_tokens per provider
  - Streaming support: SSE endpoint for real-time progress

- [ ] **3.2** Prompt construction
  - Port the 5-phase ATS system prompt from `Scripts/tailor_resume.py`
  - Template engine: inject JD, company, role, and LaTeX content into prompt
  - Keep prompt in a template file (not hardcoded) for easy iteration

- [ ] **3.3** LaTeX compilation service
  - Detect `pdflatex` / `xelatex` on system PATH
  - Run 2-pass compilation in a temp directory
  - Parse `.log` file for errors, return structured error messages
  - Clean up `.aux`, `.log`, `.out` files after compilation

- [ ] **3.4** Generation endpoint
  - `POST /api/generate` — accepts: JD text, company, role, template_id
  - Orchestrates: load template → build prompt → call LLM → extract .tex → compile → save
  - Returns: generation ID, download URL, token usage stats
  - Streams progress via SSE: `{ "stage": "extracting_keywords" }`, `{ "stage": "compiling" }`, etc.

- [ ] **3.5** Download endpoint
  - `GET /api/download/:id` — serves the generated PDF
  - Sets `Content-Disposition: attachment` with a clean filename
  - Also serves the `.tex` source for inspection

- [ ] **3.6** Generation history
  - List of past generations (company, role, date, template used)
  - Click to re-download PDF
  - Click to view the JD that was used
  - [Delete] old generations

**Gate:** Paste a JD → generate → download a correctly tailored 1-page PDF

---

## Phase 4 — Polish & UX

- [ ] **4.1** Loading states & progress
  - Generate button → spinner + live status text
  - SSE stream updates the status in real-time:
    "Extracting keywords from JD…" →
    "Tailoring bullet points…" →
    "Compiling LaTeX…" →
    "Done! ✅"
  - Handle timeout gracefully (DeepSeek can take 30–60s for large prompts)

- [ ] **4.2** Error handling
  - LLM API errors: show user-friendly message, offer retry
  - LaTeX compilation errors: show the error line + context, not a raw log dump
  - Upload errors: file too large, unsupported format, parse failure
  - All errors logged with `tracing` for debugging

- [ ] **4.3** PDF preview
  - Embed PDF in an `<iframe>` or use `pdf.js` for in-browser preview
  - Fallback: "Open PDF in new tab" link
  - Mobile: force download (preview is unreliable on small screens)

- [ ] **4.4** JD textarea improvements
  - Auto-resize to fit content
  - Character/word count
  - "Clear" button
  - Paste detection (highlight border on paste event)

- [ ] **4.5** Responsive design
  - Mobile: single-column, full-width cards, bottom-sheet actions
  - Tablet: comfortable but not wasteful
  - Desktop: max-width container (960px), centered

- [ ] **4.6** Keyboard shortcuts
  - `Cmd/Ctrl + Enter` → Generate
  - `Cmd/Ctrl + K` → focus JD textarea
  - `Esc` → close modals/drawers

- [ ] **4.7** Dark mode (future)
  - Tailwind `dark:` variants for all components
  - System preference detection (`prefers-color-scheme`)
  - Manual toggle in navbar

**Gate:** The app feels polished — no jarring flashes, every action has feedback, errors are helpful

---

## Phase 5 — Deployment

- [ ] **5.1** Single-binary build
  - `cargo build --release` produces a self-contained binary
  - Embeds SQLite, Askama templates (compile-time), static assets
  - External dependencies documented: `pdflatex`, `.env` file

- [ ] **5.2** Reverse proxy config
  - `nginx` or `caddy` config for TLS termination
  - Proxy pass to `localhost:3000`
  - Rate limiting on `/api/generate` (prevent API cost abuse)
  - `Caddyfile` example in the repo

- [ ] **5.3** Health check & monitoring
  - `GET /health` → checks: pdflatex available, SQLite writable, LLM API reachable
  - Structured JSON logging (`tracing-subscriber` with JSON format)
  - Optional: Prometheus metrics endpoint

- [ ] **5.4** CI / CD
  - GitHub Actions: `cargo test`, `cargo clippy`, `cargo build --release`
  - Tailwind CSS compilation check
  - SQLx prepare check (`cargo sqlx prepare --check`)

**Gate:** `./careerhelper` starts and serves the app behind nginx with HTTPS

---

## Phase 6 — Future Ideas

- [ ] **6.1** Multi-user support with lightweight auth (API keys, not passwords)
- [ ] **6.2** ATS score simulation: show a "match score" before downloading
- [ ] **6.3** Cover letter generation using the same LLM pipeline
- [ ] **6.4** Job board integration: paste a job listing URL instead of raw text
- [ ] **6.5** Interview question generation based on the tailored resume
- [ ] **6.6** Desktop app via Tauri (offline-first, no browser needed)

---

## Quick Start (when ready to build)

```bash
# 1. Scaffold
cargo init careerhelper-web --name careerhelper
cd careerhelper-web

# 2. Dependencies (add to Cargo.toml)
cargo add axum tokio sqlx askama serde serde_json reqwest \
  tower-http tracing tracing-subscriber uuid chrono dotenvy

# 3. Tailwind
curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
chmod +x tailwindcss-macos-arm64

# 4. Run
cargo run
```

---

*See [project_context.md](project_context.md) for architecture, design, and tech stack rationale.*
*See [README.md](../README.md) for the current Python pipeline.*
