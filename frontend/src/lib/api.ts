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
  CreateTemplateInput,
  Generation,
  GenerationListResponse,
  HealthResponse,
  TemplateDetail,
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

/**
 * Decode one dynamic route segment exactly once.
 *
 * Next.js hands the `[id]` param to pages and route handlers still
 * percent-encoded (`%20` for a space), while every consumer below —
 * `getGeneration`, `deleteGeneration`, and the proxy URLs in
 * `src/app/api/generations/[id]/*` — encodes the value again before putting it
 * on the wire. Passing the raw param through therefore double-encodes it
 * (`%20` -> `%2520`) and the backend answers 404 for any generation id
 * containing a space, such as `GopalKumar_Stripe_Technical Program
 * Manager_20260919-3`.
 *
 * Decoding at the route boundary restores the intended asymmetry: the browser
 * encodes once, the server decodes once.
 */
export function decodeRouteParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    // Not a well-formed escape sequence, so it cannot be a real id either.
    // Pass it through and let the backend answer with its own 404.
    return value;
  }
}

/**
 * Make a generation id safe to echo inside an HTTP header value.
 *
 * The id originates from a URL segment, so it must never be able to inject
 * separators or quote out of the fallback `filename="..."` parameter.
 */
export function safeHeaderFilename(value: string, fallback = "artifact"): string {
  const cleaned = value.replace(/[^A-Za-z0-9._ -]/g, "_").trim();
  return cleaned.length > 0 ? cleaned : fallback;
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

export function listTemplates(): Promise<TemplateListResponse> {
  return apiFetch<TemplateListResponse>("/api/templates");
}

export function getTemplate(id: number): Promise<TemplateDetail> {
  return apiFetch<TemplateDetail>(`/api/templates/${encodeURIComponent(String(id))}`);
}

export function createTemplate(input: CreateTemplateInput): Promise<TemplateDetail> {
  return apiFetch<TemplateDetail>("/api/templates", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/**
 * Retry a finished generation.
 *
 * The backend appends a NEW generation that reuses the original company, role,
 * job description, and template version, so history stays append-only and the
 * original run's artifacts and token usage remain intact.
 */
export function retryGeneration(id: string): Promise<Generation> {
  return apiFetch<Generation>(
    `/api/generations/${encodeURIComponent(id)}/retry`,
    { method: "POST" },
  );
}
