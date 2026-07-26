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

/** Discord user IDs that may access the global admin panel. */
export function getAdminIds(): string[] {
  return (process.env.ADMIN_IDS || process.env.NEXT_PUBLIC_ADMIN_IDS || "")
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

export interface GuildAccessResult {
  allowed: boolean;
  /** HTTP status to answer with when `allowed` is false. */
  status: number;
  reason: string;
  userId?: string;
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

  if (isGlobalAdmin(userId)) {
    return { allowed: true, status: 200, reason: "Global admin.", userId };
  }

  if (!session.accessToken) {
    return { allowed: false, status: 401, reason: "Discord session expired. Please sign in again.", userId };
  }

  if (!/^\d{17,20}$/.test(guildId)) {
    return { allowed: false, status: 400, reason: "Invalid guild id.", userId };
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
  if (!isGlobalAdmin(session.user.id)) {
    return { allowed: false, status: 403, reason: "Admin access required.", userId: session.user.id };
  }
  return { allowed: true, status: 200, reason: "OK", userId: session.user.id };
}
