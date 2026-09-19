# Project Context — CareerHelper

> Architecture, design principles, and technology decisions for the CareerHelper
> web application. This document describes the future state — a Rust-powered
> web frontend wrapping the existing Python/LaTeX pipeline.

---

## 1. Vision

A clean, minimal web application where users upload their resume once, define
multiple role-specific templates, and generate ATS-optimized PDFs for any job
in seconds. No accounts. No clutter. Paste a JD, get a PDF.

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                      Browser                              │
│  ┌────────────────────────────────────────────────────┐  │
│  │         Frontend (HTMX + Tailwind CSS)              │  │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │  │
│  │  │ Template │ │  Resume  │ │  Generate &        │  │  │
│  │  │ Manager  │ │  Upload  │ │  Download          │  │  │
│  │  └──────────┘ └──────────┘ └───────────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP (JSON + HTML partials)
┌──────────────────────▼───────────────────────────────────┐
│                  Rust Backend (Axum)                       │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  API Layer                                           │ │
│  │  POST   /api/upload          Upload & parse resume   │ │
│  │  GET    /api/templates       List user templates     │ │
│  │  POST   /api/templates       Create template         │ │
│  │  PUT    /api/templates/:id   Update template         │ │
│  │  DELETE /api/templates/:id   Delete template         │ │
│  │  POST   /api/tailor          JD → tailored .tex      │ │
│  │  POST   /api/compile         .tex → PDF              │ │
│  │  GET    /api/download/:id    Serve PDF               │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Services                                             │ │
│  │  ┌──────────────┐  ┌──────────────┐                  │ │
│  │  │ DocParser     │  │ LaTeXEngine  │                  │ │
│  │  │ (pdf,docx,md) │  │ (tex → pdf)  │                  │ │
│  │  └──────────────┘  └──────────────┘                  │ │
│  │  ┌──────────────┐  ┌──────────────┐                  │ │
│  │  │ LLMClient     │  │ TemplateStore│                  │ │
│  │  │ (OpenAI API)  │  │ (SQLite)     │                  │ │
│  │  └──────────────┘  └──────────────┘                  │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  External Dependencies                                │ │
│  │  • pdflatex / xelatex  (system binary)               │ │
│  │  • Kimi K3             (OpenCode Go API)             │ │
│  │  • pandoc              (optional, for MD/HTML→LaTeX) │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## 3. Technology Stack

### Recommended: Rust backend + HTMX frontend

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend framework** | [Axum](https://github.com/tokio-rs/axum) 0.8+ | Fast, ergonomic, tower-based middleware, excellent async support |
| **Frontend** | [HTMX](https://htmx.org/) 2.0 + [Tailwind CSS](https://tailwindcss.com/) 4 | Minimal JS, server-rendered HTML, no build step, progressive enhancement |
| **Templating** | [Askama](https://github.com/djc/askama) | Type-safe Jinja2-style templates, compile-time checked |
| **Database** | [SQLite](https://github.com/launchbadge/sqlx) via SQLx | Zero-config, single-file, plenty fast for single-user workloads |
| **PDF parsing** | [lopdf](https://github.com/J-F-Liu/lopdf) + `pdf-extract` | Pure Rust PDF text extraction |
| **DOCX parsing** | [docx-rs](https://github.com/bheisler/docx-rs) or shell out to `pandoc` | Rust-native or battle-tested |
| **LaTeX compilation** | `std::process::Command` → `pdflatex` | Simple, reliable, no Rust crate needed |
| **LLM client** | [reqwest](https://github.com/seanmonstar/reqwest) + `serde_json` | OpenAI-compatible API is just HTTP + JSON |
| **Asset bundling** | Tailwind standalone CLI | No node_modules, no npm, single binary |

### Why this stack

- **Rust on the backend** makes sense here because document parsing (especially
  PDF and DOCX) is CPU-bound work where Rust's performance and safety shine.
  LaTeX compilation is a syscall — Rust handles subprocess management cleanly.
  LLM API calls are I/O-bound — Tokio's async runtime is purpose-built for this.

- **HTMX instead of React/Vue/Svelte** because this app has very little
  client-side state. Most interactions are form submissions or file uploads.
  HTMX gives us partial page updates without a JavaScript build pipeline.
  The result is a faster dev cycle and a smaller, simpler codebase.

- **Tailwind CSS standalone CLI** because it produces a single minified CSS
  file with zero npm dependencies. The light blueish theme is trivially
  expressed in Tailwind's utility classes.

- **SQLite via SQLx** because there's no need for a client-server database.
  The app serves one user at a time. SQLite is embedded, ACID-compliant,
  and the SQLx compile-time query checking catches bugs before runtime.

### Alternative stacks worth considering

| Stack | Best for | Trade-off |
|-------|----------|-----------|
| **Tauri + Svelte** | Desktop app, offline-first | Tauri is desktop-focused; web deployment is secondary |
| **Next.js + API routes** | Fastest to prototype, largest ecosystem | Slower document processing, heavier deployment |
| **Go + Templ + HTMX** | Simpler than Rust, still fast | Less type safety, weaker document parsing libraries |
| **Python FastAPI + Jinja2** | Reuse existing Python pipeline directly | Slower, GIL-bound for parsing, heavier deployment |

## 4. Design Principles

### Visual language

```
Theme:       Light blueish — calm, professional, minimal
Primary:     #3B82F6  (blue-500)      — buttons, links, accents
Primary bg:  #EFF6FF  (blue-50)       — cards, panels, selected states
Surface:     #FFFFFF  (white)          — page background
Text:        #1E293B  (slate-800)      — body text
Muted:       #64748B  (slate-500)      — secondary text, placeholders
Success:     #10B981  (emerald-500)    — completion states
Border:      #E2E8F0  (slate-200)      — dividers, input borders
```

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  [Logo]  CareerHelper                 [Templates] [New] │  ← Navbar: white bg, subtle bottom border
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  📄  Paste job description                       │   │  ← Main card: blue-50 bg, rounded-xl
│  │  ┌─────────────────────────────────────────────┐│   │
│  │  │                                             ││   │  ← Textarea: white bg, border-slate-200
│  │  │  We are looking for a Senior PM to lead...  ││   │
│  │  │                                             ││   │
│  │  └─────────────────────────────────────────────┘│   │
│  │  Company: [________]  Role: [________]           │   │
│  │  Template: [▼ Program Manager    ]               │   │
│  │  [  Generate Resume  ]                           │   │  ← Button: blue-500, hover: blue-600
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  ✅  Resume generated                            │   │  ← Result card: emerald-50 bg
│  │  Stripe — Technical Program Manager              │   │
│  │  [  Download PDF  ]  [  Preview  ]               │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### UX principles

- **Zero friction**: landing page IS the JD paste area. No signup. No navigation
  required to perform the core action.
- **Progressive disclosure**: template management lives behind a drawer or
  secondary page — it's not the first thing you see.
- **Instant feedback**: the "Generate" button shows a loading spinner with
  a live status line ("Extracting keywords…", "Tailoring bullet points…",
  "Compiling PDF…").
- **Optimistic UI**: the download button appears immediately after generation
  completes — no page refresh needed (HTMX swap).

## 5. Data Model

```
┌──────────────┐       ┌──────────────────┐
│   template   │       │  template_version  │
├──────────────┤       ├──────────────────┤
│ id (PK)      │──┐    │ id (PK)          │
│ name         │  │    │ template_id (FK) │──┐
│ description  │  │    │ latex_content    │  │
│ created_at   │  │    │ created_at       │  │
│ updated_at   │  │    │ is_active        │  │
└──────────────┘  │    └──────────────────┘  │
                  │                           │
                  └───────────────────────────┘
                        one-to-many

┌──────────────┐
│  generation   │
├──────────────┤
│ id (PK)      │
│ template_id  │──→ template_version
│ company      │
│ role         │
│ jd_text      │     (job description pasted by user)
│ llm_prompt   │     (full prompt sent to LLM)
│ llm_response │     (raw LLM output)
│ tex_content  │     (final .tex after tailoring)
│ pdf_path     │     (relative path in resources/output/)
│ token_usage  │     (JSON: prompt_tokens, completion_tokens)
│ created_at   │
└──────────────┘
```

## 6. Key Flows

### Flow 1: First-time setup

```
User visits / → uploads existing resume (PDF/DOCX)
  → backend parses the document, extracts structured content
  → content is rendered into the base LaTeX template
  → user reviews and saves as "Default" template
  → user can create variants (e.g., "PM focus", "Engineering focus")
```

### Flow 2: Generate tailored resume

```
User visits / → pastes job description
  → selects Company, Role, and Template variant
  → clicks "Generate"
  → backend:
      1. Loads the selected template's LaTeX content
      2. Constructs the ATS-optimization prompt (JD + template)
      3. Calls Kimi K3 through the OpenCode Go API
      4. Extracts the tailored .tex from the LLM response
      5. Writes .tex to resources/workspace/
      6. Calls pdflatex → produces PDF
      7. Copies PDF to resources/output/ with company_role_date filename
      8. Records generation in SQLite
  → frontend shows download button + preview
```

### Flow 3: Template management

```
User clicks "Templates" in navbar
  → sees list of templates with names, descriptions, last used date
  → can: create new, duplicate, edit (opens LaTeX editor), delete, set active
  → editing saves as a new version (version history preserved)
```

## 7. Rust Crate Map

```
careerhelper/
├── Cargo.toml
├── src/
│   ├── main.rs              # Axum server bootstrap, router setup
│   ├── routes/
│   │   ├── mod.rs
│   │   ├── pages.rs         # GET /, GET /templates (HTMX partials)
│   │   ├── upload.rs        # POST /api/upload
│   │   ├── templates.rs     # CRUD /api/templates
│   │   └── generate.rs      # POST /api/tailor, POST /api/compile
│   ├── services/
│   │   ├── mod.rs
│   │   ├── parser.rs        # Document parsing (PDF, DOCX, MD, HTML)
│   │   ├── latex.rs         # LaTeX compilation (pdflatex subprocess)
│   │   ├── llm.rs           # OpenAI-compatible API client
│   │   └── template.rs      # Template CRUD business logic
│   ├── models/
│   │   ├── mod.rs
│   │   ├── template.rs      # Template, TemplateVersion structs
│   │   └── generation.rs    # Generation record struct
│   ├── db.rs                # SQLx queries, migrations
│   └── config.rs            # Env vars, file paths, constants
├── templates/               # Askama templates (HTML)
│   ├── base.html            # Layout shell
│   ├── index.html           # Landing page (JD paste area)
│   ├── templates.html       # Template list
│   └── components/          # Reusable HTMX partials
│       ├── generate_result.html
│       └── template_card.html
├── static/
│   └── tailwind.css         # Compiled Tailwind output
├── migrations/              # SQLx migration files
└── tailwind.config.js       # Tailwind configuration (theme colors)
```

### Key dependencies (`Cargo.toml`)

```toml
[dependencies]
axum = "0.8"
tokio = { version = "1", features = ["full"] }
sqlx = { version = "0.8", features = ["sqlite", "runtime-tokio", "migrate"] }
askama = "0.12"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
reqwest = { version = "0.12", features = ["json"] }
tower-http = { version = "0.6", features = ["fs", "cors"] }
tracing = "0.1"
tracing-subscriber = "0.3"
uuid = { version = "1", features = ["v4"] }
chrono = { version = "0.4", features = ["serde"] }
dotenvy = "0.15"
```

## 8. Deployment

### Development

```bash
# Terminal 1: Rust backend with hot-reload
cargo watch -x run

# Terminal 2: Tailwind CSS watcher
npx @tailwindcss/cli -i ./input.css -o ./static/tailwind.css --watch
```

### Production

```bash
# Single-binary deployment
cargo build --release
./target/release/careerhelper

# The binary embeds SQLite, Askama templates (compile-time),
# and serves static files. Only external dependencies are:
#   - pdflatex on the system PATH
#   - .env file with API keys
```

Recommended: deploy behind `nginx` or `caddy` for TLS termination. The Rust
binary listens on `127.0.0.1:3000`.

---

## See also

- [README.md](../README.md) — current Python pipeline, setup, and CLI reference
- [Project Checklist](project_checklist.md) — phased implementation roadmap
- [scripts/tailor_resume.py](../scripts/tailor_resume.py) — the ATS-optimized LLM prompt
- [resources/templates/latex/](../resources/templates/latex/) — local canonical LaTeX resume template

*Last updated: 2026-08-09*
