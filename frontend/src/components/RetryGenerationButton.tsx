"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { retryGenerationAction } from "@/app/actions";

/**
 * Re-run a finished generation.
 *
 * The backend appends a new generation that reuses the original company, role,
 * job description, and template version, so the original row and its artifacts
 * stay in history.
 */
export default function RetryGenerationButton({ id }: { id: string }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const onRetry = () => {
    setError(null);
    startTransition(async () => {
      const result = await retryGenerationAction(id);
      if (result.ok && result.id) {
        router.push(`/generate/${encodeURIComponent(result.id)}`);
        return;
      }
      setError(result.error ?? "Could not retry this generation.");
    });
  };

  return (
    <span>
      <button
        type="button"
        className="btn btn--small"
        onClick={onRetry}
        disabled={isPending}
      >
        {isPending ? "Retrying…" : "Retry"}
      </button>
      {error ? (
        <span className="form-error" style={{ display: "block", marginTop: 6 }}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
