"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import type { Generation, ProgressEvent } from "@/lib/types";

const ORDER = [
  "queued",
  "preparing_prompt",
  "calling_kimi",
  "validating_latex",
  "compiling_pdf",
  "completed",
] as const;

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  preparing_prompt: "Preparing prompt",
  calling_kimi: "Calling Kimi K3",
  validating_latex: "Validating LaTeX",
  compiling_pdf: "Compiling PDF",
  completed: "Completed",
};

function stageIndex(stage: string): number {
  const index = ORDER.indexOf(stage as (typeof ORDER)[number]);
  return index === -1 ? 0 : index;
}

interface GenerationProgressProps {
  initial: Generation;
}

export default function GenerationProgress({ initial }: GenerationProgressProps) {
  const router = useRouter();
  const [status, setStatus] = useState<string>(initial.status);
  const [stage, setStage] = useState<string>(initial.stage);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [errorCode, setErrorCode] = useState<string | null>(
    initial.error_code ?? null,
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(
    initial.error_message ?? null,
  );
  const [streamError, setStreamError] = useState<string | null>(null);
  const refreshed = useRef(false);

  const isTerminal = status === "completed" || status === "failed";

  useEffect(() => {
    if (isTerminal) {
      return;
    }

    const url = `/api/generations/${encodeURIComponent(initial.id)}/events`;
    const source = new EventSource(url);

    const handle = (raw: MessageEvent<string>) => {
      let parsed: ProgressEvent;
      try {
        parsed = JSON.parse(raw.data) as ProgressEvent;
      } catch {
        return;
      }
      setEvents((previous) => [...previous, parsed]);
      if (parsed.stage) setStage(parsed.stage);
      if (parsed.status) setStatus(parsed.status);
      if (parsed.error_code) setErrorCode(parsed.error_code);
      if (parsed.error_message) setErrorMessage(parsed.error_message);

      if (
        parsed.stage === "completed" ||
        parsed.stage === "failed" ||
        parsed.status === "completed" ||
        parsed.status === "failed"
      ) {
        source.close();
        setStreamError(null);
        if (!refreshed.current) {
          refreshed.current = true;
          router.refresh();
        }
      }
    };

    source.addEventListener("progress", handle as EventListener);
    source.onerror = () => {
      // EventSource reconnects automatically; surface a soft notice meanwhile.
      setStreamError(
        "Live updates were interrupted. Retrying automatically…",
      );
    };

    return () => {
      source.close();
    };
  }, [initial.id, isTerminal, router]);

  const reachedIndex = useMemo(() => {
    let highest = stageIndex(stage);
    for (const event of events) {
      highest = Math.max(highest, stageIndex(event.stage));
    }
    if (status === "completed") highest = ORDER.length - 1;
    return highest;
  }, [events, stage, status]);

  const percent = useMemo(() => {
    const last = events[events.length - 1];
    if (last?.percent != null) return last.percent;
    if (status === "completed" || status === "failed") return 100;
    return Math.round((reachedIndex / (ORDER.length - 1)) * 100);
  }, [events, reachedIndex, status]);

  const failed = status === "failed";
  const completed = status === "completed";

  return (
    <>
      <section className="card">
        <div className="btn-row" style={{ justifyContent: "space-between" }}>
          <span className={`badge badge--${status}`}>
            {failed ? "Failed" : completed ? "Completed" : "In progress"}
          </span>
          <span className="muted">{percent}%</span>
        </div>

        {streamError && !isTerminal ? (
          <p className="muted" style={{ marginTop: "0.75rem" }}>
            {streamError}
          </p>
        ) : null}

        <ol className="timeline">
          {ORDER.map((item, index) => {
            const isError = failed && index === reachedIndex;
            const isDone = index < reachedIndex || (completed && index === reachedIndex);
            const isActive = !isDone && !isError && index === reachedIndex && !isTerminal;
            const className = isError
              ? "is-error"
              : isDone
                ? "is-done"
                : isActive
                  ? "is-active"
                  : "";
            return (
              <li key={item} className={className}>
                <span className="marker" aria-hidden="true" />
                <div>
                  <div className="label">{STAGE_LABELS[item]}</div>
                  <div className="detail">
                    {isError
                      ? errorMessage ?? "Generation failed"
                      : isDone
                        ? "Done"
                        : isActive
                          ? "In progress…"
                          : "Pending"}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>

        <dl className="meta-grid">
          <div>
            <dt>Model</dt>
            <dd>{initial.model ?? "—"}</dd>
          </div>
          <div>
            <dt>Prompt tokens</dt>
            <dd>{initial.prompt_tokens ?? "—"}</dd>
          </div>
          <div>
            <dt>Completion tokens</dt>
            <dd>{initial.completion_tokens ?? "—"}</dd>
          </div>
          <div>
            <dt>Started</dt>
            <dd>{initial.started_at ?? "—"}</dd>
          </div>
        </dl>
      </section>

      {failed ? (
        <section className="card" aria-live="polite">
          <h2>Generation failed</h2>
          <p className="form-error" role="alert" style={{ marginBottom: 0 }}>
            {errorCode ? <strong>{errorCode}: </strong> : null}
            {errorMessage ?? "The backend reported an error."}
          </p>
          <div className="btn-row" style={{ marginTop: "1rem" }}>
            <Link className="btn btn--secondary" href="/">
              Start another generation
            </Link>
            <Link className="btn btn--secondary" href="/history">
              View history
            </Link>
          </div>
        </section>
      ) : null}

      {completed ? (
        <section className="card">
          <h2>Result</h2>
          <p className="muted">
            Preview the tailored resume below, or download the PDF and LaTeX
            source.
          </p>
          <div className="btn-row" style={{ marginBottom: "1rem" }}>
            <a
              className="btn"
              href={`/api/generations/${encodeURIComponent(initial.id)}/pdf?download=1`}
              download
            >
              Download PDF
            </a>
            <a
              className="btn btn--secondary"
              href={`/api/generations/${encodeURIComponent(initial.id)}/tex`}
            >
              Download LaTeX
            </a>
            <Link className="btn btn--secondary" href="/">
              Start another generation
            </Link>
          </div>
          <iframe
            className="pdf-frame"
            title="Tailored resume PDF preview"
            src={`/api/generations/${encodeURIComponent(initial.id)}/pdf`}
          />
        </section>
      ) : null}
    </>
  );
}
