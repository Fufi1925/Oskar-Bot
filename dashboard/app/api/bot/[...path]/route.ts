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
import {
  verifyGuildAccess,
  verifyAdminAccess,
  isGlobalAdmin,
  fetchTeamAccess,
  hasTeamPermission,
  fetchBanState,
} from "@/lib/guild-auth";

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

/**
 * Which dashboard permission an /admin/* endpoint requires.
 * Anything not listed here falls back to "must be a global admin".
 */
const ADMIN_PERMISSIONS: Record<string, { GET?: string; WRITE?: string }> = {
  health: { GET: "health.view" },
  logs: { GET: "logs.view" },
  metrics: { GET: "metrics.view" },
  audit: { GET: "audit.view" },
  timeline: { GET: "audit.view" },
  features: { GET: "features.view", WRITE: "features.edit" },
  reports: { GET: "reports.view" },
  approvals: { GET: "approvals.view", WRITE: "approvals.resolve" },
  announcements: { WRITE: "announcements.send" },
  // Owner-only unless a team role carries announcements.send. Reads are
  // gated too: the history shows every server the bot is on.
  broadcast: { GET: "announcements.send", WRITE: "announcements.send" },
  premium: { WRITE: "premium.manage" },
  blacklist: { WRITE: "blacklist.manage" },
  "mass-config": { WRITE: "massconfig.push" },
  stats: { GET: "dashboard.access" },
  notifications: { GET: "audit.view" },
  settings: { GET: "health.view", WRITE: "maintenance.toggle" },
  backups: { GET: "health.view", WRITE: "maintenance.toggle" },
};

/** Which permission an /actions/* endpoint requires. */
const ACTION_PERMISSIONS: Record<string, { GET?: string; WRITE?: string }> = {
  verification: { WRITE: "verification.edit" },
  tickets: { WRITE: "tickets.manage" },
  welcome: { WRITE: "welcome.edit" },
  message: { WRITE: "channels.manage" },
  automod: { GET: "automod.view" },
  giveaways: { GET: "guild.view", WRITE: "settings.edit" },
  autoresponder: { GET: "guild.view", WRITE: "settings.edit" },
  emergency: { GET: "antinuke.view", WRITE: "antinuke.edit" },
};

/** Which permission a /moderation/* endpoint requires. */
const MODERATION_PERMISSIONS: Record<string, { GET?: string; WRITE?: string }> = {
  warnings: { GET: "members.view", WRITE: "moderation.warn" },
  members: { GET: "members.view" },
};

/** Which permission a /team/* endpoint requires. */
const TEAM_PERMISSIONS: Record<string, { GET?: string; WRITE?: string }> = {
  roles: { GET: "dashboard.access" },
  permissions: { GET: "dashboard.access" },
  members: { GET: "team.view", WRITE: "team.assign" },
};

function deny(status: number, message: string) {
  return NextResponse.json({ detail: message }, { status });
}

async function authorize(
  segments: string[],
  request: NextRequest
): Promise<{ ok: true } | { ok: false; response: NextResponse }> {
  const [scope, ...rest] = segments;

  // A dashboard ban blocks the API for an already-signed-in user too. The
  // middleware catches page loads; this catches everything the browser fires
  // afterwards.
  {
    const session = await getServerSession(authOptions);
    if (session?.user?.id) {
      const ban = await fetchBanState(session.user.id);
      if (ban.banned) {
        return {
          ok: false,
          response: deny(
            403,
            ban.reason
              ? `You are banned from this dashboard: ${ban.reason}`
              : "You are banned from this dashboard."
          ),
        };
      }
    }
  }

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

      // Moderation through the dashboard needs the matching team permission.
      const wanted = String(body?.action ?? "").toLowerCase();
      const permissionFor: Record<string, string> = {
        ban: "moderation.ban",
        kick: "moderation.kick",
        mute: "moderation.mute",
        unmute: "moderation.mute",
        purge: "moderation.purge",
        nickname: "members.manage",
        clear_nickname: "members.manage",
        add_role: "members.manage",
        remove_role: "members.manage",
        member_info: "members.view",
        create_role: "roles.manage",
        delete_role: "roles.manage",
        rename_role: "roles.manage",
        color_role: "roles.manage",
        toggle_role_hoist: "roles.manage",
        toggle_role_mentionable: "roles.manage",
        create_text_channel: "channels.manage",
        create_voice_channel: "channels.manage",
        create_category: "channels.manage",
        rename_channel: "channels.manage",
        delete_channel: "channels.manage",
        clone_channel: "channels.manage",
        lock_channel: "channels.manage",
        unlock_channel: "channels.manage",
        slowmode: "channels.manage",
        server_name: "server.manage",
        verification_level_low: "server.manage",
        verification_level_medium: "server.manage",
        default_notifications_mentions: "server.manage",
        default_notifications_all: "server.manage",
      };
      const required = permissionFor[wanted] ?? (wanted.startsWith("scan_") || wanted.startsWith("list_") || wanted === "audit_summary" || wanted === "server_stats" ? "security.scan" : null);

      const team = await fetchTeamAccess(session.user.id);
      const holdsRole = Boolean(team && team.roles.length > 0);

      if (holdsRole && required) {
        const allowed = await hasTeamPermission(session.user.id, required, guildId);
        if (!allowed) {
          return { ok: false, response: deny(403, `Your dashboard role does not include '${required}'.`) };
        }
        return { ok: true };
      }

      const access = await verifyGuildAccess(guildId);
      if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };
      return { ok: true };
    }

    // Everything else: check the permission mapped to this endpoint.
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const mapping = ADMIN_PERMISSIONS[action];
    if (mapping) {
      const isRead = request.method === "GET";
      const required = isRead ? mapping.GET : mapping.WRITE;
      if (required && (await hasTeamPermission(session.user.id, required))) {
        return { ok: true };
      }
      if (required) {
        return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
      }
    }

    const access = await verifyAdminAccess();
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };
    return { ok: true };
  }

  if (scope === "actions") {
    // Shape: /actions/<guildId>/<resource>/...
    const guildId = rest[0];
    const resource = rest[1] ?? "";

    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    // Reached here through Manage Server on Discord: keep the usual rights.
    if (!team || team.roles.length === 0) return { ok: true };

    const mapping = ACTION_PERMISSIONS[resource];
    const required = request.method === "GET" ? mapping?.GET : mapping?.WRITE;
    if (!required) return { ok: true };
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "vanity") {
    // Shape: /vanity/<guildId>/...
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "leveling") {
    // Shape: /leveling/<guildId>/...
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "giveaways") {
    // Shape: /giveaways/<guildId>/...
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "tickets") {
    // Shape: /tickets/<guildId>/...
    // Same gate as the other per-guild scopes.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "tickets.manage";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "servertools") {
    // Shape: /servertools/<guildId>/<tool>/...
    // These read (and for webhooks, change) one specific guild, so the
    // gate is the same as everywhere else: Manage Server on that guild,
    // or the matching dashboard role.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    // Reached here through Discord's own Manage Server permission.
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "server.manage";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "moderation") {
    // Shape: /moderation/<guildId>/<resource>/...
    const guildId = rest[0];
    const resource = rest[1] ?? "";

    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    // Someone who reached this point through Manage Server on Discord (and
    // holds no team role) keeps their usual rights.
    if (!team || team.roles.length === 0) return { ok: true };

    const mapping = MODERATION_PERMISSIONS[resource];
    const required = request.method === "GET" ? mapping?.GET : mapping?.WRITE;
    if (!required) return { ok: true };
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "team") {
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const resource = rest[0] ?? "";

    // Everyone may look up their own access.
    if (resource === "me") return { ok: true };

    // Owner and admin management is the highest privilege in the system:
    // a team role is never enough, only real owners get through.
    if (resource === "owners") {
      const access = await fetchTeamAccess(session.user.id);
      // Reading the list is fine for any owner or admin; changing it is
      // reserved for owners.
      if (request.method === "GET" ? access?.is_owner : access?.can_manage_owners) {
        return { ok: true };
      }
      return {
        ok: false,
        response: deny(403, "Only owners can manage owner and admin access."),
      };
    }

    const mapping = TEAM_PERMISSIONS[resource];
    const required = request.method === "GET" ? mapping?.GET : mapping?.WRITE;
    if (required && (await hasTeamPermission(session.user.id, required))) {
      return { ok: true };
    }
    return {
      ok: false,
      response: deny(403, required ? `This requires the '${required}' permission.` : "Not allowed."),
    };
  }

  if (scope === "access") {
    // Dashboard user management: who signed in, who is banned. Reading the
    // list needs team.view, banning somebody needs team.assign — same bar as
    // handing out roles, because a ban is the mirror image of that.
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const required = request.method === "GET" ? "team.view" : "team.assign";
    if (await hasTeamPermission(session.user.id, required)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "servers") {
    // Global server management.
    //
    // This deliberately does NOT re-implement the permission model. The bot
    // knows who the Discord application owner is and who administrates which
    // server; duplicating that here is how the previous version ended up
    // rejecting the deployer's own requests with 403. The proxy only checks
    // "is this a signed-in human", and the bot makes the real decision.
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const guildId = /^\d{17,20}$/.test(rest[0] ?? "") ? rest[0] : undefined;

    // Someone acting on one specific server may also get in through Discord's
    // own Manage Server permission, which is what verifyGuildAccess checks.
    if (guildId) {
      const access = await verifyGuildAccess(guildId);
      if (access.allowed) return { ok: true };
    }

    // Reading the fleet overview is fine for anyone with dashboard access.
    if (request.method === "GET") {
      if (await hasTeamPermission(session.user.id, "guild.view")) return { ok: true };
      return { ok: false, response: deny(403, "This requires the 'guild.view' permission.") };
    }

    const isRoleWrite = rest.includes("roles") || rest.includes("members");
    const required = isRoleWrite ? "roles.manage" : "blacklist.manage";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
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

  // Preserve the trailing slash the FastAPI router expects on collection routes.
  const trailing = request.nextUrl.pathname.endsWith("/") ? "/" : "";
  const url = new URL(`${API_BASE_URL}/${segments.join("/")}${trailing}`);
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value));

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) headers.Authorization = `Bearer ${API_KEY}`;

  const session = await getServerSession(authOptions);
  const actorId = session?.user?.id;

  let body: string | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    body = await request.text();

    // The `actor` must come from the session, never from the client — a
    // forged actor would bypass the rank check when assigning roles.
    if (body && actorId) {
      try {
        const parsed = JSON.parse(body);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          parsed.actor = actorId;
          body = JSON.stringify(parsed);
        }
      } catch {
        // not JSON, forward unchanged
      }
    }
  }

  // Same for DELETE, where the actor travels as a query parameter.
  if (request.method === "DELETE" && actorId) {
    url.searchParams.set("actor", actorId);
  }

  const targetUrl = url.toString();

  try {
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });

    const headersOut: Record<string, string> = {
      "Content-Type": upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store",
    };

    // File downloads (config export, backup zips) only work if the
    // Content-Disposition survives the proxy. Without it the browser just
    // renders the JSON in a tab instead of saving it.
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) headersOut["Content-Disposition"] = disposition;

    const length = upstream.headers.get("content-length");
    if (length) headersOut["Content-Length"] = length;

    // Pass the body straight through as a stream. Buffering it first
    // (arrayBuffer/text) holds the whole file in memory, which breaks large
    // backup downloads on a small container — and reading it as text would
    // corrupt the zip archives on top of that.
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: headersOut,
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
