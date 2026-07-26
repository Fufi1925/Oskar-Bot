/**
 * Backend-for-Frontend proxy.
 *
 * The browser talks ONLY to this route. It never sees `DASHBOARD_API_KEY`.
 * Every request is authorized here, then forwarded to the FastAPI bot API
 * with the secret key attached server-side.
 *
 *   Browser  ──►  /api/bot/guilds/<id>/automod  ──►  FastAPI /api/v1/guilds/<id>/automod
 *                 (session cookie)                    (Bearer DASHBOARD_API_KEY)
 *
 * Authorization rules:
 *   /api/bot/guilds/<id>/...  → user must have Manage Server on <id>
 *   /api/bot/admin/...        → user must be listed in ADMIN_IDS
 *   /api/bot/bot/...          → any signed-in user (read-only status info)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { verifyGuildAccess, verifyAdminAccess, isGlobalAdmin } from "@/lib/guild-auth";

export const dynamic = "force-dynamic";

const API_BASE_URL =
  process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;
const API_KEY = process.env.DASHBOARD_API_KEY || "";

/** Admin endpoints that take a guild_id in the body and act on that guild. */
const GUILD_SCOPED_ADMIN_ACTIONS = new Set(["member-action", "quick-action"]);

/**
 * Admin endpoints every signed-in user may READ. These only expose the global
 * notification banner and the maintenance state, which the dashboard shell
 * renders for everyone. Writes still require admin rights.
 */
const PUBLIC_ADMIN_READS = new Set(["config", "session-policy"]);
/** Endpoints any signed-in user may POST to (telemetry only). */
const PUBLIC_ADMIN_WRITES = new Set(["oauth-error"]);

function deny(status: number, message: string) {
  return NextResponse.json({ detail: message }, { status });
}

async function authorize(
  segments: string[],
  request: NextRequest
): Promise<{ ok: true } | { ok: false; response: NextResponse }> {
  const [scope, ...rest] = segments;

  if (scope === "guilds") {
    // `/guilds` (list) is allowed for any signed-in user — the page filters it
    // down to the servers the user actually administrates.
    const guildId = rest[0];
    if (!guildId) {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
      return { ok: true };
    }

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };
    return { ok: true };
  }

  if (scope === "admin") {
    const action = rest[0] ?? "";

    // Read-only shell data (banner, maintenance state) for any signed-in user.
    if (request.method === "GET" && PUBLIC_ADMIN_READS.has(action)) {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
      return { ok: true };
    }

    if (request.method === "POST" && PUBLIC_ADMIN_WRITES.has(action)) {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
      return { ok: true };
    }

    // Actions that mutate a specific guild: allow guild managers too,
    // but only for the guild named in the request body.
    if (GUILD_SCOPED_ADMIN_ACTIONS.has(action)) {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };

      if (isGlobalAdmin(session.user.id)) return { ok: true };

      let body: any = {};
      try {
        body = await request.clone().json();
      } catch {
        return { ok: false, response: deny(400, "Invalid JSON body.") };
      }
      const guildId = String(body?.guild_id ?? "");
      if (!guildId) return { ok: false, response: deny(400, "guild_id is required.") };

      const access = await verifyGuildAccess(guildId);
      if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };
      return { ok: true };
    }

    const access = await verifyAdminAccess();
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };
    return { ok: true };
  }

  if (scope === "bot") {
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    return { ok: true };
  }

  return { ok: false, response: deny(404, "Unknown API scope.") };
}

async function handler(request: NextRequest, context: { params: { path?: string[] } }) {
  const segments = context.params.path ?? [];
  if (segments.length === 0) return deny(404, "Not found.");

  const auth = await authorize(segments, request);
  if (!auth.ok) return auth.response;

  const search = request.nextUrl.search;
  // Preserve the trailing slash the FastAPI router expects on collection routes.
  const trailing = request.nextUrl.pathname.endsWith("/") ? "/" : "";
  const targetUrl = `${API_BASE_URL}/${segments.join("/")}${trailing}${search}`;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) headers.Authorization = `Bearer ${API_KEY}`;

  let body: string | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    body = await request.text();
  }

  try {
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });

    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error: any) {
    console.error(`[BFF] Upstream request failed for ${targetUrl}:`, error?.message ?? error);
    return deny(502, "Bot API is unreachable. Is the bot running?");
  }
}

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const PUT = handler;
export const DELETE = handler;
