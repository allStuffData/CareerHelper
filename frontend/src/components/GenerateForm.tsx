"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { createGenerationAction } from "@/app/actions";
import type { CreateGenerationState, Template } from "@/lib/types";

const initialState: CreateGenerationState = { ok: false };

interface GenerateFormProps {
  templates: Template[];
  templatesAvailable: boolean;
  selectedTemplateId?: number | null;
}

export default function GenerateForm({
  templates,
  templatesAvailable,
  selectedTemplateId = null,
}: GenerateFormProps) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(
    createGenerationAction,
    initialState,
  );
  const [jobDescription, setJobDescription] = useState("");

  useEffect(() => {
    if (state.ok && state.id) {
      router.push(`/generate/${encodeURIComponent(state.id)}`);
    }
  }, [state, router]);

  const characterCount = jobDescription.trim().length;

  return (
    <form action={formAction} className="card">
      {state.error ? (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      ) : null}

      <div className="field">
        <label htmlFor="job_description">Job description</label>
        <textarea
          id="job_description"
          name="job_description"
          required
          value={jobDescription}
          onChange={(event) => setJobDescription(event.target.value)}
          placeholder="Paste the full job description here…"
          aria-describedby="job-description-hint"
        />
        <span id="job-description-hint" className="hint">
          {characterCount} characters. The more complete the description, the
          better the keyword targeting.
        </span>
      </div>

      <div className="field-grid">
        <div className="field">
          <label htmlFor="company">Company</label>
          <input
            id="company"
            name="company"
            type="text"
            required
            maxLength={200}
            placeholder="Stripe"
            autoComplete="organization"
          />
        </div>

        <div className="field">
          <label htmlFor="role">Role</label>
          <input
            id="role"
            name="role"
            type="text"
            required
            maxLength={200}
            placeholder="Technical Program Manager"
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="template_version_id">Resume template</label>
        <select
          id="template_version_id"
          name="template_version_id"
          defaultValue={
            selectedTemplateId ? String(selectedTemplateId) : ""
          }
        >
          <option value="">Default resume (backend canonical template)</option>
          {templates
            .filter((template) => template.active_version_id != null)
            .map((template) => (
              <option
                key={template.id}
                value={template.active_version_id as number}
              >
                {template.active_version
                  ? `${template.name} (v${template.active_version})`
                  : template.name}
              </option>
            ))}
        </select>
        <span className="hint">
          {templatesAvailable
            ? "Choose a saved template, or use the backend default resume."
            : "No templates could be loaded; the backend default resume will be used."}
        </span>
      </div>

      <button className="btn" type="submit" disabled={pending}>
        {pending ? (
          <>
            <span className="spinner" aria-hidden="true" /> Generating…
          </>
        ) : (
          "Generate resume"
        )}
      </button>
    </form>
  );
}
