# Job Search — Learnings from career-ops and JustHireMe

**Status:** research notes for CareerHelper's job-discovery subsystem. Read-only survey of the two cloned
reference projects; nothing was modified in either.
**Scope:** discovering, normalizing, deduplicating, filtering, scoring, and tracking job postings.
**Explicitly out of scope:** resume tailoring, cover letters, LaTeX/PDF generation, interview prep, and
outreach. Both reference projects contain a lot of that machinery; this document deliberately ignores it,
except where it has a direct bearing on the posting data model.

Sources surveyed:

- `inspiration/career-ops` — Node ESM, MIT, v1.33.0. An agent-skill library that ships with a flat Node toolkit.
- `inspiration/JustHireMe` — Python backend (FastAPI) + Tauri/React shell. A standalone desktop job-search app.

---

## 0. How to read this document

Every claim carries a `path:line` anchor, relative to its project root (`inspiration/career-ops/` or
`inspiration/JustHireMe/`).

Provenance is marked, because not everything was verified to the same depth:

- **No marker** — verified by direct read during this investigation. Line numbers were read, not inferred.
- **⚠ unverified** — came from a sub-investigation's self-report and was not independently re-read. Treat
  the anchor as "roughly here" and spot-check before porting.
- **⚠ uncertain** — the source itself is ambiguous, or the claim could not be resolved at all.

The high-value anchors — the provider contract, the filter chain, the dedup keys, the scoring branches —
are all in the unmarked category, so the core of this document is solid.

---

## 1. The two projects in one paragraph each

**career-ops** is an *agent-skill library* first and a script collection second. The product logic lives in
Markdown prompt files under `modes/` that any AI coding CLI can execute; the ~128 Node scripts at the repo
root are tools the agent calls. `ARCHITECTURE.md:5-11` states the intent plainly: "AI-agnostic. The logic
lives in Markdown prompt files under `modes/`, executed by whatever AI coding CLI you use… No single model is
hardcoded." Its job-discovery engine is `scan.mjs` (3,637 lines) plus ~89 provider modules under
`providers/`, and — importantly for us — that engine is **zero-token**: it uses no LLM and no API key at all.
`modes/scan.md:3-5` says so directly: "the default scanner (`scan.mjs` / `npm run scan`) is zero-token."
The LLM is reserved for the *evaluation* stage, which is a separate, agent-driven mode. Runtime dependencies
are only `@google/generative-ai`, `dotenv`, `js-yaml`, and `playwright 1.63.0`; the root `package.json` is
`"private": true` with no `bin` or `main`, while a separate `scaffolder/package.json` publishes the installer
CLI as `@santifer/career-ops`. Its doctrine: *files are canonical, databases are derived* — `ARCHITECTURE.md:22-24`
insists SQLite "will never become a primary store — not even opt-in," because the web UI, a Go TUI dashboard,
community plugins, and thousands of forks all read the Markdown files.

**JustHireMe** is a conventional application: a FastAPI backend, SQLite storage, a Playwright browser
automation layer, and a Tauri/React desktop shell. Discovery is a server-side pipeline triggered by
`POST /api/v1/scan` (`backend/api/routers/discovery.py:550` ⚠ unverified), which runs keyless public job
sources first, then optionally generates profile-tailored queries with an LLM, then sweeps job boards in
batches, then ranks the results. Unlike career-ops, its job-discovery path **does** spend LLM tokens, and its
frontier feature is a deterministic-first scoring engine with a bounded LLM refinement layer that cannot
raise its own hard caps (`backend/ranking/scoring_engine.py:1-11`). It stores everything in one `leads`
table in SQLite.

---

## 2. career-ops — the job search subsystem

### 2.1 The architectural split that matters most

career-ops separates **discovery** (machine, deterministic, zero-token, no auth) from **curation** (agent,
LLM-driven, judgment-heavy). Discovery is `scan.mjs` and the provider modules. Curation is the
`modes/*.md` prompt files: `modes/pipeline.md` walks a human-or-agent through liveness-checking the inbox,
then `modes/auto-pipeline.md` runs JD extraction → liveness gate → blacklist gate → evaluation → report →
CV. The scanner **never** writes to the tracker (`data/applications.md`). It writes to a checkbox inbox
(`data/pipeline.md`) and is done.

That boundary is the single most transferable idea in the project, and it is worth copying deliberately
rather than by accident. It means the expensive, nondeterministic, judgment-bearing part is isolated from
the cheap, testable, reproducible part.

### 2.2 End-to-end flow of `scan.mjs`

`npm run scan` (and the variants `scan:full`, `scan:seeds`, `scan:yc`, `scan:hn`, `scan:interamt`) all
converge on the same ten stages. `main()` begins at `scan.mjs:2834`.

1. **Filter construction** (`scan.mjs:2960-2967`) — builds `titleFilter`, `locationFilter`,
   `postingAgeFilter`, `postedDateFilter`, `salaryFilter`, `trustValidator`, `contentFilter`,
   `countryEligibilityFilter`, and `visaFilter` from `portals.yml`. Also computes an early-stop hint from
   `max_posting_age_days`.
2. **Provider resolution** (`scan.mjs:2984-3043`) — `resolveEntries()` walks the `companies` list, then the
   `boards` list. Entries that are `enabled: false`, blank-named, or have no matching provider are skipped.
   Entries flagged `scan_method: websearch` are not scanned at all; they are pushed onto an `agentHandoff`
   list for the agent to handle later.
3. **Blacklist load** (`scan.mjs:3095`, `loadBlacklist` at `:2511`) — reads `data/blacklist.md`.
4. **Dedup snapshot load** (`scan.mjs:3097-3102` → `loadDedupSnapshot` at `:2355-2371`) — one read of three
   files (`scan-history.tsv`, `pipeline.md`, `applications.md`) derives three lookup structures: `seen`
   (normalized URLs), `seenCompanyRoles` / `seenCompanyRoleBases`, and `fingerprintHistory`.
5. **Concurrent fan-out** (`scan.mjs:3297`) — `parallelFetch(tasks, CONCURRENCY)` with `CONCURRENCY = 10`
   (`scan.mjs:122`). Each target calls `provider.fetch(company, ctx)` at `scan.mjs:3117` with
   `ctx = {...makeHttpCtx(), sinceMs, includeUndated: true, locationHints}`.
6. **The filter chain**, in a fixed order, per job (`scan.mjs:3155-3205`) — see §2.5.
7. **Optional liveness verification** (`scan.mjs:3300-3318`, stage "5.5") — only with `--verify`. Launches
   Playwright and sorts results into `verified / expired / dropped / invalid / migrated`. Migrated offers
   re-enter the pipeline at their new URL.
8. **Cross-listing check** (stage "5.7", `scan.mjs:3320-3331`) — computes a SimHash fingerprint per offer
   and warns on near-duplicates against `fingerprintHistory`. **Warn-only; nothing is dropped.**
9. **Writes** (stage "6", `scan.mjs:3333-3385`) — surviving offers append to both `data/pipeline.md` and
   `data/scan-history.tsv`. Offers rejected for cooldown/expiry/other reasons go to `scan-history.tsv` only,
   with distinct status strings.
10. **Summary** (stage "7", `scan.mjs:3387-3440`) — prints counters and appends a row to
    `data/scan-runs.tsv` via `appendScanRunSummary()` (`scan.mjs:2557`).

### 2.3 The provider contract

The contract is small and worth copying almost verbatim. It is defined in JSDoc-only form in
`providers/_types.js`, with the note that "the runtime contract is enforced by scan.mjs (id presence, fetch
is a function, fetch returns an array)" (`providers/_types.js:4-6`).

A provider declares four things (`providers/_types.js:163-178`):

- **`id: string`** — required, unique.
- **`detect?(entry) → DetectHit | null`** — optional. Auto-detects that a config entry belongs to this provider.
- **`fetch(entry, ctx) → Promise<Job[]>`** — required. Returns a normalized array.
- **`dedupKey?(job) → string | null`** — optional. Provider-scoped refinement of the dedup key, for boards
  whose own identifier is more stable than the URL.

The `Context` the scanner hands in (`providers/_types.js:127-158`) is deliberately narrow:

- `transport: 'http'`
- `fetchText(url, opts)`, `fetchJson(url, opts)`, `fetchResponse(url, opts)`
- `maxPages?` — a hint, used by health probes
- `sleep?(ms)`

Provider-specific config fields are explicitly **opaque to `scan.mjs`** — `PortalEntry` only names `name`,
`enabled?`, `careers_url?`, `api?`, `provider?`, `transport?`, `max_pages?`, `offset_param?`
(`providers/_types.js:81-101`). Anything else is the provider's business.

**Registry and resolution** (`providers/_registry.mjs:23-59`, `:76-107`): `loadProviders(dir)` reads the
directory, keeps files ending `.mjs` that are not `_`-prefixed, sorts them alphabetically, and imports each.
An import error, a missing `{id, fetch}`, or a duplicate `id` produces a **warning and a skip** — never a
crash. Resolution order in `resolveProvider()` is: an explicit `provider:` field on the entry wins; then a
local parser; then `detect()` run in **load order, first hit wins**.

Providers on disk: 99 `*.mjs` files under `providers/`, of which 10 are `_`-prefixed shared infrastructure —
so roughly **89 real providers**. Notables: `greenhouse.mjs`, `lever.mjs`, `ashby.mjs`, `workday.mjs`,
`remoteok.mjs`, `workingnomads.mjs`, `builtin.mjs`.

### 2.4 The normalized record

The `Job` type (`providers/_types.js:21-69`) is deliberately minimal — eight fields:

- **`title`** — string
- **`url`** — string, required; this is the dedup key
- **`company`** — string
- **`location`** — string
- **`description`** — optional, populated *only when the list payload returns it for free*
- **`postedAt`** — optional
- **`salary`** — optional object `{min?, max?, currency?}`, annualized, never inferred
- **`trustScore` / `trustFlags` / `trustLevel`** — optional trust enrichment

Two design decisions here are load-bearing, and both cut against intuition:

**The `description` "free or absent" rule keeps the scanner zero-token.** Providers do not fetch a detail
page to obtain the full description. If a listing endpoint happens to include the body, it is used; if not,
`description` is simply absent. That is the entire reason a full scan costs no money. Anything that needs
the full body (evaluation, similarity, skill-gap) runs later and separately.

**The record has no `seniority`, no `tags`, and no `remote` boolean.** Remoteness is free text folded into
`location`. This is the model's biggest weakness (see §6), and it is a warning, not a template.

An important supporting convention, repeated in every filter's docstring: **`undefined` is not empty
string, and a missing value always passes the filter.** A posting with no salary is not a posting with a
bad salary. This is the "don't penalize missing data" rule, and it is what keeps filters from silently
deleting whole boards whose payloads omit a field.

### 2.5 The filter chain

This is the ordering, verified directly at `scan.mjs:3155-3205`. Each step either passes the job through or
rejects it with a distinct, counted reason.

1. **Blacklist** — company/domain exclusions from `data/blacklist.md`.
2. **Title filter** — keyword include/exclude against the posting title.
3. **Tier filter** — `classifyTier()` decides a tier, and `skipTiers` drops unwanted ones. Note:
   `classifyTier` defaults to `mid` when it cannot tell (`classify-tier.mjs`), which is a deliberate
   "don't drop what you don't understand" choice.
4. **`locationFilter(location, url, title)`** — note that it receives *three* arguments. The URL and title are
   passed because location signal often has to be recovered from them when the location field is junk.
5. **`postingAgeFilter(postedAt)`** — age ceiling, honoring `max_posting_age_days`.
6. **`postedDateFilter`** — explicit `--posted-after` / `--posted-before` window.
7. **`salaryFilter(salary)`** — compares against a configured band.
8. **`contentFilter(description, matchedTitleKeywords(...))`** — positive/negative keyword matching scoped by
   title keyword, so a negative term only vetoes within the role family it applies to.
9. **`countryEligibilityFilter`** — country-eligibility rules.
10. **`visaFilter`** — visa-sponsorship rules.
11. **URL dedup** — against `seen`, keyed by `normalizeUrlForDedup`.
12. **Company+role dedup** — against `seenCompanyRoles` / `seenCompanyRoleBases`, keyed by
    `companyRoleDedupKey`.
13. **Cooldown filter** — re-surfacing rules driven by `scan_history.recheck_after_days`.

The ordering principle is worth naming: **cheap, local, and certain checks run first; expensive and
heuristic checks run last.** Nothing in the chain does I/O.

### 2.6 Deduplication — three keys, deliberately asymmetrical

career-ops uses three separate identity systems, at increasing fuzziness.

**Key 1 — normalized URL** (`scan.mjs:1325-1340`, `normalizeUrlForDedup`). It strips a narrow, explicitly
enumerated set of cosmetic query params (`scan.mjs:1285-1297`):

```
language, lang, locale,
utm_source, utm_medium, utm_campaign, utm_term, utm_content,
ref, src, source, gh_src, lever-origin, lever-source,
rltr   // StepStone: regenerated per request, so one posting returns as new every scan
```

The comment is explicit that this is a **deliberately narrow strip-set, not a blanket strip**, because
several ATSes key the posting off a query param — Greenhouse's `gh_jid` being the named example — so a
blanket strip would collapse distinct roles into one. It then promotes recognized hash-route job IDs,
drops the fragment, drops a trailing slash, and lowercases scheme/host/path. It **keeps query-value casing**,
again because `gh_jid` values are identity-bearing. The path is lowercased because `scan.mjs` and
`scan-ats-full.mjs` are separate processes that can independently produce different casing for the same
Workday posting, which would otherwise land the role in `pipeline.md` twice.

**Key 2 — canonical company + role** (`scan.mjs:1984-1991`). Returns:

```
`${canonicalize(company)}::${normalizeRoleForDedup(role)}`    // plus `@@${places}` when a location is given
```

The separator choice is documented: `@@` rather than a third `::`, because `normalizeTextKey` strips
punctuation, so neither the role nor the location component can contain the separator — meaning a company
alias carrying one cannot forge a "located" key out of a bare one. There is also a *base* form
(`seenCompanyRoleBases`) so a role seen without location still suppresses the same role seen later with a
location.

**Key 3 — SimHash fingerprint of the JD body** (`fingerprint-core.mjs:1-35`). 64-bit SimHash over 3-token
shingles, stored as 16 hex characters per row. Constants: `FINGERPRINT_MIN_TEXT = 200`,
`CROSSLIST_THRESHOLD = 0.92` (roughly ≤5 of 64 bits differ), `CROSSLIST_WINDOW_DAYS = 90`. The doctrine is
"no body, no signal, no false positives" — because the scanner usually has no body (see the free-or-absent
rule), this fires rarely. **This key is warn-only.** It never drops anything.

The governing doctrine for Key 1 lives in `url-key.mjs:1-34` and is the most quotable paragraph in either
project. It is titled **"UNDER-STRIP ON PURPOSE"** and reasons explicitly about the asymmetry of failure:

- Over-normalizing produces a *silent merge* — two distinct postings become one row, and data is lost with
  no signal.
- Under-normalizing produces a *visible duplicate* — which a human will notice and can fix.

Therefore the code prefers duplicates over merges, walks an RFC 3986 §6 normalization ladder one rung at a
time, and — the sharpest rule — **"NO KEY IS NOT A KEY"**: when a URL cannot be normalized, it returns the
empty string `''` rather than a lowercase stand-in. The reason given is SQL three-valued logic plus a
recorded bug where every `N/A` row shared one key and collapsed together.

`url-key.mjs` and `fingerprint-core.mjs` also form the tracker-side identity system, which is separate from
the scan-side three keys above. **Two overlapping identity systems exist by design** — worth deciding
deliberately rather than inheriting.

### 2.7 Liveness verification

Liveness is a four-layer ladder, each layer cheaper and noisier than the next:

- **`liveness-core.mjs`** (241 lines) — the pure classifier. No network. Takes a status code plus a body and
  returns a verdict.
- **`liveness-api.mjs`** — zero-token ATS public API probes, for the four ATSes whose public JSON endpoints
  return posting *status*: `JD_TEXT_API_ATS = new Set(['greenhouse','lever','ashby','workday'])`
  (`liveness-api.mjs:330-340`). Microsoft and LinkedIn are explicitly excluded because their endpoints
  "answer search/status, never body text."
- **`liveness-browser.mjs`** — Playwright, for everything else.
- **`check-liveness.mjs`** — the CLI.

Two operating rules: it runs **sequentially, never Playwright in parallel** (`check-liveness.mjs:85`), and it
escalates **lazily — API first, browser only on miss** (`:87-101`).

The classifier's decision order (`liveness-core.mjs:150`) is: 404/410 → expired; bot challenge → uncertain;
403/429/503 → uncertain/`access_blocked`; ≥500 → uncertain; explicit `error=true` → expired;
`HARD_EXPIRED_PATTERNS`; **a lost job-ID token on redirect → uncertain**; then — and this is the interesting
one — **`hasApplyControl()` → active**; only then `SOFT_EXPIRED_PATTERNS`; then listing-page detection;
then `< 300 chars` of content → expired (`MIN_CONTENT_CHARS = 300`); then fallthrough → uncertain.

That ordering means **positive evidence of an apply button outranks soft textual hints of expiry.** An
expired-looking phrase is not enough if the page still offers an apply control.

The doctrine that governs the whole layer is written down at `liveness-core.mjs:120-124` and called the
**asymmetric-error doctrine**: a *false* `expired` verdict is written to the ledger as `skipped_expired` and
then dedup-filters a genuinely live job out of *every subsequent scan, indefinitely* — unless
`scan_history.recheck_after_days` eventually releases it. A false `active` costs one wasted Playwright page
load. Because the errors are not symmetric, every uncertain case resolves to `uncertain`, never to `expired`.

Two provider-specific quirks are modeled in the provider rather than the framework, and both are recorded
with the bug that motivated them:

- **Ashby**: the browser rung *false-reports live postings as expired* because Ashby renders client-side.
  The API rung is authoritative (`liveness-api.mjs:110-113`).
- **Lever**: `api404Authoritative: false`, with a dated repro comment (`liveness-api.mjs:82-95`).

And the LinkedIn classifier (`liveness-api.mjs:216-241` ⚠ unverified line range) requires **two-signal
agreement** before concluding anything; disagreement returns `uncertain`. It also throttles at
`throttleMs: 3_500`.

Finally, the classifier is honest about its own fragility: `HARD_EXPIRED_PATTERNS` has 20+ entries and each
one carries a comment naming the issue number and the false positive or negative it was added to fix
(#4175, #4194, #3498). `APPLY_PATTERNS` carries per-language notes, including Polish `aplikuj` and Chinese
MokaHR/Feishu `^申请职位$` / `^投递$`, annotated "keep them narrow" (`liveness-core.mjs:115-155`).

### 2.8 JD capture — four mechanisms

1. **ATS public JSON API** (cheapest). `fetch-jd.mjs` is the shell-callable front door
   (`TEXT_CAP = 20_000`, `TIMEOUT_MS = 15_000`), and it is designed to emit **no stderr** — a miss is
   `process.exit(1)` with empty stdout, because the caller's browser fallback *is* the next step.
   Everything routes through one dispatch function, `fetchJdViaKnownApi()`
   (`browser-extract.mjs:586-598`), which is deliberately shared by the CLI `jd` mode and `fetch-jd.mjs`
   "so the interactive and headless paths cannot drift." A router table, `JD_FETCHERS`
   (`browser-extract.mjs:561-573`), maps each ATS to a uniform
   `(resolved, url, textCap, timeoutMs)` signature.
2. **Headless Playwright DOM read** (`browser-extract.mjs`). API first (`:827-834`), browser second,
   `navigation_error` exit 1 last. Constants: `JD_TEXT_CAP = 12_000`, `MIN_JD_TEXT_CHARS = 200`,
   `HYDRATION_WAIT_MS = 2_000`, `DEFAULT_TIMEOUT_MS = 15_000`. Every request is SSRF-checked via
   `rejectPrivateOrInvalid`, and the **final** URL is re-checked after redirects ("belt-and-suspenders").
3. **The agent's own fetch tools**, described in `modes/triage.md:35-52` as a ladder: PDF URL → use the Read
   tool directly, explicitly *not* WebFetch ("WebFetch can't extract PDF text, which would wrongly mark a
   live PDF posting `SKIP`"); `local:` prefix → read the local file; otherwise WebFetch, and "If WebFetch
   returns no real JD content … **and** a Playwright/browser tool is available, retry once with it before
   concluding the posting is dead." That last clause carries an empirical note: "measured on a real batch
   run, most of that gap turned out to be exactly this, not actually-dead postings."
4. **Manual paste / archive** (`jd-capture.mjs`) — resolves a prior capture in `jds/` by report number.
   Notably it returns `null` rather than another company's file when the slug does not match, and the
   header documents the cost of getting that wrong: `outcome.mjs` would copy the wrong JD in as the
   permanent record and, counting the lookup as a success, never archive the real one (`jd-capture.mjs:100-106`).

Normalization has two functions that look similar and are deliberately different:

- `jdHtmlToText()` (`browser-extract.mjs:186-209`) preserves paragraph and bullet structure and does a
  **double entity-decode**, which is load-bearing because payloads often carry entity-escaped markup
  (`&lt;p&gt;`). It is explicitly *not* the scan-path `htmlToText` (`providers/_html-to-text.mjs`), which
  hard-caps at 4,000 chars and collapses *all* whitespace including newlines — fine for scan payloads,
  useless for a JD you intend to read.
- `normalizeJd()` (`browser-extract.mjs:114-141`) reconciles schema.org `JobPosting` JSON-LD against the
  rendered DOM and takes the **longer after whitespace normalization**. Justification: Phenom boards
  (e.g. careers.roche.com) render a `<main>` containing ~300 chars of title/location/Apply chrome while the
  real body never becomes visible text. Comparing pre-collapse lengths would defeat the point.

Mode is config, not code: `resolveExtractorMode()` (`browser-extract.mjs:92-101`) reads
`config/profile.yml → scan.extractor`, accepting `'cli'` or `'mcp'`, defaulting to `mcp` on anything
unrecognized.

### 2.9 Configuration surface

`templates/portals.example.yml` is **2,792 lines** of mostly commented per-provider stanzas. A company
entry can be integrated at one of four levels:

- **Level 0** — local parser (zero-token)
- **Level 1** — Playwright
- **Level 2** — per-company `api:` JSON endpoint
- **Level 3** — WebSearch (handed off to the agent)

Named config keys include `max_posting_age_days`, `location_filter` (with `always_allow` beating `block`,
plus a separate `block_hard`), `country_eligibility_filter`, `salary_filter`, `trust_filter`,
`content_filter` (`positive`/`negative`, scoped by `by_title_keyword`), `visa_filter`, and under
`scan_history`: `recheck_after_days` and `dedup_include_location` (default `false`).

The honest assessment: this is powerful and the mental model required to add a company is *"which of five
integration styles, and does its host auto-detect?"* That is a steep entry cost, and it is the main reason
a smaller, stricter config format is attractive for CareerHelper.

### 2.10 Artifacts and the handoff

- `data/pipeline.md` — the checkbox inbox (`PIPELINE_PATH`, `scan.mjs:111`)
- `data/scan-history.tsv` — the dedup ledger, 12 positional columns, header written on create
  (`scan.mjs:2449`)
- `data/scan-runs.tsv` — one row per run with per-filter counters (`appendScanRunSummary`, `scan.mjs:2557`)
- `data/portal-health.tsv` — per-portal health records (`scan.mjs:2615`, `loadPortalHealth` at `:2627`)
- `data/blacklist.md` — user do-not-apply list, read-only to the scanner (`scan.mjs:2478`)
- `data/cache/ats-companies` — reverse-ATS company directory cache, 24 h TTL (`scan-ats-full.mjs:79-82`)

All four of `scan.mjs`'s I/O paths (portals, profile, scan-history, pipeline) are env-overridable, which is
how it supports "parallel search lanes" (`scan.mjs:104-111`; the comment cites issue #3510, where sibling
scanners had carried bare-relative copies of the same paths and drifted).

The handoff to a tracked application is **agent-driven, not scripted**: `modes/pipeline.md` runs a liveness
sweep over all pending `- [ ]` URLs, strikes out the dead ones as
`- [x] ~~URL | Company | Role~~ — posting expired (liveness sweep)`, and sends each survivor through
`modes/auto-pipeline.md` (JD extract → liveness gate → blacklist gate → A–G evaluation → report → CV/PDF),
finally landing a row in `data/applications.md`.

---

## 3. JustHireMe — the job search subsystem

### 3.1 End-to-end flow

The pipeline is orchestrated in `backend/api/routers/discovery.py` (scan endpoint at `:550` ⚠ unverified).
Verified order at `discovery.py:265-300`:

1. **Precondition gate.** It loads settings and a discovery profile, and refuses to scan without signal:
   *"Scan skipped: add a target role, profile skills, work history, or explicit job source first."*
   `has_profile_discovery_signal(profile)` OR `has_explicit_discovery_targets(cfg)`. Note this is a
   **fail-closed gate with an explicit escape hatch** — the escape hatch being explicit user-supplied targets.
2. **`run_x_signal_scan(...)`** — scans X/Twitter signals.
3. **`run_free_source_scan(...)`** — the keyless source backbone.
4. **Query generation** — `query_gen_start` → `discovery_service.plan_board_targets(profile, raw_urls, market_focus)`.
   It broadcasts progress, and crucially wraps it in `except Exception` with the fallback
   `urls = raw_urls` and the message *"Query generation failed ({exc}), using raw URLs"*. So an LLM failure
   degrades to a deterministic scan that still runs, and **logs loudly** rather than silently dropping
   every target.
5. **Batched board sweeps** — `batch_size = int_cfg(cfg, "board_scan_batch_size", 4, 1, 12)`, so the default
   is 4 with an enforced range.
6. **Read back** discovered leads (`data/sqlite/leads.py:851` ⚠ unverified, `status='discovered'`) and rank
   them.

`query_gen.py` **does** use an LLM: `llm.call_llm(system, user, _Plan, step="query_gen")` against a Pydantic
model `_Plan(BaseModel) { queries: list[str] }` (`query_gen.py:229-392` ⚠ unverified). The interesting
detail is what it *doesn't* send to the model: only `site:`-style domain queries go to the LLM; other
queries are **deterministically enriched** instead (remotive's `search=` param, jobicy's `tag=` param). That
is the same cheap-first instinct as career-ops, applied to a different problem.

### 3.2 Source layer and error conventions

The stated protocol is in `backend/discovery/sources/base.py` — 20 lines containing a
`RawLead(TypedDict, total=False)` and a `class Source(Protocol)` declaring `name: str` and
`async def fetch(queries, config) -> list[RawLead]`.

**Nothing implements it.** No source class subclasses or registers against this Protocol. This is a
capability model that exists as documentation only, which is why there is no pagination, rate-limit, or
auth declaration anywhere in the codebase. Worth knowing so you don't take the Protocol as evidence of a
working plugin system.

The conventions that *are* enforced, however, are good:

- **Every adapter returns `[]` on failure and never raises on a malformed item.** One bad posting cannot
  kill a source.
- **Per-source try/except accumulates error text** (`free_scout.py:369-377` ⚠ unverified).
- **`_source_error_detail` maps status codes to human strings** — 403 → "blocked by source", 429 → "rate
  limited by source" (`scout.py:93-107` ⚠ unverified). (It is duplicated in `free_scout.py:118-127`.)
- **Tenacity retry policy**: `stop_after_attempt(4)`, exponential backoff `min=2, max=30`, retrying only
  `HTTPStatusError / ConnectError / TimeoutException` (`sources/common.py:104-124` ⚠ unverified).
- **429 honors `Retry-After`** parsed as *either* delay-seconds *or* an HTTP-date, clamped to 1–300s
  (`sources/common.py:33-55` ⚠ unverified). Handling both formats is rarer than it should be.

The ATS dispatch lives in `backend/automation/free_scout.py:300-335` ⚠ unverified and is
string-prefix-based: `ats:greenhouse:`, `ats:lever:`, `ats:ashby:`, `ats:workable:` route to specific
handlers; a bare `ats:` falls through to a generic scrape; anything else goes to `_scrape_direct_ats_url`.
It is a smaller, flatter version of career-ops's provider registry.

### 3.3 Deduplication and storage

Substantially simpler than career-ops, and worth understanding as the "minimum viable" version.

`backend/discovery/lead_intel.py:70-118` (verified) holds:

- `_TRACKING_PARAMS` — a frozenset of 15 tracking params (`utm_*`, `gclid`, `fbclid`, `mc_cid`, `mc_eid`,
  `ref`, `ref_src`, `source`, `src`, `igshid`, `spm`, `campaign_id`).
- `canonical_url(url)` — lowercase host with `www.` stripped, default port dropped, **http == https**, no
  trailing slash, tracking params dropped, remaining params **sorted**.
- `canonical_lead_id(url)` — `hashlib.md5(canonical_url(url).encode()).hexdigest()[:16]`. A stable,
  source-independent 16-char id "so the same job discovered by two different scouts maps to one row."
- `clean_text(text)` — collapse whitespace.

The docstring notes the original `lead.url` is kept untouched "for actually opening/applying" — the same
separation of *comparison key* from *display value* that career-ops uses.

Storage is a single `leads` table with primary key `job_id`, written with `INSERT OR IGNORE`. Migrations
are numbered files: `001_initial.sql`, `002_add_signal_columns.sql`, `003_add_feedback_columns.sql`,
`004_resume_templates.sql`. A grep for `CREATE INDEX` across all four finds **exactly one**
(`004:13 idx_resume_templates_default`), which confirms there is **no secondary index on `leads`**.

**Dedup is URL-canonical only.** There is no company+title key and no body fingerprint. The same role posted
to three boards is three rows.

### 3.4 Quality gate

`backend/discovery/quality_gate.py:1-40` (verified) is small, explicit, and centralized:

- `MIN_DEFAULT_QUALITY = 60`, `HOT_LEAD_THRESHOLD = 80`
- `_RED_FLAGS` — 10 entries beginning `unpaid`, `for exposure`, `equity only`
- `_SENIOR_FLAGS`, `_BEGINNER_FLAGS`

The notable piece is a **fail-closed freshness gate with a "trusted recency" escape hatch**
(`quality_gate.py:79-116` ⚠ unverified line range): undated postings are dropped by default, but a source
can be marked trusted for recency to override. That is the same shape as the precondition gate in §3.1 —
closed by default, with a named, deliberate way through.

The known weakness: a 7-day freshness gate can silently drop entire date-less lanes.

### 3.5 Ranking and scoring — the standout subsystem

`backend/ranking/scoring_engine.py` is 873 lines and states its thesis in the module docstring
(`:1-11`): **"keeps the model out of the rating loop."**

**The core formula is a plain weighted mean** (`:620-622`):
`_weighted_total = Σ(score × weight) / (Σ weight or 1)`. No base score, no bonus term, no sigmoid. That
simplicity is the point — it is auditable.

**There are three scoring branches, selected by whether the posting has technical terms**
(`:804-860`, `score_job_lead`). The predicate is captured *before* a domain-generalization step mutates the
posting:

```python
tech_taxonomy_present = bool(posting.terms)   # captured BEFORE apply_domain_generalization
```

- **Non-software** — role 12, stack 8, proof 15, seniority 18, constraints 12, semantic 45
- **Software** — role 15, stack 20, proof 18, seniority 20, constraints 12, semantic 15
- **No-semantics** — role 18, stack 27, proof 20, seniority 20, constraints 15

The semantic weight swinging from 45 to 15 depending on role family is a real insight: for a non-software
role, keyword overlap with the stack is nearly worthless, so the embedding signal has to carry the score.

**Caps are conjunctive ceilings** (`_apply_caps`, `:655-680`), and this is the piece I would port first.
Each cap is an *upper bound on the final score*, the tightest wins via `min()`, and **every cap that fired
appends its reason to `result.gaps`** so the user can see exactly why a role was suppressed. The values:

- wrong field — **15**
- seniority mismatch — **30 / 38 / 45 / 48** depending on direction
- no direct stack — **52** (adjacent) or **42**
- thin posting — **68**

Caps are ordered by tightness, so the reported reason is the binding constraint, not an arbitrary one.

**Explainability is data, not prose.** `ScoreResult.criteria[]` is a list of
`{name, score, weight, reason}` records, and `applied_cap` is a first-class field. A UI can render the
breakdown without parsing text.

**The LLM refinement layer is bounded** (`ranking/evaluator.py`; `_hard_cap` at `:211-260` ⚠ unverified).
This is the single most transferable design in either project: the LLM may adjust a score, but
`_hard_cap` **re-imposes the wrong-field and seniority caps afterward**, so the model can never promote a
wrong-field role above 15 or a seniority-mismatched role above 48. Deterministic rubric first; LLM as
*refinement*, never as *authority*.

It is gated by `use_llm`, prefilters off-field postings with `_OFF_FIELD_SIM = 0.22` (default on), has an
opt-in `llm_eval_floor` (default off), and only evaluates the top 25 via `select_llm_eval_ids`. The result
records its provenance in `scored_by ∈ {deterministic, prefiltered_off_field, llm, deterministic_fallback}` —
so a score always says how it was produced.

**Semantic scoring** (`ranking/semantic.py`) is a three-tier embedding stack: local ONNX
`all-MiniLM-L6-v2` (384-d), OpenAI `text-embedding-3-small` (1536-d), and a hash fallback. Vectors live in
LanceDB. Group weights are 0.22 / 0.34 / 0.26 / 0.10 / 0.08, and the blend is **60% mean + 40% peak**
linearly stretched per provider. Empty profiles *disable* search rather than matching against stale
vectors. When reduced to hashing, it reports `"hashing"` with `degraded: True` rather than pretending.

**Feedback is hand-weighted heuristics, not a learned model.** Two persisted score channels recompute
idempotently from stored bases: `signal_score` ±18 via `feedback_ranker.py`, and `score` ±12 via
`feedback_semantic.py` (a Rocchio centroid). The weights are declared constants (platform 6, stack 5,
tag 3) with saturation at 5 observations.

**Evaluation is done properly.** Six JSONL case files run through the *production* function, asserting
score bands and whether a cap fired. Cases marked `invariant: true` are CI-failing guarantees, and
`ACCURACY_FLOOR = 1.0`. Honest gap: **there is no rank-order metric** — no nDCG, no precision@k. It tests
absolute bands, not ordering quality.

### 3.6 Browser automation and safety

The automation layer is five modules: `automation/scout.py` (583), `free_scout.py` (515), `x_scout.py` (511),
`actuator.py` (604), `browser_runtime.py` (150), plus `selectors.py` (91).

`selectors.py` is **remote-refreshable with a cache and a bundled fallback** — so a board's DOM change
cannot hard-fail the system; it degrades to the last known-good selector set.

Auto-submit is opt-in via `JHM_AUTO_APPLY`, centralized in `actuator._submit_mode` (`:249-271` ⚠ unverified),
behind a **default-deny `_safe_to_click`** hit-test (`:277-357` ⚠ unverified). SSRF is guarded on every
request via `core/url_guard.py` (`assert_public_url` / `block_private_route`) and
`sources/net.py:guarded_async_client`.

The safety pattern worth naming: **the decision is centralized in one unit-testable function, and the
default is deny.** Not a sprinkling of `if` checks at call sites.

---

## 4. Side-by-side, by concern

- **Discovery trigger**: career-ops — a CLI command you run (`npm run scan`). JustHireMe — an HTTP endpoint
  that runs a multi-stage pipeline.
- **LLM in discovery**: career-ops — none, by design, zero-token. JustHireMe — yes, for query generation and
  (bounded) for scoring.
- **Source integration**: career-ops — a filesystem-discovered provider registry, ~89 providers, 4-level
  integration ladder plus auto-detect. JustHireMe — prefix-dispatched ATS handlers plus generic scrapers,
  backed by a Protocol that nothing implements.
- **Normalized shape**: career-ops — 8 fields, no `seniority`/`tags`/`remote`, `description` only when free.
  JustHireMe — `RawLead` dict plus a `leads` table with signal/feedback columns.
- **Dedup keys**: career-ops — **three** (normalized URL, canonical company+role with location variant,
  SimHash fingerprint). JustHireMe — **one** (canonical URL → `md5[:16]`).
- **Over-normalization stance**: career-ops — explicitly under-strips on purpose, with the asymmetry argued
  in writing. JustHireMe — sorts remaining params, which is slightly more aggressive but unremarked.
- **Filter chain**: career-ops — 13 ordered steps, cheap-first, all local, each with a counted reason.
  JustHireMe — precondition gate, freshness gate, quality gate; no ordered chain.
- **Scoring**: career-ops — none in discovery; scoring is the agent's job in `modes/`. JustHireMe — a
  deterministic rubric with three branch profiles, conjunctive caps, and a bounded LLM layer.
- **Liveness**: career-ops — four-layer ladder, pure classifier + API + browser, asymmetric-error doctrine,
  20+ patterns each carrying a bug story. JustHireMe — no dedicated liveness classifier in discovery;
  it re-checks at apply time.
- **Persistence**: career-ops — Markdown + TSV, files canonical, SQLite derived and explicitly never primary.
  JustHireMe — SQLite, single table, no secondary indexes.
- **Config surface**: career-ops — 2,792-line YAML, four integration levels. JustHireMe — settings rows with
  `int_cfg` ranges and sensible defaults.
- **Observability**: career-ops — `scan-runs.tsv` per-filter counters, `portal-health.tsv`, plus
  `doctor.mjs` (16-check registry, deterministic `--json`) and a `--json` scan receipt. JustHireMe — per-call
  `ContextVar` result sinks plus named suppression logging.
- **Testing**: career-ops — auto-discovered suites with no registration list. JustHireMe — six JSONL eval
  cases through the production scorer, with `invariant: true` cases as CI guarantees.
- **Maturity of the discovery layer specifically**: career-ops — deep and battle-scarred, with issue numbers
  attached to individual constants. JustHireMe — clean and legible, with a stronger scoring core.

---

## 5. Patterns worth stealing

Ranked. Tier 1 is the four that would change CareerHelper's architecture; Tier 2 is high-value and
self-contained; Tier 3 is smaller mechanisms that are cheap to adopt and each fix a specific class of bug.
Every entry names where it lives and how it maps onto Next.js + FastAPI + Python.

### Tier 1 — architectural

#### 5.1 Deterministic rubric first; the LLM is a bounded refinement that cannot lift the hard caps

**Where:** `inspiration/JustHireMe/backend/ranking/scoring_engine.py:1-11` states the thesis —
*"keeps the model out of the rating loop"* — and `inspiration/JustHireMe/backend/ranking/evaluator.py`
implements the boundary (`_hard_cap` at `:211-260` ⚠ unverified).

**What it is:** the score is computed by a plain weighted mean over named criteria
(`scoring_engine.py:620-622`). An LLM may then adjust it — but `_hard_cap` **re-imposes the wrong-field and
seniority ceilings after the model has run.** So however persuasive the model's reasoning, it can never
promote a wrong-field role above 15 or a seniority-mismatched role above 48.

**Why it is the strongest single transfer:** it separates *judgement* (which the model is good at) from
*authority* (which it must not have). The mechanism, not the prompt, carries the guarantee. It also makes
the system debuggable: when a score is wrong you can ask whether the rubric or the refinement was wrong,
and the answer is recorded in `scored_by ∈ {deterministic, prefiltered_off_field, llm, deterministic_fallback}`.

**How it maps to CareerHelper:** CareerHelper already sends a resume to Kimi K3 for tailoring and trusts
the output. The analogous boundary is: **the model may rewrite and reorder bullets; it may not change
employers, titles, dates, degrees, or awards** — which the README's prompt already claims. Port the *shape*:
implement the invariant as a post-generation validator in Python that re-imposes the canonical facts after
the model returns, instead of relying on the prompt to hold. A tailoring run that alters a date should fail
loudly, not quietly ship.

#### 5.2 The asymmetric-error doctrine, written down in the code that acts on it

**Where:** `inspiration/career-ops/liveness-core.mjs:120-124`.

**What it is:** the file names its own failure asymmetry. A *false* `expired` verdict is written to the
ledger as `skipped_expired` and then dedup-filters a genuinely live job out of **every subsequent scan,
indefinitely** — unless `scan_history.recheck_after_days` eventually releases it. A *false* `active` costs
one wasted Playwright page load. Because those costs are not comparable, **every uncertain case resolves to
`uncertain`, never to `expired`.**

**Why it works:** the doctrine is not a comment about intent — it is the stated reason the classifier's
fallthrough is `uncertain` (`liveness-core.mjs:150`). And the classifier goes further: positive evidence of
an apply control *outranks* soft textual hints of expiry, so an expired-looking phrase cannot veto a page
that still offers an apply button.

**How it maps to CareerHelper:** CareerHelper has no liveness stage at all today. When it gets one, the
absence of a classifier is currently indistinguishable from a classifier that found nothing — that is the
bug this doctrine prevents. In Python terms: a liveness result should be
`Literal["active", "expired", "uncertain"]` with no `bool` narrowing anywhere, and the persistence layer
should refuse to record an `expired` that came from an `uncertain` source.

#### 5.3 The provider contract plus a registry that actually enforces it

**Where:** `inspiration/career-ops/providers/_types.js:163-178` (the `Provider` typedef),
`inspiration/career-ops/providers/_registry.mjs:23-59` (`loadProviders`) and `:76-107` (`resolveProvider`).

**What it is:** a provider is four fields — `id`, optional `detect(entry)`, required
`fetch(entry, ctx) → Job[]`, optional `dedupKey(job)`. The registry walks a directory, keeps `.mjs`, drops
`_`-prefixed files, `.sort()`s, and **warn-and-skips** on import error, on a missing `{id, fetch}`, and on a
duplicate id ("keeping first"). Resolution order is explicit: `provider:` key wins → local parser →
`detect()` in load order, first hit wins.

**Why it works:** the contract is three fields, so writing a provider is a small job. The registry validates
rather than trusts. And the `Context` passed to `fetch` (`_types.js:127-158` — `fetchText`, `fetchJson`,
`fetchResponse`, `maxPages`, `sleep`) means a provider never touches the network directly, so retry policy,
timeouts, user-agent, and the private-IP guard are all centralized and cannot drift per provider.

**How it maps to CareerHelper:** define a Python `Protocol` —

```python
class Provider(Protocol):
    id: str
    def detect(self, entry: PortalEntry) -> DetectHit | None: ...
    async def fetch(self, entry: PortalEntry, ctx: FetchContext) -> list[Posting]: ...
    def dedup_key(self, posting: Posting) -> str | None: ...
```

— and, unlike JustHireMe's `Source` Protocol (§6.11), **make the registry the only way a provider is
loaded**, with a startup assertion that every discovered module satisfies it. Same `ctx` idea: providers get
`ctx.fetch_text` / `ctx.fetch_json`, never `httpx` directly.

#### 5.4 "UNDER-STRIP ON PURPOSE" and "NO KEY IS NOT A KEY"

**Where:** `inspiration/career-ops/url-key.mjs:1-34`.

**What it is:** the most quotable paragraph in either project. It reasons about the *asymmetry of
normalization failure*: over-normalizing produces a **silent merge** — two distinct postings become one
row and data is lost with no signal; under-normalizing produces a **visible duplicate**, which a human
notices and fixes. Therefore the code prefers duplicates over merges, walks an RFC 3986 §6 normalization
ladder one rung at a time, and — the sharpest rule — **returns the empty string rather than a lowercase
stand-in when a URL cannot be normalized.** The reason given is SQL three-valued logic plus a recorded bug
where every `N/A` row shared one key and collapsed together.

**Why it works:** it converts a taste question ("how aggressive should normalization be?") into a decision
rule with a stated cost model, and the rule generalizes far beyond URLs.

**How it maps to CareerHelper:** apply it to every identity decision — dedup keys, slug generation,
company-name canonicalization. Under-strip; prefer a visible duplicate over a silent merge; and represent
"no key" as a distinct sentinel rather than an empty-ish string. A `NULL`/`None` that does not compare equal
to itself is the correct representation.

### Tier 2 — high-value and self-contained

#### 5.5 Three dedup keys, where the third is warn-only

**Where:** `scan.mjs:1325-1340` (normalized URL), `scan.mjs:1980-1995` (canonical company + role + location),
`fingerprint-core.mjs:1-35` (SimHash).

**What it is:** increasing fuzziness, decreasing authority. URL dedup and company+role dedup are *gates* —
they drop. The body fingerprint is *advisory* — `findCrossListings()` warns and drops nothing.

**Why it works:** the fuzziest signal is also the one most likely to be wrong, so it is given no veto. The
gradient from gate to advisory is explicit in the code's behavior rather than in a config flag.

**How it maps to CareerHelper:** implement the same gradient. A URL key and a `(company, title, location)`
key can gate; a body-similarity signal should only attach a `possible_duplicate_of` note to the record.

#### 5.6 Explainability as data, not prose

**Where:** `scoring_engine.py` — `ScoreResult.criteria[]` is a list of
`{name, score, weight, reason}` records, and `applied_cap` is a first-class field.

**What it is:** the score breakdown is a structured object a UI can render directly. No text parsing.

**How it maps to CareerHelper:** make the FastAPI response for a scored posting a Pydantic model with
`criteria: list[ScoreCriterion]` and `applied_cap: str | None`. The Next.js side renders the breakdown with
no string munging, and any future "why is this ranked low?" feature is free.

#### 5.7 Caps as conjunctive ceilings with every reason surfaced, ordered by tightness

**Where:** `scoring_engine.py:655-680` (`_apply_caps`).

**What it is:** each cap is an *upper bound on the final score*, the tightest wins via `min()`, and **every
cap that fired appends its reason to `result.gaps`**. The values are wrong field 15; seniority mismatch
30/38/45/48 by direction; no direct stack 52 or 42; thin posting 68.

**Why it works:** `min()` means caps cannot interact multiplicatively or in an order-dependent way — the
cap set is a declarative constraint system rather than a sequence of adjustments. And because caps are
ordered by tightness, the reported reason is the *binding* constraint, not an arbitrary one of several.

**How it maps to CareerHelper:** adopt verbatim as the scoring backbone. This is the piece that makes
"why was this job filtered out?" answerable in one field.

#### 5.8 The "free or absent" rule that keeps a scanner zero-token

**Where:** `providers/_types.js:21-69` — `description?` is optional and the scanner fills it only when a
source hands it over for free.

**What it is:** the normalized `Job` carries a description only when a source provides one at no cost. The
scanner never *fetches* a body merely to have one.

**Why it works:** it is the reason `npm run scan` is zero-token and zero-LLM, and it is why the downstream
fingerprint signal is "no body, no signal, no false positives" (`fingerprint-core.mjs`) rather than a
best-effort guess. A capability that would be expensive is simply made *absent and honest* instead of
approximated.

**How it maps to CareerHelper:** CareerHelper's core cost is the Kimi K3 tailoring call, so the same
discipline applies with more force. Discovery must not make an LLM call per posting. Enrichment is a separate,
explicit, later stage.

#### 5.9 Fingerprinting without storing the body

**Where:** `fingerprint-core.mjs:1-35` — 64-bit SimHash over 3-token shingles, persisted as 16 hex chars.
`FINGERPRINT_MIN_TEXT = 200`, `CROSSLIST_THRESHOLD = 0.92`, `CROSSLIST_WINDOW_DAYS = 90`.

**What it is:** 16 bytes per posting buys near-duplicate detection across a 90-day window, with no storage
of job-description bodies and no embedding model.

**Why it works:** the storage decision and the capability decision are separated. You get "same text,
different URL" cheaply.

**How it maps to CareerHelper:** this is the natural bridge to a semantic matcher. Store the SimHash *now*
(16 chars in SQLite), ship a hashing-based near-duplicate signal, and treat embeddings as a later upgrade
that reuses the same column contract.

#### 5.10 Positionally-stable append-only TSV with a header-drift warning

**Where:** `scan.mjs:2259-2293` (`formatScanHistoryRow`), `:2449` (header written on create),
`:2531` (`SCAN_RUNS_HEADER`).

**What it is:** `data/scan-history.tsv` has 12 positional columns and a header. It is append-only and never
rewritten.

**Why it matters and why it is a caveat:** append-only positional files are excellent for audit and terrible
for evolution — `detect-reposts.mjs:146-150` already carries index-fallback logic for pre-`normalized_company`
rows. The *stealable* part is that the format declares itself and warns on drift; the *unstealable* part is
that adding a column requires every reader to know its position.

**How it maps to CareerHelper:** use append-only TSV/JSONL for scan history and run receipts — it diffs
cleanly and never corrupts — but put a schema version in the header from day one, so the fallback index
logic is bounded rather than open-ended.

#### 5.11 Locked read-modify-write for the tracker's ledger

**Where:** `scan.mjs:2395-2446` (`appendToPipeline` / `appendToScanHistory`, with the lock rationale in the
comments); `tracker.mjs` for the tracker lock.

**What it is:** every write to a shared user-facing file takes a lock, then appends. Hand-editing is
explicitly forbidden by the docs — writes funnel through a small number of locked scripts.

**How it maps to CareerHelper:** FastAPI can receive concurrent requests that touch the same files. A
read-modify-write on a resume or a tracker needs a lock or an atomic-replace, not a naive write. (Note the
caveat in §6.14: the lock idiom is correct here but its extraction across the repo is incomplete.)

#### 5.12 Report numbers reserved under lock, never `max + 1`

**Where:** `reserve-report-num.mjs` (⚠ child-reported), using `O_CREAT|O_EXCL` sentinels with a 4 h TTL and a
50-retry cap, under the tracker lock.

**What it is:** identifiers are *reserved* by atomically creating a sentinel, not derived by reading the
current maximum and adding one.

**Why it works:** `max + 1` across concurrent workers is a classic duplicate-id race. `O_CREAT|O_EXCL`
turns the allocation into a single atomic syscall, and the TTL plus retry cap means a crashed reservation
does not deadlock the system forever.

**How it maps to CareerHelper:** any generated artifact that gets a number or a slug — tailoring runs,
report ids, output directories — must allocate atomically. In Python: `os.open(path, os.O_CREAT | os.O_EXCL)`,
with a staleness sweep.

#### 5.13 Keyless-first with a graceful keyed fallback

**Where:** `inspiration/JustHireMe/backend/discovery/free_scout.py` (`run_free_source_scan`), called before
board sweeps in `backend/api/routers/discovery.py:265-300`.

**What it is:** the free, keyless source scan runs as the backbone; paid/authenticated sources are additive.

**How it maps to CareerHelper:** CareerHelper needs exactly one key (the OpenCode Go API key for Kimi K3).
Discovery should need *none* — so "can I search for jobs?" and "can I tailor a resume?" fail independently.

#### 5.14 One dispatch point per capability, with past bugs cited

**Where:** `browser-extract.mjs:586-598` — `fetchJdViaKnownApi()` is shared by the CLI `jd` mode and
`fetch-jd.mjs`, deliberately, *"so the interactive and headless paths cannot drift."*

**What it is:** when the same capability is reachable two ways, both go through one function.

**Why it works:** drift between two implementations of one capability is the failure this prevents, and the
comment names the intent so a future edit does not reintroduce it.

**How it maps to CareerHelper:** the FastAPI service layer and the CLI in `scripts/` must call the same
Python modules — which `docs/nextjs-fastapi-plan.md` already prescribes ("Python service modules shared by
CLI and FastAPI"). This pattern is the enforcement mechanism for that plan.

#### 5.15 Provenance-carrying errors: distinguish "checked and found none" from "never checked"

**Where:** `scout.py:93-107` ⚠ unverified — `_source_error_detail` maps status codes to human strings
(403 → "blocked by source", 429 → "rate limited by source"), and errors accumulate per source rather than
being swallowed.

**What it is:** an empty result carries *why* it is empty.

**Why it matters:** without it, a blocked source and a genuinely empty source render identically, which is
how a job search silently returns nothing for a week.

**How it maps to CareerHelper:** every discovery source result should be
`{postings: [...], status: "ok" | "blocked" | "rate_limited" | "error", detail: str | None}`. Surface it in
the Next.js UI as a per-source health indicator rather than an empty list.

#### 5.16 Two-signal agreement instead of a confident guess

**Where:** `liveness-api.mjs:216-241` ⚠ unverified — the LinkedIn classifier requires two signals to agree
before concluding; disagreement returns `uncertain`.

**What it is:** when the evidence is weak enough that one signal can be wrong, require a second independent
one, and fall back to uncertainty on disagreement.

**How it maps to CareerHelper:** generalize past liveness. Anywhere CareerHelper infers something the user
will act on from weak evidence — "is this remote?", "is this senior-level?", "is this the same job?" — the
pattern is: two independent signals, agreement required, otherwise mark it unknown rather than guessing.

#### 5.17 Remote-refreshable selectors with a bundled fallback

**Where:** `inspiration/JustHireMe/backend/automation/selectors.py` (91 lines).

**What it is:** CSS/DOM selectors for scraped boards can be refreshed remotely, are cached, and fall back to
a bundled copy.

**Why it works:** a board's DOM change degrades the system instead of breaking it. The fallback means the
worst case is stale, not dead.

**How it maps to CareerHelper:** if CareerHelper ever scrapes a board, do not hardcode selectors in code.
Ship a bundled default in the repo and allow an override, with the bundled copy as the tested path.

#### 5.18 Centralized, unit-testable safety decision with a default-deny hit test

**Where:** `inspiration/JustHireMe/backend/automation/actuator.py` — auto-submit is opt-in via
`JHM_AUTO_APPLY`, centralized in `_submit_mode` (`:249-271` ⚠ unverified), behind a default-deny
`_safe_to_click` hit test (`:277-357` ⚠ unverified). SSRF is guarded on every request via
`core/url_guard.py`.

**What it is:** one function decides whether it is safe to click, the default answer is no, and the decision
is testable in isolation.

**Why it works:** a scattered `if` per call site cannot be audited or tested; a single predicate can.

**How it maps to CareerHelper:** CareerHelper's stated scope is tailoring and PDF generation, not
auto-apply. If auto-apply is ever added, this is the pattern — and the current scope is the reason not to
add it yet. The immediately useful part is `url_guard.py`: CareerHelper will fetch user-supplied job URLs,
so an SSRF guard belongs in the fetch layer from the start, alongside `providers/_ip-guard.mjs`'s
approach on the career-ops side.

#### 5.19 Per-provider quirks modeled in the provider, not the framework

**Where:** `liveness-api.mjs:110-113` — Ashby's browser rung *false-reports live postings as expired*
because Ashby renders client-side, so the API rung is authoritative for Ashby. `:82-95` — Lever's
`api404Authoritative: false`, with a dated repro comment.

**What it is:** a source-specific correction lives in that source's declaration, as data with a reason,
not as a branch in the shared classifier.

**How it maps to CareerHelper:** when a particular ATS behaves oddly, the fix belongs in that provider's
module (or its config stanza), with the bug recorded. This is what keeps the core small as provider count
grows.

### Tier 3 — smaller mechanisms, each closing a specific bug class

#### 5.20 Idempotent re-scoring from stored bases

**Where:** `feedback_ranker.py` (±18) and `feedback_semantic.py` (±12, a Rocchio centroid) recompute from
stored base values.

**What it is:** derived scores are recomputed from durable inputs rather than incrementally mutated.

**How it maps to CareerHelper:** the tailoring score and any feedback adjustment should be a function of
stored facts, recomputable at any time. This makes a scoring-formula change a recompute, not a migration.

#### 5.21 Provider-honest degradation

**Where:** `ranking/semantic.py` — when the embedding stack reduces to hashing it reports
`"hashing"` with `degraded: True` rather than pretending.

**What it is:** a capability states when it is operating in a reduced mode.

**How it maps to CareerHelper:** if Kimi K3 is unreachable and CareerHelper falls back to a cheaper model or
a template-only compile, the result must say so. The user is about to send a resume into the world; a
silently degraded generation is the worst possible failure mode.

#### 5.22 `PREVIEW` by default for user-layer writes

**Where:** `prepare-application.mjs` / `application-artifacts.mjs` (⚠ child-reported) — preview-by-default for
writes into the user layer.

**What it is:** the write path shows what it would do before doing it.

**How it maps to CareerHelper:** a "dry run" for tailoring is already present (`--dry-run`). Extend the
principle: any operation that overwrites or consumes a canonical resume path should be inspectable first.

#### 5.23 Fail-closed identity checks before writing user config

**Where:** `mode setup` / `boardIdentityMatches` (⚠ child-reported) — identity is verified before the system
writes into a user's configuration.

**How it maps to CareerHelper:** before CareerHelper writes `.env`, a resume path, or a config file, verify
it is operating on the project it thinks it is. Cheap check, catastrophic failure class.

#### 5.24 Tests auto-discovered, with no registration list

**Where:** `ARCHITECTURE.md` and `test-all.mjs` — suites live in `tests/**/*.test.mjs`, discovered
automatically, guarded against regression to hand-registration by a dedicated test.

**What it is:** *"a new suite runs the moment it is written and a typo cannot silently turn CI green."*

**How it maps to CareerHelper:** `tests/` should be discovered by pytest's default collection with no
per-file registration. The guard test — asserting that discovery has not been downgraded to a list — is the
unusual and valuable part.

#### 5.25 A capability registry that reports its own state deterministically

**Where:** `doctor.mjs` — a 16-check registry with deterministic `--json` output.

**How it maps to CareerHelper:** a `doctor` command that reports whether `pdflatex` exists, whether the
canonical resume is present, whether the API key is configured, and whether the model is reachable — with
machine-readable output. This is a small amount of code that removes most first-run support burden.

#### 5.26 Per-call result sinks

**Where:** JustHireMe's `Scout`-style `ContextVar` result sinks.

**What it is:** a discovery call collects its own findings and diagnostics in a context-local sink, so
concurrent calls cannot cross-contaminate.

**How it maps to CareerHelper:** FastAPI serves concurrent requests; `contextvars.ContextVar` is the right
Python mechanism for per-request accumulation, and it composes with the async fetch layer without threading
state through every function signature.

#### 5.27 Layered rung escalation, lazily, and never in parallel

**Where:** `check-liveness.mjs:85` (sequential; never Playwright in parallel), `:87-101` (API first, browser
only on miss).

**What it is:** cheap layers run first, expensive layers run only when the cheap ones are inconclusive, and
the expensive layer is deliberately serialized to avoid looking like an attack.

**How it maps to CareerHelper:** the same ladder applies to any enrichment — try the free structured source,
then the HTML page, then the headless browser; never fan out headless.

#### 5.28 Semantics with a stated blend, not a black box

**Where:** `ranking/semantic.py` — group weights 0.22 / 0.34 / 0.26 / 0.10 / 0.08, blended as
**60% mean + 40% peak**, linearly stretched per provider.

**What it is:** the aggregation rule is declared numbers, and the per-provider stretch accounts for the fact
that different embedding models have different score distributions.

**How it maps to CareerHelper:** when a semantic signal is introduced, publish its blend. The 60/40
mean-plus-peak split is a good default: the mean captures overall fit, the peak captures that one
requirement being an exact match.

#### 5.29 Field-agnostic generalization instead of a technology whitelist

**Where:** `scoring_engine.py` — `apply_domain_generalization` transforms terms by role family rather than
checking against a fixed list of technologies.

**Why it matters:** a tech whitelist ages badly and silently excludes everything new. (Caveat: the same
function mutates a dataclass in place and its predicate is captured before mutation —
see §6.18, §6.19.)

#### 5.30 The fail-closed gate with a named escape hatch

**Where:** `discovery.py:265-300` (refuses to scan without profile signal or explicit targets);
`quality_gate.py:79-116` ⚠ unverified (undated postings dropped unless a source is marked trusted for recency).

**What it is:** the default is closed, and the way through is explicit, named, and narrow.

**Why it works:** this is the same shape as §5.2's asymmetric error handling and §5.18's default-deny click
— the same instinct applied three times to three different resources.

**How it maps to CareerHelper:** any operation that would waste a paid API call or write into the user layer
should be closed by default with an explicit override, rather than open by default with a guard.

---

## 6. Anti-patterns and caveats

Numbered so §7 and §8 can refer to them. Items marked ⚠ are child-reported, not independently re-verified.

### career-ops

**6.1 — `scan.mjs` is a 3,637-line monolith that every sibling imports.** Verified by `wc -l`. It is not
just large; it is a *dependency* of the other scanners, so its internal helpers have become an accidental
public API. Two recorded bugs trace to sibling scanners carrying bare-relative copies of the same path
constants instead of importing them (the comment at `scan.mjs:104-111` cites #3510). The env-overridable
paths fixed the instance, not the cause: there is still no module boundary stopping the next sibling from
re-deriving a constant.

**6.2 — The normalized record omits fields a job search actually needs.** `Job`
(`providers/_types.js:21-69`) is `title`, `url`, `company`, `location`, `description?`, `postedAt?`,
`salary?`, and the three trust fields. There is **no first-class `remote`, `seniority`, or `tags`.** Remote
is inferred from the location string, seniority from the title, tags from nothing. That is a surprising
omission for a job-search tool, and it is the reason the filter chain has to reach into URL and title
(`locationFilter(location, url, title)`).

**6.3 — `location` is a free-text kitchen sink.** It carries geography, work model, and sometimes a salary
band (Built In's `fa-sack-dollar` marker). `normalizeLocationForDedup` (`scan.mjs:1900-1935`) — five
documented separators plus a labeled-segment allowlist — exists to compensate. When one field encodes three
concerns, every consumer needs a parser.

**6.4 — `detect()` runs before the provider knows whether the entry was meant for it.** Resolution is
alphabetical by load order with first-hit-wins (`_registry.mjs:76-107`). A new provider following the
URL-pattern shape can therefore silently steal an entry from an existing provider, and the failure is a
wrong-source fetch rather than an error.

**6.5 — Duplicate detection is heuristic and noisy enough to need its own constraints.**
`MIN_REPOST_SPAN_DAYS = 1` (`detect-reposts.mjs:85`) is an openly admitted compromise: `first_seen` records
when the *scanner* first saw a URL, not when the employer posted it, so a weekly scanner cannot distinguish a
repost from a batch listing one day apart. Repost detection mixes title identity with fuzzy matching;
cross-listing uses a SimHash threshold. Both are configured to be conservative, and both are advisory — but
that means the user does the final discrimination.

**6.6 — No unified error surfacing.** Failures accumulate per-board into an array. A target that fails *every
run* is visible only through `portal-health.tsv`, `verify-portals.mjs`, or `audit-portals.mjs` — three
separate scripts, none of which is the scan itself.

**6.7 — `dead-boards.mjs` and posting liveness have disjoint lifetimes and share no vocabulary.**
`dead-boards.mjs` uses 3 strikes over 30 days; posting liveness is single-shot per posting. A board that
404s every posting may advance neither counter consistently.

**6.8 — `discover-ats.mjs` pays the full 11-vendor probe cost for an unresolvable company.** The code
comments state this honestly: *"A company on no supported board is the case that got more expensive: it now
probes every vendor before giving up."* There is no negative cache, unlike `dead-boards.mjs`.

**6.9 — `jd-capture.mjs` cannot disambiguate a report with several captures when no `companySlug` is
supplied** — it takes the most recent unconditionally. The header flags this as a deliberate but lossy
default, and documents the cost of the alternative it rejected: the wrong company's JD would be copied in as
the permanent record.

**6.10 — `jd-similarity` uses raw Jaccard with no IDF or BM25 weighting.** A JD padded with generic
engineering vocabulary scores high against any other JD; the seniority gate is the only real discriminator.
The thresholds (0.72 similar, 0.45 related) are uncalibrated against any published corpus and have **no
config binding** — they are code constants.

**6.11 — No embeddings anywhere in the discovery layer.** Everything is lexical. There is no semantic
similarity, no vector store, no clustering of JDs by meaning. For a resume-tailoring product this is the
first thing worth replacing.

**6.12 — The configuration surface is very large.** `templates/portals.example.yml` is 2,792 lines, mostly
commented per-provider stanzas, across four integration levels. The mental model required to add one company
is *"which of five integration styles, and does its host auto-detect?"* That is a steep entry cost for the
most common user action.

**6.13 — Four files do not do what their names suggest.** Preserve these; they are easy traps.

- `jd-capture.mjs` is a **filesystem lookup** that resolves an archived capture in `jds/` by report number.
  No network, no parsing (`jd-capture.mjs:1-14`, `findCaptureForReport` at `:68`).
- `match-star.mjs` is a **STAR-story ↔ behavioural-question matcher** over
  `interview-prep/story-bank.md`. Nothing to do with postings (`match-star.mjs:1-20`).
- `verify-ats.mjs` is a **generated-CV ATS-parseability scorer** (0–100, letter grade) reading one HTML
  file. Not ATS discovery (`verify-ats.mjs:1-30`).
- `extract-latex-content.mjs` is a **LaTeX CV slot detector**. Out of scope entirely.
- And `intake.mjs` is **CV/documents intake, not job intake** (`intake.mjs:2-14`) — an easy misread given
  the name.

The real ATS re-verification lives in `verify-portals.mjs` + `audit-portals.mjs`; the real posting score
lives in `modes/triage.md` and the `*-eval.mjs` scripts.

**6.14 — The lock idiom is correct but its extraction is incomplete.** `portal-health-lock.mjs` is the
**fourth copy** of the same directory-lock protocol; a prior refactor patched two of them and declared "one
definition, no sibling drift," while `portal-health-lock.mjs` and `followup-seed.mjs` were still carrying
all three faces of the original bug. The lesson is not "locks are bad" — it is that a correct idiom copied
four times drifts, and the drift was invisible precisely because the code was correct the first time.

### JustHireMe

**6.15 — The `Source` Protocol is implemented by nothing.**
`backend/discovery/sources/base.py` is 20 lines declaring `RawLead(TypedDict, total=False)` and
`class Source(Protocol)` with `name: str` and `async def fetch(queries, config) -> list[RawLead]`. **No
source class subclasses or registers against it.** The capability model exists as documentation only, which
is why there is no pagination, rate-limit, or auth declaration anywhere in the codebase. Do not read the
Protocol as evidence of a working plugin system.

**6.16 — Dedup is URL-canonical only.** There is no company+title key and no body fingerprint. The same role
posted to three boards is three rows.

**6.17 — No secondary index on `leads`.** A grep for `CREATE INDEX` across all four migrations finds exactly
one, `idx_resume_templates_default` (`004_resume_templates.sql:13`). Every discovery query is a table scan.

**6.18 — `apply_domain_generalization` mutates a dataclass in place.** The function rewrites the posting
object it was handed rather than returning a transformed copy, so callers see the mutation and ordering
becomes observable behavior.

**6.19 — That ordering dependency is implicit and silently fragile.** `score_job_lead`
(`scoring_engine.py:804-860`) captures `tech_taxonomy_present = bool(posting.terms)` **before** calling
`apply_domain_generalization`, which is the correct thing to do — and the entire three-branch scoring
structure depends on it. Nothing enforces that order but the line sequence. A future edit that moves the
generalization call up silently collapses three branches into one, with no test designed to catch it.

**6.20 — Two disagreeing sources of truth for the criterion weights, with nothing enforcing consistency.**
`CriterionSpec.max_weight` declares role 15 / stack 22 / evidence 20 / seniority 25 / logistics 13 /
learning curve 5, while the live scoring branch uses different hardcoded numbers (role 15, stack 20, proof
18, seniority 20, constraints 12). `criteria/registry.py` is **never consulted** by the scoring engine. So
there is a declarative description of the rubric that does not describe the rubric, and a reader who finds
the registry first will be wrong.

**6.21 — The LLM *can* lift the stack and thin-posting caps.** `_hard_cap` re-applies only the wrong-field
and seniority ceilings after the model runs. The no-direct-stack cap (52/42) and the thin-posting cap (68)
are **not** re-imposed. This is a real hole in the strongest pattern in the codebase (§5.1) and it is worth
understanding before porting: the guarantee holds only for the caps someone remembered to re-apply, so the
mechanism should be **enumerate-the-caps-you-re-impose verified by a test that fails when a cap is added
without registration.**

**6.22 — Two score scales that barely interact.** The feedback channels adjust by ±18 (`feedback_ranker.py`)
and ±12 (`feedback_semantic.py`), while several caps bind at 15. A cap at 15 is therefore swamped by feedback
that can move a score by 30 in either direction, depending on which channel fires. The magnitudes were
chosen independently.

**6.23 — Stretch windows are model-specific magic numbers.** The per-provider linear stretch in
`ranking/semantic.py` is calibrated to particular embedding models (local MiniLM-L6 384-d, OpenAI
`text-embedding-3-small` 1536-d). Swapping either model silently invalidates the calibration of every
downstream band, and nothing detects the swap.

**6.24 — Computed but unread data.** `JobLead`/`REQUIRES` graph nodes are written and never read.
`commercial_intent`, `budget_amount`, and `budget_present` are computed and read by no criterion. This is
cost paid at write time for a consumer that does not exist.

**6.25 — `learning_curve.py` is a specification with no `evaluate()`.** Dead code, and worse than dead:
it looks like a scoring dimension because `CriterionSpec` gives it a max weight of 5.

**6.26 — A failed profile-correlation rebuild is only a `_log.debug`.** The system proceeds with stale
correlations and says nothing at any level a user would see.

**6.27 — The 7-day freshness gate can silently drop entire date-less lanes.** It is mitigated by the
trusted-recency escape hatch (§5.30), but sources that are not marked trusted have no path through if they
do not emit dates.

**6.28 — No staffing-agency or recruiter blocklist.** Nothing distinguishes an employer's posting from a
recruiter reposting the same role at an undisclosed client.

**6.29 — Only the aggregator paginates.** Every other source returns whatever the first response contains,
so result depth is a property of the source rather than of the query.

**6.30 — Helpers are duplicated across `scout.py`, `free_scout.py`, and `x_scout.py`.** For example
`_source_error_detail` exists in both `scout.py:93-107` and `free_scout.py:118-127` ⚠. Three near-copies of
the same conventions, free to drift.

**6.31 — There is no rank-order metric.** Six JSONL eval case files run through the production scorer and
assert score bands and whether a cap fired, with `invariant: true` cases as CI guarantees and
`ACCURACY_FLOOR = 1.0`. That is genuinely good discipline — but it tests **absolute bands, not ordering
quality.** There is no nDCG, no precision@k, no MRR. A change that reorders the top of the list while
keeping every score in its band passes CI.

### Cross-cutting

**6.32 — Neither project's discovery layer has verified test receipts in this survey.** The child reports
consulted here are self-reports with no attached command or test output. Line-level claims marked ⚠ should be
spot-checked before being cited as authority.

**6.33 — Two overlapping identity systems exist by design in career-ops.** The scan side uses three keys
(URL, company+role, fingerprint); the tracker side uses `url-key.mjs` + `normalizeCompany`. They are not the
same machinery. That is a deliberate consequence of files being canonical and the handoff being agent-driven
— but it means a slug can be correct on one side and wrong on the other, and deciding it deliberately for
CareerHelper is better than inheriting it.

**6.34 — docs drift from reality in both projects.** career-ops's `ARCHITECTURE.md:26` says "~70 scripts"
against ~128 root `.mjs` files; `build-dashboard.mjs` is named for a job it does not do; the web app's
version (`0.11.0`) and the scaffolder's (`1.33.0`) are separate release trains; state names appear in Spanish
in some docs and in the canonical English `states.yml` labels elsewhere. Small individually, and collectively
the reason a generated doc beats a hand-maintained one for anything counted.

---

## 7. Suggested design for CareerHelper

### 7.0 The shape of the gap

A job search has three stages. career-ops does **discovery** and hands off; JustHireMe does **discovery plus
ranking** and hands off; CareerHelper does **tailoring** — the third stage — and currently has no first two.
That framing is what makes §5 and §6 actionable rather than an exercise in admiration: the parts worth taking
are precisely the parts CareerHelper lacks, and the parts worth avoiding are the parts it would otherwise
reinvent under time pressure.

```text
career-ops      [ discovery ────────────────► ]  hand off to an agent
JustHireMe      [ discovery ─► ranking ─────► ]  hand off to a human
CareerHelper    [ ◄── missing ──► ][ tailoring ─► PDF ]
                 ↑ this document is about this box
```

`docs/nextjs-fastapi-plan.md` describes the third box in detail and does not mention the first two at all —
no discovery, no sources, no ranking, no `portals.yml` equivalent. So everything below is **additive to that
plan, not a revision of it.** The plan's endpoint list (`/api/health`, `/api/templates`, `/api/generations`)
and its phase ordering (Phase 1 Python service extraction → Phase 2 FastAPI MVP → Phase 3 Next.js) stay as
written. Discovery is a new phase that depends on Phase 1 and can proceed in parallel with Phases 3–4.

### 7.1 Where discovery lands in the plan's existing structure

The plan already proposes the folder shape and the shared-service doctrine. Discovery slots in without
changing either:

```text
backend/app/
├── api/
│   ├── health.py             # extend: report each source's health
│   ├── templates.py
│   ├── generations.py
│   └── discovery.py          # NEW — POST /api/discovery/runs, GET /api/discovery/postings
├── models/                   # NEW: discovery_*.py SQLAlchemy models
├── schemas/
│   └── discovery.py          # NEW: Pydantic Posting, PortalEntry, ScoreResult
├── services/
│   ├── llm.py                # unchanged
│   ├── tailoring.py          # unchanged
│   ├── latex.py              # unchanged
│   ├── storage.py            # extended with the discovery ledger
│   ├── jobs.py               # unchanged (in-process asyncio job manager)
│   └── discovery/            # NEW package
│       ├── __init__.py
│       ├── runner.py         # the orchestration loop — the scan.mjs analogue
│       ├── registry.py       # provider discovery + contract enforcement
│       ├── types.py          # Provider Protocol, Posting, FetchContext
│       ├── http.py           # shared client: retry, timeout, SSRF guard, UA
│       ├── filters.py        # the ordered filter chain
│       ├── dedup.py          # three keys + the under-strip doctrine
│       ├── fingerprint.py    # 64-bit SimHash
│       ├── ranking.py        # deterministic rubric + cap registry
│       └── providers/
│           ├── greenhouse.py
│           ├── lever.py
│           ├── ashby.py
│           └── ...
```

Two plan rules do the heavy lifting and should be treated as binding for this package:

- *"Python service modules contain the business logic. CLI scripts and FastAPI call the same functions."* —
  this is §5.14 generalized. `scripts/scan.py` (if it exists) must be a thin adapter over
  `services/discovery/runner.py`, exactly as the plan already requires for `tailor_resume.py`.
- *"Do not recreate Kimi or LaTeX logic in Next.js Route Handlers."* — extend to discovery: the Next.js side
  never fetches a job board. It asks FastAPI, which owns every provider and every credential.

### 7.2 The provider interface

Port career-ops's four-field contract (§5.3) into Python, and fix the two things career-ops and JustHireMe
each got wrong: career-ops's registry validates but its `scan.mjs` monolith is load-bearing (§6.1);
JustHireMe's `Source` Protocol is a shape nothing implements (§6.15). The fix for both is the same — **the
registry is the only way a provider is loaded, and it fails loudly.**

```python
# backend/app/services/discovery/types.py
from typing import Protocol, Any, Literal
from pydantic import BaseModel, HttpUrl

class DetectHit(BaseModel):
    confidence: Literal["certain", "likely"]
    api_url: str | None = None

class PortalEntry(BaseModel):
    """Opaque to the runner; only the provider interprets provider-specific keys."""
    name: str                                  # required
    enabled: bool = True
    careers_url: HttpUrl | None = None
    api: str | None = None
    provider: str | None = None                # explicit override — wins over detect()
    company_slug: str | None = None
    max_pages: int | None = None
    extra: dict[str, Any] = {}                 # provider-namespaced, never read by the runner

class Provider(Protocol):
    id: str
    def detect(self, entry: PortalEntry) -> DetectHit | None: ...
    async def fetch(self, entry: PortalEntry, ctx: "FetchContext") -> list["Posting"]: ...
    def dedup_key(self, posting: "Posting") -> str | None: ...
```

Resolution order is career-ops's, made explicit: **explicit `provider:` → registered `detect()` by
declaration order → error.** Never silent fallthrough to "some other provider's fetch" (§6.4). A `FetchContext`
mirrors career-ops's `Context` (`_types.js:127-158`) so no provider ever touches the network client directly:

```python
class FetchContext(Protocol):
    transport: Literal["http"]
    async def fetch_text(self, url: str, **kw) -> str: ...
    async def fetch_json(self, url: str, **kw) -> Any: ...
    max_pages: int
    async def sleep(self, ms: int) -> None: ...
```

That indirection is what makes retry, timeout, `Retry-After`, jitter, user-agent, and the private-IP guard
one implementation instead of N (§5.3, §5.18).

**Registry enforcement.**

```python
# backend/app/services/discovery/registry.py
PROVIDERS: dict[str, Provider] = {}

def register(p: Provider) -> Provider:
    if not isinstance(getattr(p, "id", None), str) or not p.id:
        raise ProviderContractError(f"{p!r} has no string id")
    if not callable(getattr(p, "fetch", None)):
        raise ProviderContractError(f"{p.id}: fetch is not callable")
    if p.id in PROVIDERS:
        raise ProviderContractError(f"duplicate provider id {p.id!r}")
    PROVIDERS[p.id] = p
    return p

def assert_all_satisfy_contract() -> None:
    for pid, p in PROVIDERS.items():
        assert isinstance(p.id, str) and p.id
        assert callable(p.fetch)
        if hasattr(p, "detect"):
            assert callable(p.detect)
```

Career-ops's registry *warn-and-skips* on a duplicate id and keeps the first. CareerHelper should **raise on
import** — a duplicate provider id is a deployment error, not a runtime condition, and keeping-first means one
of two providers is silently dead (§6.6's "no unified error surfacing" is the same failure at a different
layer). Validate at startup, not per fetch.

### 7.3 The normalized `Posting` record

This is where the single largest correction goes. career-ops's `Job` (`providers/_types.js:21-69`) omits
`remote`, `seniority`, and `tags`, and encodes all three implicitly in `location` and `title` (§6.2, §6.3).
Every downstream consumer then re-parses free text with its own regex. Model them explicitly instead:

```python
# backend/app/services/discovery/types.py
WorkModel  = Literal["remote", "hybrid", "onsite", "unknown"]
Seniority  = Literal["intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager", "unknown"]

class Location(BaseModel):
    raw: str                       # exactly what the source said — never discard
    city: str | None = None
    region: str | None = None
    country: str | None = None      # ISO 3166-1 alpha-2 where derivable
    work_model: WorkModel = "unknown"

class Salary(BaseModel):
    min: int | None = None
    max: int | None = None
    currency: str | None = None
    period: Literal["year", "month", "day", "hour", "unknown"] = "unknown"
    source: Literal["posting", "enriched", "inferred"] = "posting"

class Trust(BaseModel):
    score: float | None = None
    flags: list[str] = []
    level: Literal["unknown", "low", "medium", "high"] = "unknown"

class Posting(BaseModel):
    source: str                     # provider id
    source_job_id: str | None = None
    company: str
    company_normalized: str
    title: str
    title_normalized: str
    url: HttpUrl
    canonical_url: str
    location: Location
    seniority: Seniority = "unknown"
    employment_type: Literal["full_time", "part_time", "contract", "internship", "unknown"] = "unknown"
    salary: Salary | None = None
    posted_at: datetime | None = None
    first_seen_at: datetime
    description: str | None = None          # free-or-absent (see below)
    fingerprint: str | None = None          # 16 hex chars, only when description present
    trust: Trust = Trust()
    dedup_key_url: str | None = None
    dedup_key_role: str | None = None
```

Four rules that go with the model:

- **`location.raw` is preserved verbatim.** Every derived field is an addition, never a replacement. This is
  the minimum that makes a bad `work_model` inference fixable rather than destructive.
- **`unknown` is a first-class value everywhere.** `WorkModel` and `Seniority` include it, so "we did not
  determine this" is representable and distinct from "we determined it is onsite" (§5.15 applied to fields).
- **`description` is free-or-absent.** CareerHelper's per-posting cost is a Kimi K3 call, so this rule matters
  more here than in career-ops: discovery never calls an LLM to obtain a description (§5.8). A source either
  hands one over or the field is `None`.
- **`fingerprint` is `None` when there is no description.** No body, no signal, no false positive
  (`fingerprint-core.mjs`).

### 7.4 Deduplication

Three keys, strictly ordered by fuzziness, with the third advisory only (§5.5). And the doctrine is
career-ops's §5.4, adopted wholesale:

- **`dedup_key_url`** — gate. Walk an RFC 3986 §6 normalization ladder one rung at a time, remove tracking
  parameters, and **return `None` rather than a lowercase stand-in when the URL cannot be normalized.**
  Preserve the reasoning: over-normalizing produces a silent merge, under-normalizing a visible duplicate,
  and a duplicate is strictly cheaper. In SQL, `None` becomes `NULL`, which does not compare equal to itself —
  which is exactly the behaviour wanted, and the reason a shared empty-string key once collapsed every
  `N/A` row into one.
- **`dedup_key_role`** — gate. Canonical `(company_normalized, title_normalized, location_country)`. Not a
  free-text `location` blob (§6.3). This is the key JustHireMe does not have at all (§6.16).
- **`fingerprint`** — **advisory.** 64-bit SimHash over 3-token shingles, 16 hex chars, compared within a
  90-day window at a 0.92 threshold (`fingerprint-core.mjs:1-35`). It attaches
  `possible_duplicate_of: str | None` to the record and drops nothing.

### 7.5 The filter chain

Career-ops's order is right — cheap local predicates before expensive ones, and dedup last (§2.5). Keep the
order and change two things: every step returns **a reason code**, and every reason code is **counted**.

```python
REASON_ORDER = (
    "blacklisted", "title", "tier", "location", "age", "date_window",
    "salary", "content", "country", "visa",
    "dup_url", "dup_role", "cooldown",
)

@dataclass
class FilterVerdict:
    keep: bool
    reason: str | None          # one of REASON_ORDER, or None when kept
    detail: str | None = None   # human-readable, for the ledger
```

Two things this buys that career-ops pays for elsewhere:

- **One run record with per-reason counts** collapses career-ops's `scan-runs.tsv` + `portal-health.tsv` +
  the log array + the separate `verify-portals.mjs`/`audit-portals.mjs` scripts (§6.6) into a single row and a
  single endpoint. "Is this scan broken or is the market quiet?" becomes one query.
- **A filter that drops everything is visible.** A zero-count `passed` with a large `title` count is a config
  bug; a large `blacklisted` count is correct behaviour. Career-ops cannot distinguish these without reading
  three files.

The dedup steps stay last, after the cheap predicates, so a duplicate never pays for a content check.
Cooldown stays final and reads the scan ledger (§7.8), not a separate file.

### 7.6 Ranking — the synthesis of §5.1 and §5.7, with §6.21 fixed

This is the one place where the two projects combine rather than one being chosen. JustHireMe's structure is
the better one (§3.5): a deterministic rubric computes the score, an LLM may refine it, and hard caps
re-impose ceilings **after** the model runs. Take the structure; fix the hole.

```python
@dataclass(frozen=True)
class Criterion:
    name: str
    weight: float
    def score(self, p: Posting, ctx: ScoringContext) -> CriterionScore: ...

@dataclass(frozen=True)
class Cap:
    id: str
    ceiling: float
    applies: Callable[[Posting, list[CriterionScore]], bool]
    reason: str
    reimpose_after_llm: bool = True
```

**One registry, and `_hard_cap` is derived from it rather than hand-written.** That is the fix for §6.21:
JustHireMe re-imposed only the wrong-field and seniority caps, so the stack and thin-posting caps could be
lifted by the model. The mechanism should make that class of omission impossible:

```python
def apply_caps(base: float, scores, cap_registry) -> tuple[float, list[str]]:
    """Conjunctive ceilings. Tightest wins; every binding cap reports its reason."""
    fired = [c for c in cap_registry if c.applies(posting, scores)]
    if not fired:
        return base, []
    binding = min(fired, key=lambda c: c.ceiling)
    return min(base, binding.ceiling), [c.reason for c in sorted(fired, key=lambda c: c.ceiling)]

def reimpose_after_llm(llm_score: float, scores, cap_registry) -> tuple[float, list[str]]:
    """Every cap with reimpose_after_llm=True is re-applied post-model. No exceptions."""
    return apply_caps(llm_score, scores, [c for c in cap_registry if c.reimpose_after_llm])
```

Start with JustHireMe's caps as the initial registry — wrong field 15; seniority 30/38/45/48 by direction;
no direct stack 52 or 42; thin posting 68 (`scoring_engine.py:655-680`) — and note that the numbers are
*theirs*, tuned for their candidate and their market. They are a starting point to be re-tuned against
CareerHelper's own data, not a transferable constant. What transfers is the shape: `min()` over conjunctive
ceilings, reasons ordered by tightness so the reported reason is the *binding* one.

**Determinism rules that come with the shape:**

- Every cap in the registry is re-imposed post-LLM unless it is explicitly opted out *and* the opt-out is
  justified in a comment. Default-on, because the failure mode is a silent promotion.
- `scored_by ∈ {"deterministic", "prefiltered_off_field", "llm", "deterministic_fallback"}` is recorded on
  every result, so a wrong score is attributable to a stage (§5.1).
- The LLM refinement is **bounded to a delta** and cannot move a score across a cap that fired. A refinement
  that would cross a ceiling is clamped, and the clamp is recorded.
- Feedback adjustment uses **one scale**, not two (§6.22). Pick a maximum magnitude and enforce it in one
  place; two independently-chosen scales (±18 / ±12) sitting under caps that bind at 15 is how a "ranking
  tweak" silently inverts a ceiling.
- Derived scores are recomputed from stored bases, never incrementally mutated (§5.20), so changing a weight
  is a recompute rather than a migration.
- If the embedding or model backend degrades, the result says so — `degraded: bool` plus a reason (§5.21).
  CareerHelper's version of this is sharper than JustHireMe's, because a degraded tailoring run is about to be
  sent to an employer.

**Explainability is a field, not a formatted string** (§5.6):

```python
class CriterionScore(BaseModel):
    name: str
    score: float
    weight: float
    reason: str

class ScoreResult(BaseModel):
    total: float
    criteria: list[CriterionScore]
    applied_cap: str | None
    cap_reasons: list[str]
    scored_by: Literal["deterministic", "prefiltered_off_field", "llm", "deterministic_fallback"]
    degraded: bool = False
    degraded_reason: str | None = None
```

The Next.js side renders `criteria` and `applied_cap` directly — no parsing, no string munging, and
"why is this low?" is answered by the payload rather than by a second request.

### 7.7 Configuration

Career-ops's config is powerful and has a 2,792-line example file and five integration levels (§6.12). The
entry cost is the problem, not the capability. Aim for a schema where **the common case is one line and the
uncommon cases are documented but absent:**

```yaml
# config/portals.yml
version: 1

scan:
  concurrency: 10
  max_posting_age_days: 45
  recheck_after_days: 120           # how long a skipped_expired stays suppressed
  extractor: http                    # http (default) | browser (opt-in, serialized)

filters:
  title_include: ["engineer", "manager", "program"]
  title_exclude: ["intern", "unpaid"]
  tiers: { include: [1, 2], exclude: [] }
  locations:
    accept: ["Remote", "US", "EU"]
    work_models: ["remote", "hybrid"]
  salary:
    min: null
    currency: "USD"
  content_block: ["unpaid", "for exposure", "equity only"]

companies:
  # auto-detect: nothing but the name
  - name: Stripe

  # explicit provider when detection is ambiguous or the entry got stolen once (§6.4)
  - name: Acme
    provider: greenhouse
    company_slug: acme

  # a raw endpoint, no provider registry involved
  - name: Example
    careers_url: https://example.com/careers

boards:
  - name: RemoteOK
    provider: remoteok
```

Three rules that keep this from growing into 2,792 lines:

- **`detect()` covers the default path**, so adding a company is one key. The explicit `provider:` exists for
  the cases §6.4 describes, and it *wins*, so a mis-detection is always correctable in config.
- **Provider-specific keys live under a namespaced sub-key**, never at the top level. The runner does not read
  them; only the provider does. `PortalEntry` stays opaque to the orchestrator.
- **Validate on load, and surface the reason.** A bad provider id, an unreachable `careers_url`, or a
  `company_slug` that no provider accepts is a startup error with a message naming the entry. Career-ops's
  warn-and-skip (§7.2) means a typo'd company is simply never scanned, and the only evidence is its absence.

### 7.8 Persistence

The two projects disagree and the disagreement is worth resolving deliberately rather than by default.
`docs/nextjs-fastapi-plan.md` commits to *"SQLite and local files … for the local-first version"*.
`ARCHITECTURE.md:22-24` in career-ops commits harder: *"the human-readable, git-diffable files … are the
permanent source of truth. SQLite exists only as a derived index … and will never become a primary store —
not even opt-in."*

A defensible synthesis, flagged in §8 as a decision rather than a conclusion:

- **Generations** stay in SQLite, per the plan. They are also artifacts on disk (`resources/output/*.pdf`,
  `resources/workspace/*.tex`), so the database is an index over files that exist independently. That is
  already consistent with the career-ops doctrine.
- **The discovery ledger is append-only JSONL**, one record per posting seen, plus one record per run. It is
  greppable, diffable, and never rewritten. Career-ops's positional TSV works but needs index-fallback logic
  once a column is added (§6.10's fate); JSONL with a `schema` field per record does not.
- **Derived discovery queries** (dedup lookups, the cooldown check, the ranking queue) read a SQLite index
  built from the ledger. Rebuildable at any time. This is the part that must **not** become the source of
  truth — same reasoning as career-ops's, and it costs nothing to honour.
- **Writes are serialized.** FastAPI serves concurrent requests and the ledger is read-modify-write
  (§5.11). One lock or one writer task; and any allocated identifier — a generation id, a report number — is
  reserved atomically via `os.open(path, os.O_CREAT | os.O_EXCL)` with a staleness sweep, never `max + 1`
  (§5.12).

### 7.9 Verification plan

Ordered by when it should exist, not by importance.

1. **Provider contract conformance test** (§5.3, §7.2). Enumerate every module in `providers/`, assert each
   satisfies the Protocol, assert ids are unique, assert no provider reaches for the HTTP client directly.
   This is the test that would have prevented JustHireMe's `Source` Protocol from becoming decorative (§6.15).
2. **Cap registry test** (§6.21). Assert that the set of caps re-imposed after the LLM equals the set of
   registered caps with `reimpose_after_llm=True`. Adding a cap without registering it for re-imposition must
   fail CI. This is the single highest-value test in the ranking layer, because §6.21 is exactly the bug that
   no other test catches.
3. **Filter chain, no network.** Pure functions over fixture `Posting` objects; assert reason codes and
   ordering. Cheap, fast, and it pins the order so a refactor cannot silently reorder dedup before content.
4. **Dedup property tests.** Assert the asymmetry: over-normalizing never happens, an unnormalizable URL
   yields `None` and never collapses with another `None`, and distinct postings never share `dedup_key_role`.
   The doctrine is a decision rule, so it is testable as one.
5. **SSRF and URL guard tests** (§5.18). Every fetch path, including redirects, rejects private and invalid
   addresses. CareerHelper takes user-supplied job URLs from the browser, so this is reachable by user input
   from day one.
6. **Golden eval cases for ranking** — JustHireMe's discipline, which is genuinely good (§3.5): JSONL cases
   through the production scorer asserting score bands, whether a cap fired, and `invariant: true` cases as CI
   guarantees with an accuracy floor.
7. **A rank-order metric to accompany them** (§6.31). Bands alone let a change reorder the top of the list
   while every score stays in range. One number — nDCG@10 over a small hand-labelled set, or even
   precision@5 — closes that gap. Without it, the golden cases are necessary but not sufficient.
8. **`doctor` with deterministic `--json`** (§5.25). Reports `pdflatex`, the canonical resume, the API key,
   model reachability, and each source's health. Small code, and it makes "it returned nothing" a diagnosable
   state rather than a shrug.
9. **Per-source status in the API and the UI** (§5.15). Every discovery result carries
   `status ∈ {ok, blocked, rate_limited, error, empty}` and a detail string. A blocked source and a quiet
   market must not render identically.
10. **Tests auto-discovered, with a guard test** (§5.24). Pytest collection with no registration list, plus a
    test asserting that discovery has not been downgraded to a hand-maintained list.

### 7.10 Deliberate non-goals

Naming these now is cheaper than arguing about them later:

- **No auto-apply.** CareerHelper's scope (`README.md`) is tailoring and PDF generation. JustHireMe's
  `actuator.py` shows what the safety machinery costs when the click is automated (§5.18). If it is ever
  added, it needs its own design pass — centralized default-deny decision, opt-in flag, per-call-site audit —
  not a feature flag on an existing path.
- **No embeddings in v1** (§6.11). Ship the SimHash fingerprint (§5.9) and the deterministic rubric; keep the
  storage contract open so a semantic layer can be added as a re-scoring pass rather than a rewrite. When it
  is added, publish the blend (§5.28) and version the calibration, because stretch windows sized for one
  embedding model silently mis-score another (§6.23).
- **No LLM tokens in discovery.** Discovery is deterministic and free; tailoring is where the model is spent
  (§5.8, §5.13).
- **No multi-user, no Postgres, no durable worker** until the plan's Phase 5, per `docs/nextjs-fastapi-plan.md`.
- **No writing into the user's canonical resume path.** Generation writes to `resources/workspace/` and
  `resources/output/`; the canonical LaTeX is read-only input (§5.22).

---

## 8. Open decisions, and what remains unverified

This document deliberately stops short of three things: choosing what CareerHelper should be, guessing at
numbers that need your data, and presenting child-reported findings as established facts. This section is the
first two; §8.11 is the third.

Each item names the decision, the real options, the tradeoff, and — where I have a view — what I would pick and
why. A view is not an instruction; every one of these is reversible except §8.1, which is why it is first.

### 8.1 The scope question that gates everything else

All of §7 assumes CareerHelper grows a discovery stage. That is one of three coherent products:

- **Tailoring only** (today's scope, per `README.md`): paste a job description, get a tailored PDF. §2–§6 then
  becomes reference material about how two other people solved a problem you are not solving. Cheap, focused,
  and defensible — the pipeline already works.
- **Discovery → tailoring** (§7.1–§7.10): CareerHelper finds postings, ranks them, you pick one, it tailors.
  The largest capability gain per line of code, because the tailoring end already exists and discovery is the
  part that is tedious to do by hand.
- **Discovery → ranking → tailoring → application**: JustHireMe's full span. §5.18 and §6.15 describe what the
  last arrow costs, and it is not small — centralized default-deny submission decisions, per-call-site audits,
  an opt-in gate. Recommend against starting here.

**My view:** stop at the second. Discovery plus ranking is what turns a tailoring tool into something you open
on a Monday morning; automated submission is a different product with a different risk profile, and §7.10
already lists it as a non-goal.

**What I need from you:** whether the second is the target. If it is not, §7 is a design study and §8.2–§8.10
are moot.

### 8.2 Where the `Posting` ledger lives

§7.8 proposes a split: SQLite for generations (following `docs/nextjs-fastapi-plan.md`), append-only JSONL for
the discovery ledger, SQLite as a *derived* index over it. The alternative is uniform: everything in SQLite.

- **Split (JSONL ledger + derived index)**: matches career-ops's doctrine (`ARCHITECTURE.md:22-24`); survives a
  schema change without a migration; a corrupt index is a rebuild, not a data loss. Costs more code — the index
  must be kept current.
- **Uniform SQLite**: simpler, one storage story, and the plan already picks it. But the discovery ledger is
  high-volume append-only event data whose schema is still moving; putting it in the migrations directory makes
  every column addition a numbered migration, and §6.10 is what happens when a positional format drifts.

**My view:** the split, because the two datasets genuinely differ in shape — generations are a small table of
durable artifacts, discovery is a large log of observations. But if uniform storage is what gets this built
this month, uniform SQLite is not wrong; it is just less forgiving later.

### 8.3 Number of dedup keys on day one

§7.4 proposes all three (URL gate, company+role gate, SimHash advisory). For fewer: a single normalized-URL key
is trivial and covers most of the real duplicate load. For all three: §6.16 shows what a URL-only key costs —
the same role on the same board reappearing under two URLs, with nothing detecting it.

**My view:** URL key plus company+role key on day one; defer the fingerprint. The first two are roughly 40
lines total and prevent a visible, annoying class of duplicates. The fingerprint requires a `description`,
which §7.3 says discovery often will not have, so it would ship mostly inert.

### 8.4 How much of career-ops's provider registry transfers

The contract (§5.3) and the resolution order (explicit → detect → error) transfer cleanly to Python; §7.2 gives
the shape. The *implementations* do not: career-ops's `providers/*.mjs` are 99 modules written against its own
HTTP client, trust validator, and HTML pipeline, and a Python provider that shells out to them or re-implements
those layers inherits none of the value.

**My view:** port the ATS providers that matter for a resume-tailoring workflow — Greenhouse, Lever, Ashby, and
Workday if you want it (`liveness-api.mjs:330-340` identifies these four as the set whose *public JSON endpoints
return body text*, which is why they are the ones a JD-capture layer can use). Write them Python-native against
one shared `FetchContext`. Skip aggregators and reverse-ATS discovery at first — §6.8 shows that probe cost is
real. Add sources one at a time, each with its own conformance test (§7.9 item 1).

### 8.5 Is there a liveness stage in v1?

§5.2's asymmetric-error doctrine — a false *live* costs one wasted click, a false *dead* discards an opportunity
— is one of the best single ideas in either project, and it is specifically about the liveness verifier. §7 has
no liveness stage, so the doctrine currently has nothing to attach to.

- **No liveness in v1**: postings are ranked and you click through. A dead link costs a click. Simplest.
- **Liveness from the start**: catches expired postings before they reach the ranking queue, at the cost of a
  headless browser plus the classifier fragility §6.7 describes and the `⚠` anchors in §8.11 list.

**My view:** no liveness in v1, but write the doctrine down where the decision would live (§5.2), so that
whenever a liveness check is added it inherits asymmetric error handling instead of inventing a symmetric one.
The value is the doctrine, not the browser.

### 8.6 The initial cap registry and its ceilings

§7.6 adopts JustHireMe's *structure* — conjunctive `min()` ceilings, reasons ordered by tightness, every cap
re-imposed post-LLM — and explicitly does not adopt their numbers. Their ceilings (wrong field 15; seniority
30/38/45/48; no direct stack 52 or 42; thin posting 68, `scoring_engine.py:655-680`) were tuned for their
candidate and their market.

**My view:** start from their *shapes* — a wrong-field cap, a seniority cap, a stack cap, a thin-posting cap;
those four categories are right — and set the ceilings against your own labelled set. Expect the seniority
numbers to need the most work; they are the ones most sensitive to the candidate's actual level.

### 8.7 How to reconcile the two feedback scales

§6.22 records a genuine internal contradiction in JustHireMe: one path applies feedback on a ±18 scale and
another on ±12, and because §7.6 adopts conjunctive `min()` ceilings, a ±18 nudge can lift a posting that a
ceiling had just capped — the cap and the correction fight, and the correction wins.

The options are to pick one scale, to keep both but clamp the *sum* before re-applying caps, or to accept it as
noise on the grounds that feedback is advisory.

**My view:** one scale, one maximum magnitude, enforced in one function that every adjustment path must call.
The specific number matters less than the fact that there is exactly one place it can be changed. §7.6 already
requires caps to be re-applied after the LLM step; this is the same discipline applied to the deterministic
step, and it is cheap — a clamp is a line.

### 8.8 A rank-order metric alongside the golden bands

§6.31 notes that six JSONL eval files assert *bands* — that a posting scores within a range — and nothing
asserts *order*: that posting A outranks posting B. Bands are necessary but they are the easier half. A ranking
system can land every posting inside its band and still put the wrong one on top, and that is precisely the
failure a rank-based product cannot detect about itself.

**My view:** add one ordering metric. nDCG@10 if you label more than about thirty postings and care about the
top several; precision@5 or a plain pairwise-accuracy count if you label twenty to thirty and mostly care about
the first screen. Both are roughly fifty lines over the existing eval harness (§7.9 item 7), and the label set
does not need to be large — twenty to thirty hand-scored postings from your own search is enough to make the
metric move meaningfully. Bands stay; the ordering metric is added beside them, not instead of them.

### 8.9 Where discovery gets documented

`docs/nextjs-fastapi-plan.md` (read in full, 10,070 bytes) is the project's live plan. It defines phases 1–5,
all of which are about tailoring: templates, generations, SSE progress, PDF and `.tex` retrieval. Discovery
appears nowhere in it. This document is therefore currently the only place a discovery design exists.

- **Amend the plan now**, adding a discovery phase before or beside the tailoring phases: keeps one plan, but
  commits to §8.1 before you have answered it, and the plan is the artifact other people read.
- **Keep it here, promote later**: this document stays a study; when §8.1 is settled, whichever sections survive
  get moved into the plan as a phase, and this file becomes the appendix the plan links to.

**My view:** the second. The plan's own structure — phases with concrete endpoints, storage, and a parity
criterion — is the right home for an accepted design and the wrong home for an undecided one. Do not lengthen
the plan until §8.1 has an answer; when it does, §7.1 becomes the phase entry and the rest of §7 stays here as
the rationale the phase cites.

### 8.10 Whether to adopt career-ops's file-canonical doctrine wholesale

`ARCHITECTURE.md:22-24` states the strongest version of the idea: the human-readable, git-diffable files are
"the **permanent source of truth**", SQLite "exists only as a derived index … and will never become a primary
store — not even opt-in." `docs/nextjs-fastapi-plan.md` picks SQLite for generations instead. §7.8 resolves the
tension as a synthesis: durable artifacts plus a rebuildable index.

- **Adopt it wholesale**: files canonical everywhere. Maximum portability, git-diffable history, no migration
  story needed. Costs: queries over a growing table get slow, and concurrent writes need the locking discipline
  §5.18 describes.
- **Adopt the reasoning, not the absolutism**: derived indexes, durable and inspectable artifacts, a schema you
  can rebuild from scratch — but the primary store is whatever fits the access pattern.

**My view:** the reasoning, not the absolutism. The career-ops doctrine is correct *for career-ops*, and the
document says why: the Go dashboard, the Next.js app, community plugins and thousands of forks all read those
files independently, so the files must be the contract. That is a multi-consumer argument. CareerHelper has one
consumer. Copying the rule without the reason buys portability you are not using in exchange for query and
concurrency costs you are. What is worth copying is the discipline underneath it — that every derived index is
disposable, and that a human can read the record of what happened without opening a database.

### 8.11 What in this document is not verified

This section exists because a design study is only as good as its weakest citation, and several of the citations
here came from delegated exploration rather than from reading the file in this session. Nothing below changes
the shape of §7, but each item is a place where a claim rests on a line range nobody has independently
re-confirmed. Section 0's reading convention applies: anything flagged as unverified or uncertain in §2 through
§8.10 is listed here by implication, and the twenty-one unverified markers already placed across those
sections are the fine-grained version of this list.

**Anchor line numbers that were not read first-hand.** These are cited in §2, §3, §5 and §6 but came from
child self-reports whose summaries carried no verified command or test receipt:

- JustHireMe: `evaluator.py:211-260` (`_hard_cap`); `actuator.py:249-271` and `:277-357`;
  `quality_gate.py:79-116`; `scout.py:93-107`; `free_scout.py:118-127` and `:300-335` and `:369-377`;
  `discovery.py:550`; `leads.py:851`; `query_gen.py:229-392`; `sources/common.py:33-55` and `:104-124`.
- career-ops: the mid-`main()` body of `scan.mjs` between roughly `:3104` and `:3200`; and in
  `liveness-api.mjs`, the exact line numbers for `classifyAshbyBoard`, `classifyLinkedInPosting`, and
  `throttleProviderRequest`.

Line numbers in this document that I did read directly are the ones listed under EVIDENCE-style anchors in §2
and §6 — `providers/_types.js:163-178`, `providers/_registry.mjs:23-59` and `:76-107`, `scan.mjs:122` and
`:1325-1340` and `:3155-3205`, `url-key.mjs:1-34`, `fingerprint-core.mjs:1-35`, `liveness-core.mjs` classifier
and doctrine ranges, `liveness-api.mjs:330-340`, `scoring_engine.py` ranges, `quality_gate.py:1-40`,
`lead_intel.py:70-118`, `discovery.py:265-300`, the four migration files, `templates/states.yml`, and
`docs/nextjs-fastapi-plan.md` in full.

**Open questions rather than merely imprecise citations.** Two items are genuinely unsettled, not just
unconfirmed:

- **Whether career-ops's `ATS_PROVIDERS` still contains a Microsoft entry.** A comment at `liveness-api.mjs:331`
  refers to Microsoft, but a search for provider ids returned only five — at `:70`, `:80`, `:98`, `:125`, `:151`
  — and none of them is Microsoft. The likely reading is that the comment is stale and the entry was removed;
  that is `⚠ uncertain`, and it does not affect §7, which ports only the four body-text ATS providers named at
  `liveness-api.mjs:330-340`.
- **Whether `scan.mjs`'s cooldown and `recheck_after_days` are one mechanism or two.** Both are cited in §2.5
  and §5.14 from the same file but from different reads, and the relationship between them was never pinned
  down. Treat them as two independent ideas that may or may not compose.

**Files characterized but not read.** Their behavior is described in §2–§6 from secondary reference, not from a
direct read: career-ops `remotive.mjs`, `weworkremotely.mjs`, `jobspresso.mjs`, `hackernews.mjs`,
`providers/_html-entities.mjs`, `merge-tracker.mjs`, `tracker-utils.mjs`, `tracker-parse.mjs`,
`pipeline-lock.mjs`, `plugins.mjs` and its internals (`_engine.mjs`, `_registry.mjs`, `_lock.mjs`),
`docs/SCRIPTS.md`, `docs/FAQ.md`, `docs/PLUGINS.md`, `modes/patterns.md`, and `modes/apply.md`; also roughly
seventeen CI workflows, which were sampled rather than read. None of these is load-bearing for §7 — they
support color in §2 and §5.

**Environment facts that limit the evidence base.** `rg` is not available on an allowlisted path, so searches
fell back to `grep`; `grep -E` and multi-pattern `grep` were rejected by the read-only shell grammar, as was
`ls -R`; and `git grep` returns nothing for these subtrees, meaning `inspiration/career-ops` and
`inspiration/JustHireMe` are untracked or ignored by the outer repository, so no `git log` provenance was
available for any file in either.

**A structural fact worth stating outright.** `career-ops/data/` in this clone contains only `.gitkeep`,
`offers/`, and `parser-output/`. There is no `applications.md` and no `pipeline.md`. Every claim in §2.7 and
§5.11 about the tracker's columns and header therefore comes from the code that writes and reads them —
`tracker.mjs:107-108` — and not from a live instance of the table. The header is code here, not data.

**The five delegated reports underlying §2, §3 and parts of §5 and §6** are retained as artifacts
(`art_sa_agent_d7f139e4_report`, `art_sa_agent_7cd9d674_report`, `art_sa_agent_955da7c5_report`,
`art_sa_agent_681dbf74_report`, and the consolidated `art_sa_agent_7198e7e8_report`) and every one of them is
`self_report_only` — no verified command or test receipt is attached to any. Within the consolidated report, the
items it tags `[C:qN]` come from its own five children and were not re-verified by it either. The safest way to
use this document is as a map: it names which files matter and what they are for, and every anchor it gives is
worth one direct read before anything is built on it.
