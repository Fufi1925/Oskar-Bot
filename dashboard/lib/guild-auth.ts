/**
 * Guild authorization helpers.
 *
 * The bot API is a trusted backend: anything that reaches it may read and write
 * every guild's configuration. Therefore the dashboard must never expose the API
 * key to the browser, and every request coming from a browser must be checked
 * against the *user's* Discord permissions before it is forwarded.
 *
 * This module answers a single question: "is the logged-in user allowed to
 * manage guild X?" — by asking Discord itself with the user's OAuth token.
 */

import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";

const MANAGE_GUILD = BigInt(0x20);
const ADMINISTRATOR = BigInt(0x8);

/**
 * Discord user IDs that may access the global admin panel.
 *
 * `OWNER_IDS` steht bewusst mit in der Liste. Der Bot liest beide Namen
 * (`utils/dashboard_roles.py`), das Dashboard las lange nur `ADMIN_IDS` --
 * und auf einer Installation, die nur `OWNER_IDS` setzt, hielt der Bot
 * den Betreiber für einen Inhaber, der Proxy aber nicht. Jede
 * Admin-Anfrage wurde dann abgewiesen, bevor sie den Bot überhaupt
 * erreichte. Beide Hälften müssen dieselbe Liste sehen.
 */
export function getAdminIds(): string[] {
  const raw =
    process.env.ADMIN_IDS ||
    process.env.OWNER_IDS ||
    process.env.NEXT_PUBLIC_ADMIN_IDS ||
    "";
  return raw
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean);
}

export function isGlobalAdmin(userId?: string | null): boolean {
  if (!userId) return false;
  return getAdminIds().includes(userId);
}

interface DiscordPartialGuild {
  id: string;
  name: string;
  icon: string | null;
  owner?: boolean;
  permissions: string;
}

/**
 * Small in-memory cache so we do not hit Discord's `/users/@me/guilds`
 * rate limit (which is a strict 1 request per second per token).
 * Keyed by access token, expires after 60 seconds.
 */
const guildCache = new Map<string, { guilds: DiscordPartialGuild[]; expires: number }>();
const CACHE_TTL_MS = 60_000;

function pruneCache() {
  const now = Date.now();
  for (const [key, entry] of guildCache.entries()) {
    if (entry.expires <= now) guildCache.delete(key);
  }
}

export async function fetchUserGuilds(accessToken: string): Promise<DiscordPartialGuild[]> {
  pruneCache();

  const cached = guildCache.get(accessToken);
  if (cached && cached.expires > Date.now()) {
    return cached.guilds;
  }

  const res = await fetch("https://discord.com/api/users/@me/guilds", {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });

  if (!res.ok) {
    // On failure return an empty list: "fail closed" is the safe default here.
    if (cached) return cached.guilds;
    return [];
  }

  const guilds = (await res.json()) as DiscordPartialGuild[];
  guildCache.set(accessToken, { guilds, expires: Date.now() + CACHE_TTL_MS });
  return guilds;
}

export function hasManagePermission(guild: DiscordPartialGuild): boolean {
  if (guild.owner === true) return true;
  try {
    const perms = BigInt(guild.permissions);
    return (perms & ADMINISTRATOR) === ADMINISTRATOR || (perms & MANAGE_GUILD) === MANAGE_GUILD;
  } catch {
    return false;
  }
}

/**
 * Verwaltet dieser Nutzer den Server auf **Discord** selbst?
 *
 * ── Warum es diese Frage braucht ────────────────────────────────────
 *
 * Der Proxy prüfte bisher in jedem Server-Bereich so:
 *
 *     const team = await fetchTeamAccess(userId);
 *     if (!team || team.roles.length === 0) return { ok: true };
 *     if (await hasTeamPermission(...)) return { ok: true };
 *     return deny(403);
 *
 * Ohne Dashboard-Rolle kam man also durch — die Discord-Prüfung lief
 * ja darüber. **Mit** Rolle zählte ab da nur noch die Rolle. Die Rolle
 * hat die Discord-Rechte nicht ergänzt, sondern **ersetzt**.
 *
 * Wer sich als Server-Inhaber selbst eine Rolle wie „Ticket Support“
 * gab, konnte auf dem eigenen Server nichts mehr einstellen: „missing
 * permission“, bei jeder Einstellung. Rolle weg — ging wieder. Genau
 * so hat der Nutzer es gemeldet, und genau so ist es nachgemessen.
 *
 * Eine Rolle ist eine **Zusatzbefugnis** für Leute ohne Discord-Rechte.
 * Sie darf niemandem etwas wegnehmen. Diese Funktion beantwortet
 * deshalb die eine Frage, die dafür fehlte: hat der Nutzer die Rechte
 * schon von Discord? Dann gilt das weiter, ganz gleich welche Rolle er
 * sonst noch trägt.
 *
 * `false` ist die sichere Antwort: ohne Sitzung, ohne Token oder bei
 * einer fehlgeschlagenen Anfrage an Discord wird die Rollenprüfung
 * angewandt — die ist enger, nicht weiter.
 */
export async function managesGuildOnDiscord(guildId: string): Promise<boolean> {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id || !session.accessToken) return false;
  if (!/^\d{17,20}$/.test(String(guildId))) return false;

  try {
    const guilds = await fetchUserGuilds(session.accessToken);
    const guild = guilds.find((g) => String(g.id) === String(guildId));
    return Boolean(guild && hasManagePermission(guild));
  } catch {
    return false;
  }
}

export interface GuildAccessResult {
  allowed: boolean;
  /** HTTP status to answer with when `allowed` is false. */
  status: number;
  reason: string;
  userId?: string;
}

/* ────────────────────────────────────────────────────────────────────────
   Dashboard team roles

   A person can be granted dashboard access without being a bot owner and
   without having Manage Server on the Discord side. Their roles are stored
   by the bot; we ask it what the user is allowed to do.
   ──────────────────────────────────────────────────────────────────────── */

export interface TeamAccess {
  user_id: string;
  is_owner: boolean;
  /** Only owners may add or remove other owners and admins. */
  can_manage_owners: boolean;
  roles: Array<{ key: string; label: string; color: string; rank: number }>;
  permissions: string[];
  highest_rank: number;
  /** null means every guild */
  accessible_guilds: string[] | null;
}

const API_BASE_URL =
  process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

const teamCache = new Map<string, { access: TeamAccess; expires: number }>();
const TEAM_CACHE_TTL_MS = 30_000;

/** Fetches the dashboard roles of a user from the bot. */
export async function fetchTeamAccess(userId: string): Promise<TeamAccess | null> {
  const now = Date.now();
  const cached = teamCache.get(userId);
  if (cached && cached.expires > now) return cached.access;

  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.Authorization = `Bearer ${key}`;

    const res = await fetch(`${API_BASE_URL}/team/me/${userId}`, {
      headers,
      cache: "no-store",
    });
    if (!res.ok) return cached?.access ?? null;

    const access = (await res.json()) as TeamAccess;
    teamCache.set(userId, { access, expires: now + TEAM_CACHE_TTL_MS });
    return access;
  } catch {
    return cached?.access ?? null;
  }
}

/* ────────────────────────────────────────────────────────────────────────
   Dashboard bans

   A ban overrides everything: owner status is the only exception, and the
   bot refuses to ban an owner in the first place. Checked on sign-in, in the
   middleware and in the proxy, so neither a fresh login nor an existing
   session gets through.
   ──────────────────────────────────────────────────────────────────────── */

const banCache = new Map<string, { banned: boolean; reason: string; expires: number }>();
/** Short TTL: a ban must take effect quickly, but not cost a round trip per request. */
const BAN_CACHE_TTL_MS = 15_000;

export interface BanState {
  banned: boolean;
  reason: string;
}

export async function fetchBanState(userId: string): Promise<BanState> {
  const now = Date.now();
  const cached = banCache.get(userId);
  if (cached && cached.expires > now) {
    return { banned: cached.banned, reason: cached.reason };
  }

  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.Authorization = `Bearer ${key}`;

    const res = await fetch(`${API_BASE_URL}/access/check/${userId}`, {
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      // Fail open on a transport error, otherwise a hiccup in the bot API
      // would lock every user out of their own dashboard.
      return cached ? { banned: cached.banned, reason: cached.reason } : { banned: false, reason: "" };
    }

    const data = (await res.json()) as { banned: boolean; reason?: string };
    const state = { banned: Boolean(data.banned), reason: data.reason || "" };
    banCache.set(userId, { ...state, expires: now + BAN_CACHE_TTL_MS });
    return state;
  } catch {
    return cached ? { banned: cached.banned, reason: cached.reason } : { banned: false, reason: "" };
  }
}

/** Records a sign-in with the bot and reports whether the user is banned. */
export async function recordLogin(
  userId: string,
  username: string,
  avatar: string
): Promise<boolean> {
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.Authorization = `Bearer ${key}`;

    const res = await fetch(`${API_BASE_URL}/access/logins`, {
      method: "POST",
      headers,
      cache: "no-store",
      body: JSON.stringify({
        user_id: userId,
        username,
        avatar,
        new_session: true,
      }),
    });
    if (!res.ok) return false;

    const data = (await res.json()) as { banned?: boolean };
    if (data.banned) {
      banCache.set(userId, { banned: true, reason: "", expires: Date.now() + BAN_CACHE_TTL_MS });
    }
    return Boolean(data.banned);
  } catch {
    // The bot API being down must not stop people from signing in.
    return false;
  }
}

/** True when the user holds `permission` (optionally scoped to a guild). */
export async function hasTeamPermission(
  userId: string,
  permission: string,
  guildId?: string
): Promise<boolean> {
  const access = await fetchTeamAccess(userId);
  if (!access) return false;
  if (access.is_owner) return true;
  if (!access.permissions.includes(permission)) return false;
  if (guildId && access.accessible_guilds !== null) {
    return access.accessible_guilds.includes(String(guildId));
  }
  return true;
}

/**
 * Verifies that the currently logged-in user may manage `guildId`.
 * Global admins (ADMIN_IDS) bypass the per-guild check.
 */
export async function verifyGuildAccess(guildId: string): Promise<GuildAccessResult> {
  const session = await getServerSession(authOptions);

  if (!session?.user?.id) {
    return { allowed: false, status: 401, reason: "Not signed in." };
  }

  const userId = session.user.id;

  // A dashboard ban beats every other rule, including Manage Server.
  const ban = await fetchBanState(userId);
  if (ban.banned) {
    return {
      allowed: false,
      status: 403,
      reason: ban.reason
        ? `You are banned from this dashboard: ${ban.reason}`
        : "You are banned from this dashboard.",
      userId,
    };
  }

  if (isGlobalAdmin(userId)) {
    return { allowed: true, status: 200, reason: "Global admin.", userId };
  }

  if (!session.accessToken) {
    return { allowed: false, status: 401, reason: "Discord session expired. Please sign in again.", userId };
  }

  if (!/^\d{17,20}$/.test(guildId)) {
    return { allowed: false, status: 400, reason: "Invalid guild id.", userId };
  }

  // A dashboard team role can grant access even without Manage Server on
  // Discord — that is the point of handing out roles like "Support Agent".
  const team = await fetchTeamAccess(userId);
  if (team && !team.is_owner && team.roles.length > 0) {
    const scoped = team.accessible_guilds;
    if (scoped === null || scoped.includes(String(guildId))) {
      return { allowed: true, status: 200, reason: "Dashboard team role.", userId };
    }
  }

  const guilds = await fetchUserGuilds(session.accessToken);
  const guild = guilds.find((g) => String(g.id) === String(guildId));

  if (!guild) {
    return { allowed: false, status: 403, reason: "You are not a member of this server.", userId };
  }

  if (!hasManagePermission(guild)) {
    return {
      allowed: false,
      status: 403,
      reason: "You need the 'Manage Server' permission to configure this server.",
      userId,
    };
  }

  return { allowed: true, status: 200, reason: "OK", userId };
}

/** Verifies that the user may use the *global* admin endpoints. */
export async function verifyAdminAccess(): Promise<GuildAccessResult> {
  const session = await getServerSession(authOptions);

  if (!session?.user?.id) {
    return { allowed: false, status: 401, reason: "Not signed in." };
  }

  const ban = await fetchBanState(session.user.id);
  if (ban.banned) {
    return {
      allowed: false,
      status: 403,
      reason: ban.reason
        ? `You are banned from this dashboard: ${ban.reason}`
        : "You are banned from this dashboard.",
      userId: session.user.id,
    };
  }

  if (!isGlobalAdmin(session.user.id)) {
    return { allowed: false, status: 403, reason: "Admin access required.", userId: session.user.id };
  }
  return { allowed: true, status: 200, reason: "OK", userId: session.user.id };
}
