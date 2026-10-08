import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { isOwnerId } from "@/lib/guild-auth";
import { allowedLouckupAction, isLouckupOrigin, ownerBinding, LOUCKUP_COOKIE, LOUCKUP_COOKIE_PATH } from "@/lib/owner-louckup";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function answer(data: unknown, status = 200): NextResponse {
  return NextResponse.json(data, { status, headers: { "Cache-Control": "no-store, private", "Vary": "Cookie" } });
}

async function handler(request: NextRequest, context: { params: { path: string[] } }) {
  const session = await getServerSession(authOptions);
  const userId = session?.user?.id;
  if (!userId) return answer({ detail: "not_signed_in" }, 401);
  if (!isOwnerId(userId)) return answer({ detail: "owner_required" }, 403);
  const parts = context.params.path;
  if (!allowedLouckupAction(parts, request.method)) return answer({ detail: "not_found" }, 404);
  if (request.headers.get("sec-fetch-site") === "cross-site") return answer({ detail: "invalid_origin" }, 403);
  if (request.method === "POST" && !isLouckupOrigin(request.headers.get("origin"), request.nextUrl.origin)) {
    return answer({ detail: "invalid_origin" }, 403);
  }
  const issuedAt = Number(session?.sessionIssuedAtMs);
  if (!Number.isFinite(issuedAt) || issuedAt <= 0) return answer({ detail: "sign_in_again" }, 401);
  const key = process.env.DASHBOARD_API_KEY || "";
  if (!key) return answer({ detail: "not_configured" }, 503);
  const headers: Record<string, string> = {
    Authorization: `Bearer ${key}`, "Content-Type": "application/json",
    "X-Louckup-Actor": userId, "X-Louckup-Session": ownerBinding(userId, issuedAt, key),
    "X-Louckup-Grant": request.cookies.get(LOUCKUP_COOKIE)?.value || "",
  };
  let body: string | undefined;
  if (request.method === "POST") {
    if (parts[0] === "unlock") {
      const raw = await request.text();
      if (raw.length > 256) return answer({ detail: "invalid_code" }, 400);
      try {
        const value = JSON.parse(raw);
        if (typeof value.code !== "string" || !/^[0-9]{6}$/.test(value.code)) return answer({ detail: "invalid_code" }, 400);
        body = JSON.stringify({ code: value.code });
      } catch { return answer({ detail: "invalid_code" }, 400); }
    } else body = "{}";
  }
  const base = process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;
  try {
    const upstream = await fetch(`${base}/owner-louckup/${parts.join("/")}`, {
      method: request.method, headers, body, cache: "no-store", signal: AbortSignal.timeout(25_000),
    });
    const data = await upstream.json();
    if (!upstream.ok) {
      const response = answer({ detail: typeof data.detail === "string" ? data.detail : "request_failed" }, upstream.status);
      const retry = upstream.headers.get("retry-after");
      if (retry) response.headers.set("Retry-After", retry);
      return response;
    }
    const response = answer(parts[0] === "unlock" ? { unlocked: true, expires_at: data.expires_at } : data);
    if (parts[0] === "unlock") {
      if (typeof data.grant !== "string" || !/^[A-Za-z0-9_-]{40,64}$/.test(data.grant)) return answer({ detail: "request_failed" }, 502);
      response.cookies.set(LOUCKUP_COOKIE, data.grant, {
        httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict",
        path: LOUCKUP_COOKIE_PATH, maxAge: 600,
      });
    }
    if (parts[0] === "lock") {
      response.cookies.set(LOUCKUP_COOKIE, "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: LOUCKUP_COOKIE_PATH, maxAge: 0 });
    }
    return response;
  } catch { return answer({ detail: "service_unavailable" }, 502); }
}

export { handler as GET, handler as POST };
