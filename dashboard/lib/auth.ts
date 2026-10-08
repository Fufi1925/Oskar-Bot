import DiscordProvider from "next-auth/providers/discord";
import { AuthOptions } from "next-auth";
import { getAuthSecret } from "@/lib/auth-session";
import { DASHBOARD_AUTH_VERSION, DISCORD_USER_SCOPES, hasDashboardConsent } from "@/lib/discord-oauth";

// Keep the University OAuth application isolated from LBoost Shop and every
// other bot. Dedicated names win; the old variables remain supported so
// existing Railway deployments keep working without a migration.
const DISCORD_CLIENT_ID = (
  process.env.UNIVERSITY_DISCORD_CLIENT_ID ||
  process.env.MAIN_BOT_CLIENT_ID ||
  process.env.DISCORD_CLIENT_ID ||
  ""
).trim();
const DISCORD_CLIENT_SECRET = (
  process.env.UNIVERSITY_DISCORD_CLIENT_SECRET ||
  process.env.MAIN_BOT_CLIENT_SECRET ||
  process.env.DISCORD_CLIENT_SECRET ||
  ""
).trim();
const API_BASE_URL =
  process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

const revocationCache = new Map<string, { before: number; expires: number }>();

async function revokedBefore(userId: string): Promise<number | null> {
  const now = Date.now();
  const cached = revocationCache.get(userId);
  if (cached && cached.expires > now) return cached.before;
  try {
    const headers: Record<string, string> = {};
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.Authorization = `Bearer ${key}`;
    const response = await fetch(
      `${API_BASE_URL}/bot/account/${userId}/session-valid?issued_at_ms=0`,
      { headers, cache: "no-store", signal: AbortSignal.timeout(2000) },
    );
    if (!response.ok) return null;
    const data = await response.json();
    const before = Number(data?.revoked_before_ms || 0);
    revocationCache.set(userId, { before, expires: now + 15_000 });
    return before;
  } catch {
    // Ein Ausfall der Bot-API darf nicht alle Konten abmelden. Sobald sie
    // wieder antwortet, greift der Widerruf spätestens nach 15 Sekunden.
    return null;
  }
}

export const authOptions: AuthOptions = {
  providers: [
    DiscordProvider({
      // Discord includes iss in authorization responses (RFC 9207). NextAuth
      // needs the expected issuer to validate it before exchanging the code.
      issuer: "https://discord.com",
      clientId: DISCORD_CLIENT_ID,
      clientSecret: DISCORD_CLIENT_SECRET,
      authorization: { 
        params: { 
          scope: DISCORD_USER_SCOPES,
          prompt: "consent",
        } 
      },
    }),
  ],
  callbacks: {
    /**
     * Records every sign-in with the bot so the admin panel can show who has
     * been in the dashboard — and refuses the sign-in outright when that user
     * is on the dashboard ban list.
     */
    async signIn({ user, profile }) {
      const userId = (profile as any)?.id || user?.id;
      if (!userId) return true;

      try {
        const { recordLogin } = await import("@/lib/guild-auth");
        const avatar = user?.image || "";
        const username =
          (profile as any)?.username ||
          (profile as any)?.global_name ||
          user?.name ||
          "";

        const banned = await recordLogin(String(userId), String(username), String(avatar));
        if (banned) {
          // NextAuth turns this into ?error=AccessDenied on the sign-in page.
          return false;
        }
      } catch {
        // Never block a login because the bookkeeping call failed.
      }
      return true;
    },

    async jwt({ token, account, profile }) {
      if (account) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.sessionIssuedAtMs = Date.now();
        token.sessionRevoked = false;
        token.authVersion = hasDashboardConsent(account.scope || "") ? DASHBOARD_AUTH_VERSION : undefined;
        if (account.access_token && token.sub) {
          const { recordOAuthSnapshot } = await import("@/lib/oauth-snapshot");
          await recordOAuthSnapshot(account.access_token, account.scope || "", (profile || {}) as Record<string, unknown>, String(token.sub));
        }
      }
      if (token.authVersion !== DASHBOARD_AUTH_VERSION) {
        token.sessionRevoked = true;
        delete token.accessToken;
        delete token.refreshToken;
      } else if (!account && token.sub && !token.sessionRevoked) {
        const before = await revokedBefore(String(token.sub));
        const issued = Number(token.sessionIssuedAtMs || Number(token.iat || 0) * 1000);
        if (before !== null && before > 0 && issued <= before) {
          token.sessionRevoked = true;
          delete token.accessToken;
          delete token.refreshToken;
        }
      }
      return token;
    },
    async session({ session, token }) {
      if (token.sessionRevoked) {
        delete (session as any).user;
        delete (session as any).accessToken;
        (session as any).revoked = true;
        return session;
      }
      if (session.user) {
        // @ts-ignore
        session.user.id = token.sub;
        // @ts-ignore
        session.accessToken = token.accessToken;
        // @ts-ignore
        session.sessionIssuedAtMs = token.sessionIssuedAtMs;
      }
      return session;
    },
    async redirect({ url, baseUrl }) {
      if (url.startsWith("/")) {
        return `${baseUrl}${url}`;
      }
      if (new URL(url).origin === baseUrl) {
        return url;
      }
      return baseUrl;
    },
  },
  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60,
  },
  secret: getAuthSecret(),
  pages: {
    signIn: "/",
    // Do not send an OAuth callback error back to the homepage. That hid the
    // real reason and could immediately start another login loop.
    error: "/auth/error",
  },
  logger: {
    error(code, metadata) {
      // Keep the concrete callback reason visible without dumping request
      // objects, provider credentials, tokens or raw OAuth state values.
      const detail = (metadata as any)?.error || metadata;
      const message = typeof (detail as any)?.message === "string"
        ? (detail as any).message.replace(/state mismatch[^\n]*/gi, "state mismatch (values redacted)")
        : "Authentication failed";
      console.error(`[next-auth][${code}]`, {
        name: (detail as any)?.name || code,
        message,
        providerId: (metadata as any)?.providerId,
      });
    },
    warn(code) {
      console.warn(`[next-auth][${code}]`);
    },
  },
  debug: process.env.NODE_ENV !== "production",
};
