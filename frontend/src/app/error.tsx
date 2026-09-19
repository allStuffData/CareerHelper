"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the digest for server-side log correlation without leaking data.
    console.error("Client route error", error.digest ?? error.message);
  }, [error]);

  return (
    <div className="card">
      <div className="empty-state">
        <h1>Something went wrong</h1>
        <p>
          The page could not be loaded. The backend may be unavailable, or the
          requested generation no longer exists.
        </p>
        <div className="btn-row" style={{ justifyContent: "center" }}>
          <button type="button" className="btn" onClick={() => reset()}>
            Try again
          </button>
          <Link className="btn btn--secondary" href="/">
            Back to generation
          </Link>
        </div>
      </div>
    </div>
  );
}
