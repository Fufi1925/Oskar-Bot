/**
 * Route protection.
 *
 * Everything under /dashboard requires a valid NextAuth session. Without this
 * middleware each page had to remember to call getServerSession() itself —
 * and 22 of 23 guild pages did not, which left them publicly reachable.
 *
 * On top of that it enforces the dashboard ban list. A ban has to bite even
 * when the person already holds a valid session cookie, so it is checked here
 * on every navigation as well as in the BFF proxy.
 *
 * Per-guild permission checks happen in the BFF proxy (app/api/bot/[...path])
 * and in the guild layout; this file only enforces "is signed in and not
 * banned".
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { withAuth } from "next-auth/middleware";

const API_BASE_URL =
  process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

/**
 * Tiny cache so a click-heavy user does not trigger one API call per request.
 * Lives per edge instance; 15 seconds is short enough for a ban to feel
 * immediate.
 */
const banCache = new Map<string, { banned: boolean; reason: string; expires: number }>();
const BAN_TTL_MS = 15_000;

async function isBanned(userId: string): Promise<{ banned: boolean; reason: string }> {
  const now = Date.now();
  const cached = banCache.get(userId);
  if (cached && cached.expires > now) return { banned: cached.banned, reason: cached.reason };

  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.Authorization = `Bearer ${key}`;

    const res = await fetch(`${API_BASE_URL}/access/check/${userId}`, {
      headers,
      cache: "no-store",
    });
    if (!res.ok) return { banned: false, reason: "" };

    const data = (await res.json()) as { banned?: boolean; reason?: string };
    const state = { banned: Boolean(data.banned), reason: data.reason || "" };
    banCache.set(userId, { ...state, expires: now + BAN_TTL_MS });
    return state;
  } catch {
    // Fail open: a bot API hiccup must not lock everyone out.
    return { banned: false, reason: "" };
  }
}

export default withAuth(
  async function middleware(request: NextRequest & { nextauth: { token: any } }) {
    const userId = request.nextauth?.token?.sub;
    if (!userId) return NextResponse.next();

    const { banned, reason } = await isBanned(String(userId));
    if (!banned) return NextResponse.next();

    // API calls get a clean 403, page loads get sent to the landing page with
    // an explanation instead of a blank screen.
    if (request.nextUrl.pathname.startsWith("/api/")) {
      return NextResponse.json(
        { detail: reason || "You are banned from this dashboard." },
        { status: 403 }
      );
    }

    const url = new URL("/", request.url);
    url.searchParams.set("error", "AccessDenied");
    if (reason) url.searchParams.set("reason", reason.slice(0, 200));
    return NextResponse.redirect(url);
  },
  {
    pages: {
      signIn: "/",
      error: "/",
    },
  }
);

export const config = {
  matcher: [
    "/dashboard/:path*",
    // The BFF proxy authorizes each request individually, but rejecting
    // anonymous traffic early keeps it cheap.
    "/api/bot/:path*",
  ],
};
