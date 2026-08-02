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

import {
  BYPASS_COOKIE,
  BYPASS_PATH,
  bypassToken,
  maintenanceOn,
} from "@/lib/maintenance";

/**
 * Maintenance mode, checked before anything else.
 *
 * Order matters: the auth check below redirects anonymous visitors to
 * the sign-in page, so running it first would send people to Discord to
 * log in during an outage instead of telling them the site is down.
 *
 * Returns a response when the request should be intercepted, or null to
 * carry on as normal.
 */
function maintenanceGate(request: NextRequest): NextResponse | null {
  if (!maintenanceOn()) return null;

  const { pathname } = request.nextUrl;

  // The bypass page has to stay reachable, or there is no way back in.
  if (pathname === BYPASS_PATH || pathname.startsWith(`${BYPASS_PATH}/`)) {
    return null;
  }

  // Already unlocked in this browser.
  if (request.cookies.get(BYPASS_COOKIE)?.value === bypassToken()) {
    return null;
  }

  // Next's own assets, or the notice cannot render at all.
  if (pathname.startsWith("/_next/") || pathname === "/favicon.ico") {
    return null;
  }

  // API callers get JSON; a rewritten HTML page would be parsed as a
  // failed request and produce a confusing error in the client.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json(
      {
        detail:
          "Website und Dashboard sind gerade in Wartung. Der Discord-Bot " +
          "läuft normal weiter.",
        maintenance: true,
      },
      { status: 503 },
    );
  }

  // Rewrite, not redirect: the address bar keeps the path the visitor
  // asked for, so a refresh lands them where they wanted once the
  // maintenance is over.
  //
  // 200 and not 503 on purpose. start.sh waits for `curl /` to succeed
  // before starting the bot, and a 503 there aborts the container --
  // which would take down the very bot this page says is still running.
  return NextResponse.rewrite(new URL("/wartung", request.url));
}

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

/** The signed-in checks, unchanged. Only runs on the protected paths. */
const authGate = withAuth(
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

/** Paths that still need a session once maintenance is off. */
function needsAuth(pathname: string): boolean {
  return pathname.startsWith("/dashboard") || pathname.startsWith("/api/bot");
}

export default function middleware(request: NextRequest, event: any) {
  // Maintenance first. withAuth sends anonymous visitors to the sign-in
  // page, so checking it second would bounce people to Discord to log
  // in during an outage rather than telling them the site is down.
  const halted = maintenanceGate(request);
  if (halted) return halted;

  if (needsAuth(request.nextUrl.pathname)) {
    return (authGate as any)(request, event);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Everything, so maintenance mode covers every path -- that is the
    // point of it. The auth check inside still only applies to
    // /dashboard and /api/bot.
    //
    // Excluded: Next's own build output and the favicon. Rewriting
    // those would leave the notice itself without styling.
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
