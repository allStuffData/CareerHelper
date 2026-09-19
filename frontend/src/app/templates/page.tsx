import Link from "next/link";

import { ApiError, listTemplates } from "@/lib/api";
import type { Template } from "@/lib/types";

export const dynamic = "force-dynamic";

function TemplateCard({ template }: { template: Template }) {
  return (
    <article className="card">
      <h2 style={{ marginBottom: "0.25rem" }}>{template.name}</h2>
      {template.original_filename ? (
        <p className="muted" style={{ marginBottom: "0.5rem" }}>
          {template.original_filename}
        </p>
      ) : null}
      <dl className="meta-grid">
        <div>
          <dt>Active version</dt>
          <dd>{template.active_version ?? "—"}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{template.updated_at ?? template.created_at ?? "—"}</dd>
        </div>
      </dl>
      <div className="btn-row" style={{ marginTop: "1rem" }}>
        <Link className="btn" href={`/?template=${template.id}`}>
          Use this template
        </Link>
      </div>
    </article>
  );
}

export default async function TemplatesPage() {
  let templates: Template[] = [];
  let available = true;
  let error: string | null = null;

  try {
    const result = await listTemplates();
    templates = result.templates;
    available = result.available;
  } catch (caught) {
    error =
      caught instanceof ApiError
        ? caught.message
        : "Could not load templates.";
  }

  return (
    <>
      <h1 className="page-title">Templates</h1>
      <p className="page-subtitle">
        Canonical resumes used as the starting point for tailoring.
      </p>

      {error ? (
        <div className="status-banner status-banner--error" role="status">
          <div>
            <strong>Could not load templates</strong>
            <p style={{ margin: "0.25rem 0 0" }}>{error}</p>
          </div>
        </div>
      ) : null}

      {!available && !error ? (
        <div className="card">
          <div className="empty-state">
            <h2>Template management is not available yet</h2>
            <p>
              The backend does not currently expose the template API. Every
              generation uses the canonical resume configured on the server.
            </p>
            <Link className="btn" href="/">
              Back to generation
            </Link>
          </div>
        </div>
      ) : null}

      {available && templates.length === 0 && !error ? (
        <div className="card">
          <div className="empty-state">
            <h2>No templates saved</h2>
            <p>Upload a canonical resume in a future release.</p>
          </div>
        </div>
      ) : null}

      {available
        ? templates.map((template) => (
            <TemplateCard key={template.id} template={template} />
          ))
        : null}
    </>
  );
}
