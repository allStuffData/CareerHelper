import Link from "next/link";

import DeleteGenerationButton from "@/components/DeleteGenerationButton";
import { ApiError, listGenerations } from "@/lib/api";
import type { Generation } from "@/lib/types";

export const dynamic = "force-dynamic";

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function StatusBadge({ generation }: { generation: Generation }) {
  return (
    <span className={`badge badge--${generation.status}`}>
      {generation.status}
    </span>
  );
}

export default async function HistoryPage() {
  let generations: Generation[] = [];
  let error: string | null = null;

  try {
    const body = await listGenerations();
    generations = body.items;
  } catch (caught) {
    error =
      caught instanceof ApiError
        ? caught.message
        : "Could not load generation history.";
  }

  return (
    <>
      <h1 className="page-title">History</h1>
      <p className="page-subtitle">
        Past generations, newest first. Open a result to preview or download it.
      </p>

      {error ? (
        <div className="status-banner status-banner--error" role="status">
          <div>
            <strong>Could not load history</strong>
            <p style={{ margin: "0.25rem 0 0" }}>{error}</p>
          </div>
        </div>
      ) : null}

      <div className="card">
        {generations.length === 0 && !error ? (
          <div className="empty-state">
            <h2>No generations yet</h2>
            <p>Generate a tailored resume to see it listed here.</p>
            <Link className="btn" href="/">
              Generate a resume
            </Link>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Company</th>
                  <th scope="col">Role</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {generations.map((generation) => (
                  <tr key={generation.id}>
                    <td>{generation.company}</td>
                    <td>{generation.role}</td>
                    <td>
                      <StatusBadge generation={generation} />
                    </td>
                    <td className="muted">{formatDate(generation.created_at)}</td>
                    <td>
                      <div className="btn-row">
                        <Link
                          className="btn btn--secondary btn--small"
                          href={`/generate/${encodeURIComponent(generation.id)}`}
                        >
                          Open
                        </Link>
                        {generation.status === "completed" ? (
                          <a
                            className="btn btn--secondary btn--small"
                            href={`/api/generations/${encodeURIComponent(
                              generation.id,
                            )}/pdf?download=1`}
                            download
                          >
                            PDF
                          </a>
                        ) : null}
                        <DeleteGenerationButton id={generation.id} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
