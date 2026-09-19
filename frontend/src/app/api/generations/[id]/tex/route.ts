import { NextResponse } from "next/server";

import { apiBaseUrl, decodeRouteParam, safeHeaderFilename } from "@/lib/api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Same-origin proxy for the tailored LaTeX artifact (always a download). */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id: rawId } = await params;
  // Decode exactly once: the browser encoded this segment already.
  const id = decodeRouteParam(rawId);
  const upstreamUrl = `${apiBaseUrl()}/api/generations/${encodeURIComponent(
    id,
  )}/tex`;

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return new NextResponse("Backend unreachable", { status: 502 });
  }

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return new NextResponse(detail || "LaTeX artifact not available", {
      status: upstream.status || 502,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const headers = new Headers();
  headers.set("Content-Type", "application/x-tex; charset=utf-8");
  headers.set("Cache-Control", "private, no-store");
  headers.set(
    "Content-Disposition",
    upstream.headers.get("content-disposition") ??
      `attachment; filename="${safeHeaderFilename(id, "resume")}.tex"`,
  );

  return new NextResponse(upstream.body, { status: 200, headers });
}
