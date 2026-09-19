import { NextResponse } from "next/server";

import { apiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Same-origin proxy for the generated PDF.
 *
 * Without `?download=1` the response is `inline`, so it can be embedded in the
 * preview iframe (the backend serves it as an attachment). With
 * `?download=1` the backend's attachment filename is preserved.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const download = new URL(request.url).searchParams.get("download") === "1";
  const upstreamUrl = `${apiBaseUrl()}/api/generations/${encodeURIComponent(
    id,
  )}/pdf`;

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
    return new NextResponse(detail || "PDF not available", {
      status: upstream.status || 502,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const headers = new Headers();
  headers.set("Content-Type", "application/pdf");
  headers.set("Cache-Control", "private, no-store");
  if (download) {
    headers.set(
      "Content-Disposition",
      upstream.headers.get("content-disposition") ??
        `attachment; filename="${id}.pdf"`,
    );
  } else {
    headers.set("Content-Disposition", "inline");
  }

  return new NextResponse(upstream.body, { status: 200, headers });
}
