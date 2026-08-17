-- Initial schema for CareerHelper

CREATE TABLE IF NOT EXISTS templates (
    id          TEXT PRIMARY KEY NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_predefined INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS template_versions (
    id              TEXT PRIMARY KEY NOT NULL,
    template_id     TEXT NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    latex_content   TEXT NOT NULL,
    version_number  INTEGER NOT NULL DEFAULT 1,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS generations (
    id                  TEXT PRIMARY KEY NOT NULL,
    template_version_id TEXT NOT NULL REFERENCES template_versions(id),
    company             TEXT NOT NULL DEFAULT '',
    role                TEXT NOT NULL DEFAULT '',
    jd_text             TEXT NOT NULL DEFAULT '',
    llm_prompt          TEXT NOT NULL DEFAULT '',
    llm_response        TEXT NOT NULL DEFAULT '',
    tex_content         TEXT NOT NULL DEFAULT '',
    pdf_path            TEXT,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Index for listing generations by recency
CREATE INDEX IF NOT EXISTS idx_generations_created_at
    ON generations(created_at DESC);

-- Index for looking up versions by template
CREATE INDEX IF NOT EXISTS idx_template_versions_template
    ON template_versions(template_id);
