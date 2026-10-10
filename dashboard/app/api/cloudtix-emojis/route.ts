import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// Only the public, bundled CloudTIX pack. Never expose the bot key, arbitrary
// application lookups, guild emojis or user data through this endpoint.
export async function GET() {
  const base = (
    process.env.API_BASE_URL ||
    `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`
  ).replace(/\/$/, "");
  try {
    const response = await fetch(`${base}/bot/cloudtix-emojis`, {
      headers: {
        Authorization: `Bearer ${process.env.DASHBOARD_API_KEY || ""}`,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error("Emoji catalog unavailable");
    return NextResponse.json(await response.json(), {
      headers: { "Cache-Control": "public, max-age=30" },
    });
  } catch {
    return NextResponse.json(
      { ready: 0, unavailable: true },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
