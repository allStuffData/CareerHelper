/**
 * Server-side client for the FastAPI backend.
 *
 * This module must only be imported from Server Components, Server Actions, or
 * Route Handlers. The backend base URL lives in `FASTAPI_BASE_URL` and is never
 * exposed to the browser: browser-side progress and artifacts are served
 * through same-origin proxy route handlers (see `src/app/api/generations`).
 *
 * No LLM or LaTeX logic lives here — every business operation is delegated to
 * FastAPI.
 */

import type {
  CreateGenerationInput,
  Generation,
  GenerationListResponse,
  HealthResponse,
  Template,
  TemplateListResponse,
} from "./types";

const DEFAULT_BASE_URL = "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function apiBaseUrl(): string {
  const raw = process.env.FASTAPI_BASE_URL?.trim();
  return (raw && raw.length > 0 ? raw : DEFAULT_BASE_URL).replace(/\/+$/, "");
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (body.detail) {
      return JSON.stringify(body.detail);
    }
  } catch {
    // fall through to text
  }
  try {
    const text = await response.text();
    return text || response.statusText;
  } catch {
    return response.statusText;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Could not reach the CareerHelper API.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/health");
}

export function listGenerations(limit = 50): Promise<GenerationListResponse> {
  return apiFetch<GenerationListResponse>(
    `/api/generations?limit=${encodeURIComponent(String(limit))}`,
  );
}

export function getGeneration(id: string): Promise<Generation> {
  return apiFetch<Generation>(`/api/generations/${encodeURIComponent(id)}`);
}

export function createGeneration(
  input: CreateGenerationInput,
): Promise<Generation> {
  return apiFetch<Generation>("/api/generations", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteGeneration(id: string): Promise<void> {
  return apiFetch<void>(`/api/generations/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/**
 * Templates are optional: the current backend does not implement
 * `/api/templates`, so a 404/405 resolves to `{ available: false }` instead of
 * failing the page.
 */
export async function listTemplates(): Promise<{
  available: boolean;
  templates: Template[];
}> {
  try {
    const body = await apiFetch<TemplateListResponse>("/api/templates");
    return { available: true, templates: body.items ?? [] };
  } catch (error) {
    if (error instanceof ApiError && [404, 405, 501].includes(error.status)) {
      return { available: false, templates: [] };
    }
    throw error;
  }
}
