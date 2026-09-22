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
 * Template metadata as returned by `GET /api/templates`.
 *
 * `active_version` is the version NUMBER (not an id); `active_version_id` is the
 * id that `POST /api/generations` expects as `template_version_id`.
 */
export interface Template {
  id: number;
  name: string;
  description?: string | null;
  original_filename?: string | null;
  active_version_id?: number | null;
  active_version?: number | null;
  version_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TemplateVersion {
  id: number;
  template_id: number;
  version: number;
  created_at?: string | null;
  latex_content?: string | null;
}

export interface TemplateDetail extends Template {
  versions: TemplateVersion[];
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

/** Payload for `POST /api/templates` and `POST /api/templates/{id}/versions`. */
export interface CreateTemplateInput {
  name: string;
  description?: string;
  original_filename?: string;
  latex_content: string;
}

/** State returned by the create-template Server Action. */
export interface CreateTemplateState {
  ok: boolean;
  id?: number;
  error?: string;
}

/** State returned by the retry-generation Server Action. */
export interface RetryGenerationState {
  ok: boolean;
  id?: string;
  error?: string;
}
