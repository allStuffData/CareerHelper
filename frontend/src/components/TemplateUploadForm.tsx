"use client";

import { useActionState, useState } from "react";

import { createTemplateAction } from "@/app/actions";
import type { CreateTemplateState } from "@/lib/types";

const initialState: CreateTemplateState = { ok: false };

export default function TemplateUploadForm() {
  const [state, formAction, pending] = useActionState(
    createTemplateAction,
    initialState,
  );
  const [latex, setLatex] = useState("");
  const [filename, setFilename] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);

  const onFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setFileError(null);
    const reader = new FileReader();
    reader.onload = () => {
      setLatex(String(reader.result ?? ""));
      setFilename(file.name);
    };
    reader.onerror = () => setFileError("Could not read that file.");
    reader.readAsText(file);
  };

  return (
    <form action={formAction} className="card">
      {state.error ? (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      ) : null}
      {state.ok ? (
        <p className="form-success" role="status">
          Template saved. It is now available in the generator.
        </p>
      ) : null}
      {fileError ? (
        <p className="form-error" role="alert">
          {fileError}
        </p>
      ) : null}

      <div className="field">
        <label htmlFor="name">Name</label>
        <input
          id="name"
          name="name"
          type="text"
          required
          maxLength={200}
          placeholder="Backend resume"
        />
      </div>

      <div className="field">
        <label htmlFor="description">Description</label>
        <input
          id="description"
          name="description"
          type="text"
          maxLength={1000}
          placeholder="Optional note about this version"
        />
      </div>

      <div className="field">
        <label htmlFor="template_file">LaTeX file (.tex)</label>
        <input
          id="template_file"
          type="file"
          accept=".tex,text/plain,application/x-tex"
          onChange={onFile}
          aria-describedby="template-file-hint"
        />
        <span id="template-file-hint" className="hint">
          {filename
            ? `Loaded ${filename} (${latex.length} characters).`
            : "Optional — pick a .tex file to fill the source below."}
        </span>
      </div>

      <input
        type="hidden"
        name="original_filename"
        value={filename}
      />

      <div className="field">
        <label htmlFor="latex_content">LaTeX source</label>
        <textarea
          id="latex_content"
          name="latex_content"
          required
          value={latex}
          onChange={(event) => setLatex(event.target.value)}
          placeholder="\\documentclass{article}…"
        />
        <span className="hint">
          {latex.length} characters. Stored verbatim as the template content.
        </span>
      </div>

      <button className="btn" type="submit" disabled={pending}>
        {pending ? "Saving…" : "Save template"}
      </button>
    </form>
  );
}
