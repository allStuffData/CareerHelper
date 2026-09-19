import GenerateForm from "@/components/GenerateForm";
import HealthBanner from "@/components/HealthBanner";
import { ApiError, getHealth, listTemplates } from "@/lib/api";
import type { HealthResponse, Template } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ template?: string }>;
}) {
  const { template: templateParam } = await searchParams;
  const selectedTemplateId = templateParam ? Number(templateParam) : null;

  let health: HealthResponse | null = null;
  let healthError: string | null = null;

  try {
    health = await getHealth();
  } catch (error) {
    healthError =
      error instanceof ApiError
        ? error.message
        : "Could not reach the CareerHelper API.";
  }

  let templates: Template[] = [];
  let templatesAvailable = false;
  try {
    const result = await listTemplates();
    templates = result.templates;
    templatesAvailable = result.available;
  } catch {
    // The generation form still works with the backend default template.
    templatesAvailable = false;
  }

  return (
    <>
      <h1 className="page-title">Tailor your resume</h1>
      <p className="page-subtitle">
        Paste a job description, pick the target company and role, and generate
        an ATS-optimized one-page PDF.
      </p>

      {health ? (
        <HealthBanner health={health} />
      ) : (
        <div className="status-banner status-banner--error" role="status">
          <div>
            <strong>API unavailable</strong>
            <p style={{ margin: "0.25rem 0 0" }}>
              {healthError} Start the FastAPI backend and reload this page.
            </p>
          </div>
        </div>
      )}

      <GenerateForm
        templates={templates}
        templatesAvailable={templatesAvailable}
        selectedTemplateId={
          selectedTemplateId && Number.isInteger(selectedTemplateId)
            ? selectedTemplateId
            : null
        }
      />
    </>
  );
}
