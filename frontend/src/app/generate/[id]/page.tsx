import { notFound } from "next/navigation";

import GenerationProgress from "@/components/GenerationProgress";
import { ApiError, getGeneration } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function GenerateResultPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let generation;
  try {
    generation = await getGeneration(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  return (
    <>
      <h1 className="page-title">
        {generation.role} at {generation.company}
      </h1>
      <p className="page-subtitle">
        Generation <code>{generation.id}</code>
      </p>
      <GenerationProgress initial={generation} />
    </>
  );
}
