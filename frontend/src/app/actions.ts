"use server";

import { revalidatePath } from "next/cache";

import { ApiError, createGeneration, deleteGeneration } from "@/lib/api";
import type {
  CreateGenerationState,
  DeleteGenerationState,
} from "@/lib/types";

const GENERIC_ERROR = "Could not reach the CareerHelper API.";

function messageFor(error: unknown): string {
  return error instanceof ApiError ? error.message : GENERIC_ERROR;
}

export async function createGenerationAction(
  _previous: CreateGenerationState,
  formData: FormData,
): Promise<CreateGenerationState> {
  const company = String(formData.get("company") ?? "").trim();
  const role = String(formData.get("role") ?? "").trim();
  const jobDescription = String(formData.get("job_description") ?? "").trim();
  const templateRaw = String(formData.get("template_version_id") ?? "").trim();

  if (!company || !role || !jobDescription) {
    return {
      ok: false,
      error: "Company, role, and job description are all required.",
    };
  }

  const templateVersionId = templateRaw ? Number(templateRaw) : null;
  if (templateVersionId !== null && !Number.isInteger(templateVersionId)) {
    return { ok: false, error: "The selected template is not valid." };
  }

  try {
    const generation = await createGeneration({
      company,
      role,
      job_description: jobDescription,
      template_version_id: templateVersionId,
    });
    revalidatePath("/history");
    return { ok: true, id: generation.id };
  } catch (error) {
    return { ok: false, error: messageFor(error) };
  }
}

export async function deleteGenerationAction(
  id: string,
): Promise<DeleteGenerationState> {
  try {
    await deleteGeneration(id);
    revalidatePath("/history");
    return { ok: true };
  } catch (error) {
    return { ok: false, error: messageFor(error) };
  }
}
