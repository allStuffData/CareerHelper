import type { HealthResponse, HealthStatus } from "@/lib/types";

const STATUS_LABEL: Record<HealthStatus, string> = {
  ok: "All systems ready",
  degraded: "Running in a degraded state",
  error: "The API reported an error",
};

function bannerClass(status: HealthStatus): string {
  if (status === "ok") return "status-banner status-banner--ok";
  if (status === "degraded") return "status-banner status-banner--degraded";
  return "status-banner status-banner--error";
}

export default function HealthBanner({ health }: { health: HealthResponse }) {
  const status = health.status;
  return (
    <div className={bannerClass(status)} role="status">
      <div>
        <strong>{STATUS_LABEL[status] ?? "API status unknown"}</strong>
        <ul className="check-list">
          {health.checks.map((check) => (
            <li key={check.name}>
              <span
                className={`dot dot--${check.status}`}
                aria-hidden="true"
              />
              {check.name}: {check.status}
              {check.detail ? ` (${check.detail})` : ""}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
