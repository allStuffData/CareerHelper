import { NextResponse } from "next/server";

import { apiBaseUrl, decodeRouteParam } from "@/lib/api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Same-origin SSE proxy for `GET /api/generations/{id}/events`.
 *
 * The browser never needs the backend URL; FastAPI stays on the server side.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id: rawId } = await params;
  // Decode exactly once: the browser encoded this segment already.
  const id = decodeRouteParam(rawId);
  const upstreamUrl = `${apiBaseUrl()}/api/generations/${encodeURIComponent(
    id,
  )}/events`;

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      headers: { Accept: "text/event-stream" },
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return new NextResponse(
      `event: error\ndata: ${JSON.stringify({
        message: "Backend unreachable",
      })}\n\n`,
      {
        status: 502,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache, no-transform",
        },
      },
    );
  }

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return new NextResponse(detail || "Upstream error", {
      status: upstream.status || 502,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
