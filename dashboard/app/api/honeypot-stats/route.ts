import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const base = (process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`).replace(/\/$/, "");
  try {
    const response = await fetch(`${base}/honeypot/live-stats`, {
      headers: { Authorization: `Bearer ${process.env.DASHBOARD_API_KEY || ""}` },
      cache: "no-store", signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) throw new Error("Statistics unavailable");
    const data = await response.json();
    // Publish only aggregate counters, dates and chart points.
    return NextResponse.json({
      total_moderations: data.total_moderations, total_servers: data.total_servers,
      moderations_7d: data.moderations_7d, triggered_servers_7d: data.triggered_servers_7d,
      history: data.history.map((point: any) => ({ day: point.day, moderations: point.moderations, servers: point.servers })),
      tracking_since: data.tracking_since, updated_at: data.updated_at,
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "Live statistics are currently unavailable." },
      { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
