import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { isOwnerId } from "@/lib/guild-auth";
import { isLouckupOrigin as isDashboardOrigin } from "@/lib/owner-louckup";

export const dynamic = "force-dynamic";
const answer = (data: unknown, status = 200) => NextResponse.json(data, { status, headers: { "Cache-Control": "no-store, private" } });

async function handler(request: NextRequest, context: { params: { path: string[] } }) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return answer({ detail: "not_signed_in" }, 401);
  if (!isOwnerId(session.user.id)) return answer({ detail: "owner_required" }, 403);
  const path = context.params.path;
  const allowed = path.length === 1 && (path[0] === "settings" ? ["GET", "PATCH"].includes(request.method) :
    ["revoke-all", "revoke-user"].includes(path[0]) && request.method === "POST");
  if (!allowed) return answer({ detail: "not_found" }, 404);
  if (request.headers.get("sec-fetch-site") === "cross-site" || (request.method !== "GET" && !isDashboardOrigin(request.headers.get("origin"), request.nextUrl.origin))) {
    return answer({ detail: "invalid_origin" }, 403);
  }
  const key = process.env.DASHBOARD_API_KEY;
  if (!key) return answer({ detail: "not_configured" }, 503);
  let body: string | undefined;
  if (request.method !== "GET") {
    if (path[0] === "revoke-all") body = "{}";
    else {
      const raw = await request.text();
      if (raw.length > 1024) return answer({ detail: "invalid_request" }, 400);
      try {
        const data = JSON.parse(raw);
        body = JSON.stringify(path[0] === "settings" ? { scopes: data.scopes } : { user_id: data.user_id });
      } catch { return answer({ detail: "invalid_request" }, 400); }
    }
  }
  try {
    const base = process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;
    const response = await fetch(`${base}/dashboard-settings/${path[0]}`, {
      method: request.method, headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json", "X-Dashboard-Settings-Actor": session.user.id },
      body, cache: "no-store", signal: AbortSignal.timeout(10_000),
    });
    const data = await response.json();
    return answer(response.ok ? data : { detail: typeof data.detail === "string" ? data.detail : "request_failed" }, response.status);
  } catch { return answer({ detail: "service_unavailable" }, 502); }
}

export { handler as GET, handler as PATCH, handler as POST };
