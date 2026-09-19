"use client";

import { useState, useTransition } from "react";

import { deleteGenerationAction } from "@/app/actions";

export default function DeleteGenerationButton({ id }: { id: string }) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const onDelete = () => {
    if (!window.confirm("Delete this generation and its artifacts?")) {
      return;
    }
    setError(null);
    startTransition(async () => {
      const result = await deleteGenerationAction(id);
      if (!result.ok) {
        setError(result.error ?? "Could not delete this generation.");
      }
    });
  };

  return (
    <span>
      <button
        type="button"
        className="btn btn--danger btn--small"
        onClick={onDelete}
        disabled={isPending}
      >
        {isPending ? "Deleting…" : "Delete"}
      </button>
      {error ? (
        <span className="form-error" style={{ display: "block", marginTop: 6 }}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
