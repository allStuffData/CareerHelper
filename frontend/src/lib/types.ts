/**
 * TypeScript mirrors of the FastAPI response schemas.
 *
 * Keep these in sync with `backend/app/schemas/*.py`. The backend deliberately
 * does not return the job description, prompt, or resume source in list/detail
 * responses, so these types do not model them either.
 */

export type HealthStatus = "ok" | "degraded" | "error";

export interface HealthCheck {
  name: string;
  status: HealthStatus;
  detail?: string | null;
}

export interface HealthResponse {
  status: HealthStatus;
  version: string;
  checks: HealthCheck[];
}

export type GenerationStatus = "queued" | "running" | "completed" | "failed";

export type GenerationStage =
  | "queued"
  | "preparing_prompt"
  | "calling_kimi"
  | "validating_latex"
  | "compiling_pdf"
  | "completed"
  | "failed";

/** Mirrors `GenerationResponse`. */
export interface Generation {
  id: string;
  company: string;
  role: string;
  status: GenerationStatus;
  stage: GenerationStage;
  model?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  events_url: string;
  pdf_url?: string | null;
  tex_url?: string | null;
}

export interface GenerationListResponse {
  items: Generation[];
  count: number;
}

export interface CreateGenerationInput {
  company: string;
  role: string;
  job_description: string;
  template_version_id?: number | null;
}

/**
 * A single SSE `progress` payload emitted by `GET /api/generations/{id}/events`.
 */
export interface ProgressEvent {
  generation_id: string;
  status: GenerationStatus;
  stage: GenerationStage;
  message?: string | null;
  percent?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  timestamp?: string | null;
  pdf_path?: string;
  pdf_filename?: string;
  tex_path?: string;
  tex_filename?: string;
}

/**
 * Template metadata.
 *
 * NOTE: the Phase 2 backend does not yet expose `/api/templates`; these fields
 * follow the plan's data model and the frontend treats the endpoint as optional.
 */
export interface Template {
  id: number;
  name: string;
  original_filename?: string | null;
  active_version?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TemplateListResponse {
  items: Template[];
  count: number;
}

/** State returned by the create-generation Server Action. */
export interface CreateGenerationState {
  ok: boolean;
  id?: string;
  error?: string;
}

/** State returned by the delete-generation Server Action. */
export interface DeleteGenerationState {
  ok: boolean;
  error?: string;
}
