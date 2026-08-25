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
  managesGuildOnDiscord,
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
  // The report names channels and roles across every guild.
  diagnose: { GET: "health.view" },
  premium: { WRITE: "premium.manage" },
  blacklist: { WRITE: "blacklist.manage" },
  "mass-config": { WRITE: "massconfig.push" },
  stats: { GET: "dashboard.access" },
  // Die Befehls-Statistik. Ohne diesen Eintrag fiel sie auf
  // verifyAdminAccess() zurück, und die lässt ausschließlich globale
  // Admins durch: der Usage-Reiter war zwar sichtbar, gab beim Klick
  // aber "Admin access required." Die Servernamen darin maskiert der
  // Bot selbst für alle außer Ownern.
  "command-stats": { GET: "metrics.view" },
  // Der Verlauf über alle Server. Reine Zahlenreihen -- keine
  // Servernamen, keine IDs --, deshalb dieselbe Schwelle wie bei den
  // übrigen Kennzahlen und nicht die strengere der Berichte. Ohne
  // diesen Eintrag fiele er auf verifyAdminAccess() zurück und wäre
  // für jede Team-Rolle ein leeres Diagramm mit Fehlermeldung.
  history: { GET: "metrics.view" },
  // Ping-Reaktionen: wer beim Erwähnen welche Emojis bekommt. Lesen
  // darf jede Team-Rolle, ändern nur, wer Bot-Einstellungen ändern
  // darf — die Regel gilt global, nicht für einen Server.
  "ping-reactions": { GET: "dashboard.access", WRITE: "maintenance.toggle" },
  notifications: { GET: "audit.view" },
  settings: { GET: "health.view", WRITE: "maintenance.toggle" },
  backups: { GET: "health.view", WRITE: "maintenance.toggle" },
  // Der Kontowechsel. Bewusst NICHT hier eingetragen: er faellt
  // absichtlich auf verifyAdminAccess() zurueck, und die laesst
  // ausschliesslich globale Admins durch.
  //
  // Begruendung: `POST /admin/umzug/einspielen` ueberschreibt saemtliche
  // Datenbankdateien auf einen Schlag -- jeden Server, jede
  // Einstellung, die Dashboard-Rollen inbegriffen. Wer das darf, kann
  // sich anschliessend selbst zum Eigentuemer machen. Eine Team-Rolle
  // wie `maintenance.toggle`, die sonst fuer Sicherungen reicht, ist
  // dafuer eine zu niedrige Schwelle.
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

      // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
      // Dieselbe Regel wie in den Server-Bereichen weiter unten: eine
      // Dashboard-Rolle ergaenzt, sie ersetzt nicht. Ohne diese Zeile
      // konnte ein Server-Inhaber, der sich selbst eine beliebige
      // Rolle gab, auf seinem eigenen Server nicht mehr moderieren.
      if (await managesGuildOnDiscord(guildId)) return { ok: true };

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

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    // Reached here through Manage Server on Discord: keep the usual rights.
    if (!team || team.roles.length === 0) return { ok: true };

    const mapping = ACTION_PERMISSIONS[resource];
    const required = request.method === "GET" ? mapping?.GET : mapping?.WRITE;
    if (!required) return { ok: true };
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "automod") {
    // Shape: /automod/<guildId>/...
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "antinuke") {
    // ── Die vertrauten Bots: /antinuke/trusted/... ──────────────────
    //
    // Muss VOR der Guild-Pruefung stehen: die liest `rest[0]` als
    // Server-ID, und „trusted" ist keine. Ohne diesen Zweig liefe die
    // Anfrage in `verifyGuildAccess("trusted")` und scheiterte mit
    // einer irrefuehrenden Meldung.
    //
    // Die Liste gilt global. Lesen darf jede Team-Rolle -- sie steht
    // auch im Server-Reiter, damit niemand raetselt, warum ein Bot
    // ungestraft Kanaele anlegt. Aendern darf nur, wer Bot-weite
    // Einstellungen aendern darf: wer sie pro Server pflegen duerfte,
    // traegt seinen Zweitbot ein und hebelt den Schutz aus.
    if (rest[0] === "trusted") {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
      if (isGlobalAdmin(session.user.id)) return { ok: true };

      const required =
        request.method === "GET" ? "dashboard.access" : "maintenance.toggle";
      if (await hasTeamPermission(session.user.id, required)) return { ok: true };

      return {
        ok: false,
        response: deny(403, `This requires the '${required}' permission.`),
      };
    }

    // Shape: /antinuke/<guildId>/...
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "logging") {
    // Shape: /logging/<guildId>/...
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "design") {
    // Shape: /design/<guildId>/...  bzw.  /design/admin/unlocked
    //
    // Die Freischaltliste gehoert dem Admin-Bereich: sie entscheidet,
    // welche Server das Design aendern duerfen, ohne dass ihr Inhaber
    // es ist. Wer sie sehen oder aendern kann, koennte sich sonst
    // selbst freischalten.
    if (rest[0] === "admin") {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
      if (!isGlobalAdmin(session.user.id)) {
        return { ok: false, response: deny(404, "Not found.") };
      }
      return { ok: true };
    }

    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, darf die Seite oeffnen.
    // Ob er wirklich AENDERN darf, entscheidet der Bot: dafuer
    // braucht es Premium und Inhaberschaft (oder eine
    // Freischaltung). Das hier ist nur die Tuer zur Seite.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "server.manage";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "honeypot") {
    // Shape: /honeypot/<guildId>/...
    //
    // Gleiche Schwelle wie der Warteraum: wer den Server verwaltet,
    // darf ihn einstellen. Der Honeypot bannt Leute, ist also keine
    // Kleinigkeit -- aber er wirkt nur auf diesem einen Server, und
    // "Server verwalten" ist genau die Berechtigung, die das abdeckt.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "server.manage";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "supportqueue") {
    // Shape: /supportqueue/<guildId>/...
    //
    // Ohne diesen Zweig fiele der Warteraum ans Ende der Funktion und
    // bekäme 404 "Unknown API scope" — derselbe Fehler wie zuletzt bei
    // command-stats, nur mit anderer Nummer.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    // Über Manage Server auf Discord hereingekommen: übliche Rechte.
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "templates") {
    // Shape: /templates/<guildId>/... oder /templates/admin/...
    //
    // Ohne diesen Zweig faellt der Reiter ans Ende der Funktion und
    // bekommt 404 "Unknown API scope" — derselbe Fehler wie zuletzt
    // bei command-stats, dem Warteraum und der Musik.
    const first = rest[0];
    if (!first) return { ok: false, response: deny(400, "guild_id missing.") };

    // Die Verwaltung: nur globale Admins.
    //
    // Diese Routen zeigen JEDE hochgeladene Vorlage, auch die
    // privaten, samt Zugangscode im Klartext — und sie können jede
    // davon sperren oder löschen. Das ist nichts, was ein
    // Server-Moderator sehen darf, auch nicht für den eigenen Server.
    //
    // Die Regel steht VOR der guild_id-Prüfung: "admin" ist keine
    // achtzehnstellige Zahl. Stünde sie danach, liefe der Aufruf in
    // verifyGuildAccess("admin") und käme dort mit einer irreführenden
    // Meldung heraus, statt sauber abgewiesen zu werden.
    if (first === "admin") {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
      if (!isGlobalAdmin(session.user.id)) {
        return {
          ok: false,
          response: deny(403, "Only global admins can manage community templates."),
        };
      }
      return { ok: true };
    }

    const guildId = first;
    // Eine echte Server-ID, keine Ausrede. Ohne diese Prüfung würde
    // jedes weitere Wort am Anfang des Pfads als guild_id
    // durchgereicht.
    if (!/^\d{17,20}$/.test(guildId)) {
      return { ok: false, response: deny(400, "guild_id missing.") };
    }

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    // Eine Vorlage anzuwenden kann den ganzen Server umbauen — das
    // ist mehr als eine Einstellung zu aendern.
    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "teamlist") {
    // Shape: /teamlist/<guildId>/...
    //
    // Ohne diesen Zweig faellt der Reiter ans Ende der Funktion und
    // bekommt 404 "Unknown API scope" — derselbe Fehler wie zuletzt
    // bei command-stats, dem Warteraum, der Musik und den Vorlagen.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    // Die Teamliste postet als Bot in einen Kanal — das ist näher an
    // "Nachrichten verwalten" als an einer Einstellung.
    const required = request.method === "GET" ? "guild.view" : "channels.manage";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "applications") {
    // Shape: /applications/<guildId>/...
    //
    // Ohne diesen Zweig faellt der Reiter ans Ende der Funktion und
    // bekommt 404 "Unknown API scope" — derselbe Fehler wie zuletzt bei
    // command-stats, dem Warteraum, der Musik, den Vorlagen und der
    // Teamliste. Jeder neue Bereich braucht hier einen Eintrag; das ist
    // inzwischen der sechste Fall.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    // Ein Bewerbungs-Panel postet als Bot in einen Kanal und entscheidet
    // über Rollen — dieselbe Messlatte wie bei den Tickets.
    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "commands") {
    // Das oeffentliche Befehlsverzeichnis. Jeder Angemeldete darf es
    // lesen -- es steht ohnehin in jeder Hilfe des Bots und verraet
    // nichts ueber einen konkreten Server.
    if (request.method !== "GET") {
      return { ok: false, response: deny(405, "Read-only.") };
    }
    return { ok: true };
  }

  if (scope === "webapply") {
    // Team-Bewerbungen ueber die Website.
    //
    // Drei Klassen von Routen, und die Unterschiede sind wichtig:
    //
    //   * die Rollenliste — OHNE Anmeldung. Sie ist der Aushang „wir
    //     suchen Leute": welche Rollen offen sind, wie viele Fragen
    //     dazugehoeren. Nichts davon ist persoenlich, und sie steht
    //     auf der oeffentlichen Team-Seite.
    //   * eigene Bewerbung (abgeben, ansehen, zurueckziehen) — jeder
    //     Angemeldete, aber ausschliesslich fuer sich selbst. Die
    //     Nutzer-ID kommt aus der Sitzung, NICHT aus dem Rumpf:
    //     sonst koennte jeder im Namen anderer bewerben oder deren
    //     Bewerbung zurueckziehen.
    //   * alles andere (Liste, Entscheidung, Einstellungen) — nur
    //     globale Admins oder wer die Berechtigung traegt.
    //
    // Die Ausnahme steht VOR der Anmeldepruefung, und das ist der
    // ganze Punkt: `roles` galt schon vorher als „eigene" Route, kam
    // dort aber nie an, weil die Pruefung darueber stand. Nachgemessen
    // mit curl ohne Sitzungs-Cookie:
    //
    //     /api/bot/webapply/roles -> HTTP 307
    //     location: /?callbackUrl=%2Fapi%2Fbot%2Fwebapply%2Froles
    //
    // Nur GET: das Abgeben einer Bewerbung braucht weiterhin eine
    // Sitzung.
    if (request.method === "GET" && rest[0] === "roles") {
      return { ok: true };
    }

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };

    const erste = rest[0] ?? "";
    const eigen = erste === "submit" || erste === "me" || erste === "withdraw"
      || erste === "roles";

    if (eigen) {
      // Bei "me" und "withdraw" steht die ID im Pfad. Sie muss die
      // eigene sein -- sonst liest jemand fremde Bewerbungen.
      if ((erste === "me" || erste === "withdraw") && rest[1] !== session.user.id) {
        return { ok: false, response: deny(403, "Nur die eigene Bewerbung.") };
      }
      return { ok: true };
    }

    if (isGlobalAdmin(session.user.id)) return { ok: true };
    if (await hasTeamPermission(session.user.id, "approvals.resolve")) {
      return { ok: true };
    }
    return {
      ok: false,
      response: deny(403, "This requires the 'approvals.resolve' permission."),
    };
  }

  if (scope === "teamupdate") {
    // Shape: /teamupdate/<guildId>/...
    //
    // Ohne diesen Zweig faellt der Reiter ans Ende der Funktion und
    // bekommt 404 "Unknown API scope" — derselbe Fehler wie zuletzt bei
    // command-stats, dem Warteraum, der Musik, den Vorlagen, der
    // Teamliste und den Bewerbungen. Jeder neue Bereich braucht hier
    // einen Eintrag; das ist inzwischen der siebte Fall.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    // Ein Team-Update steckt Rollen um und kuendigt es oeffentlich an.
    // Das ist mehr als eine Einstellung — deshalb "roles.manage" statt
    // "settings.edit".
    const required = request.method === "GET" ? "guild.view" : "roles.manage";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "music") {
    // Shape: /music/<guildId>/...
    //
    // Ohne diesen Zweig fiele der Musik-Reiter ans Ende der Funktion
    // und bekäme 404 "Unknown API scope" — derselbe Fehler wie zuletzt
    // bei command-stats und beim Warteraum.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "verify") {
    // Shape: /verify/<guildId>/...
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "voice") {
    // Shape: /voice/<guildId>/...  (join to create, voice roles,
    // custom role commands)
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "speedrun") {
    // Shape: /speedrun/templates, /speedrun/steps or /speedrun/<guildId>/...
    //
    // Ein Speedrun legt Dutzende Rollen und Kanäle an und schaltet
    // Verify, Anti-Nuke und Tickets scharf. Das ist die eingreifendste
    // Aktion im ganzen Dashboard, deshalb liegt die Latte hier auf
    // "server.manage" statt auf "settings.edit".
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };

    const first = rest[0] ?? "";

    // Die Listen sind serverunabhängig: welche Templates es gibt und
    // welche Schritte der Bot anbietet. Für jeden Angemeldeten lesbar,
    // sie verraten nichts über einen konkreten Server.
    if (first === "templates" || first === "steps") {
      return { ok: true };
    }

    // Die Verwaltung der Beta-Zugänge: nur globale Admins.
    //
    // Diese Routen zeigen *jeden* Server, der den Code eingegeben hat,
    // samt Namen, Mitgliederzahl und dem, wer ihn wann freigeschaltet
    // hat -- und sie können jedem Server den Zugang nehmen. Das ist
    // nichts, was ein Server-Moderator sehen oder tun darf, auch nicht
    // für den eigenen Server.
    //
    // Die Regel steht *vor* der guild_id-Prüfung: "admin" ist keine
    // achtzehnstellige Zahl und würde sonst als fehlende guild_id
    // abgewiesen, noch bevor irgendjemand sie erreichen kann.
    if (first === "admin") {
      if (!isGlobalAdmin(session.user.id)) {
        return {
          ok: false,
          response: deny(403, "Only global admins can manage Speedrun access."),
        };
      }
      return { ok: true };
    }

    const guildId = first;
    if (!/^\d{17,20}$/.test(guildId)) {
      return { ok: false, response: deny(400, "guild_id missing.") };
    }

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    // Über Discords eigenes "Server verwalten" hereingekommen.
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "server.manage";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "extras") {
    // Shape: /extras/<guildId>/...
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "perks") {
    // Shape: /perks/<guildId>/...  (join DM, no-prefix, reaction roles)
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "guild.view" : "settings.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "nukealert") {
    // Shape: /nukealert/<guildId>/...
    // The history names who attacked, so it follows the antinuke rights.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    const required = request.method === "GET" ? "antinuke.view" : "antinuke.edit";
    if (await hasTeamPermission(session.user.id, required, guildId)) return { ok: true };
    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
  }

  if (scope === "tester") {
    // Der Tester-Bereich prüft seine Rechte im Bot selbst, über die
    // Tester-Rolle. Hier reicht deshalb "angemeldet" -- ein
    // isGlobalAdmin-Gate wie bei /admin würde genau die Leute
    // aussperren, für die der Bereich gebaut ist.
    //
    // Die user_id wird aus der Sitzung gesetzt und nicht aus dem
    // Aufruf übernommen: sonst schreibt sich jeder eine fremde ID in
    // die Anfrage und liest deren Meldungen.
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    return { ok: true };
  }

  if (scope === "premium") {
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };

    // `grant` gehoert dem Template-Bot, nicht dem Browser.
    //
    // Die Route traegt sich selbst mit dem Partner-Token ab; erreichbar
    // ueber den Proxy waere sie ein Weg, sich per Klick eine Probewoche
    // auf ein beliebiges Konto zu schreiben. Derselbe Grund wie bei
    // `check` weiter unten.
    if (rest[0] === "grant") {
      return { ok: false, response: deny(403, "Not available through the dashboard.") };
    }

    // Listing, revoking and deleting keys is staff work. Deleting most
    // of all: it cannot be undone. Die Probewochen gehoeren dazu --
    // „zuruecksetzen" verschenkt sieben Tage.
    if (["keys", "revoke", "delete", "purge", "trials"].includes(rest[0] ?? "")) {
      if (isGlobalAdmin(session.user.id)) return { ok: true };
      const team = await fetchTeamAccess(session.user.id);
      const staff = Boolean(team && (team.is_owner || team.roles.length > 0));
      if (!staff) return { ok: false, response: deny(403, "Admins only.") };
      return { ok: true };
    }

    // "Does this user have premium" belongs to the template bot, which
    // authenticates with its own token straight against the API. Serving
    // it here would let any signed-in browser read other accounts.
    if (rest[0] === "check") {
      return { ok: false, response: deny(403, "Not available through the dashboard.") };
    }

    // Everything else (reading your own status, redeeming a key) is for
    // the signed-in user and is pinned to their own id below.
    return { ok: true };
  }

  if (scope === "compose") {
    // Shape: /compose/<guildId>/...
    // Posting as the bot into any channel is close to "manage messages",
    // so it needs a write permission, not guild.view.

    // Die Emoji-Liste ist serverunabhängig: sie zählt auf, welche
    // eigenen Emojis der Bot mitbringt, und verrät nichts über einen
    // konkreten Server. Für jeden Angemeldeten lesbar.
    //
    // Die Regel steht vor der guild_id-Prüfung, weil "emojis" keine
    // achtzehnstellige Zahl ist und sonst als fehlende guild_id
    // abgewiesen würde, bevor sie jemand erreichen kann.
    if (rest[0] === "emojis") {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
      return { ok: true };
    }

    // Dasselbe gilt für die vorgefertigten Texte: sie hängen an keinem
    // Server, sondern zählen auf, was der Bot an Vorlagen mitbringt.
    // Auch hier vor der guild_id-Prüfung, weil "templates" keine
    // achtzehnstellige Zahl ist.
    if (rest[0] === "templates") {
      const session = await getServerSession(authOptions);
      if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
      return { ok: true };
    }

    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    if (await hasTeamPermission(session.user.id, "channels.manage", guildId)) return { ok: true };
    return { ok: false, response: deny(403, "This requires the 'channels.manage' permission.") };
  }

  if (scope === "anonchat") {
    // Shape: /anonchat/<guildId>/...
    // The log here deanonymises members, so a plain guild.view is not
    // enough — reading it needs the same right as changing it.
    const guildId = rest[0];
    if (!guildId) return { ok: false, response: deny(400, "guild_id missing.") };

    const access = await verifyGuildAccess(guildId);
    if (!access.allowed) return { ok: false, response: deny(access.status, access.reason) };

    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

    const team = await fetchTeamAccess(session.user.id);
    if (!team || team.roles.length === 0) return { ok: true };

    if (await hasTeamPermission(session.user.id, "settings.edit", guildId)) return { ok: true };
    return { ok: false, response: deny(403, "This requires the 'settings.edit' permission.") };
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

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

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

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

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

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

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

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

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

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

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

    // Wer den Server auf Discord verwaltet, behaelt seine Rechte.
    // Eine Dashboard-Rolle ist eine Zusatzbefugnis fuer Leute
    // OHNE solche Rechte -- sie darf niemandem etwas wegnehmen.
    // Ohne diese Zeile sperrte sich ein Server-Inhaber aus,
    // sobald er sich selbst irgendeine Rolle gab.
    if (await managesGuildOnDiscord(guildId)) return { ok: true };

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

    // Jeder darf seinen *eigenen* Zugang abfragen -- und nur den.
    //
    // Die user_id steht im Pfad und kommt aus dem Browser. Vorher
    // stand hier ein bedingungsloses `return { ok: true }`, also
    // konnte jeder Angemeldete mit /team/me/<fremde-id> nachsehen,
    // welche Dashboard-Rollen jemand anderes hat. Keine Geheimnisse,
    // aber eine Auskunft über andere Leute, die niemand angefordert
    // hat -- und sie war mit einer geänderten URL zu holen.
    if (resource === "me") {
      const wanted = rest[1] ?? "";
      if (wanted && wanted !== session.user.id) {
        return {
          ok: false,
          response: deny(403, "You can only look up your own access."),
        };
      }
      return { ok: true };
    }

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
    // Die Zahlen der Startseite: ohne Anmeldung lesbar. Sie stehen
    // ohnehin auf jeder oeffentlichen Bot-Liste, und die Startseite
    // ist nun einmal oeffentlich.
    if (rest[0] === "numbers" && request.method === "GET") {
      return { ok: true };
    }
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    return { ok: true };
  }

  if (scope === "cookies") {
    // Genau EINE Route ist ohne Anmeldung erreichbar: das Festhalten
    // der Bestaetigung. Sie muss es sein -- der Hinweis erscheint auf
    // der oeffentlichen Startseite, lange bevor sich jemand anmeldet.
    // Wer angemeldet ist, dessen Discord-ID haengt der Handler weiter
    // unten aus der Sitzung an; aus dem Browser wird sie nie
    // uebernommen.
    if (request.method === "POST" && rest[0] === "consent") {
      return { ok: true };
    }

    // Alles Uebrige ist die Nachweisliste. Sie nennt Discord-Konten
    // und Zeitpunkte, also gilt dieselbe Schwelle wie fuer die
    // Dashboard-Nutzer: team.view zum Lesen, team.assign zum Loeschen.
    // Ein Loeschen ist hier keine Kleinigkeit -- es entfernt den
    // Nachweis einer Einwilligung.
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) return { ok: false, response: deny(401, "Not signed in.") };
    if (isGlobalAdmin(session.user.id)) return { ok: true };

    const required = request.method === "GET" ? "team.view" : "team.assign";
    if (await hasTeamPermission(session.user.id, required)) return { ok: true };

    return { ok: false, response: deny(403, `This requires the '${required}' permission.`) };
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

  // ── Binaerer Upload: unveraendert durchreichen ─────────────────────
  //
  // Der Umzug schickt eine ZIP-Datei. `request.text()` weiter unten
  // dekodiert den Rumpf als UTF-8, und jedes Byte, das keine gueltige
  // UTF-8-Folge ist, wird dabei durch U+FFFD ersetzt. Bei einem Archiv
  // ist das die Mehrzahl der Bytes -- es kaeme unbrauchbar an, und der
  // Fehler ("keine gueltige ZIP-Datei") entstuende erst im Bot, weit
  // weg von der Ursache.
  //
  // Deshalb hier vorher abbiegen und den Datenstrom unangetastet
  // weiterreichen. Die JSON-Behandlung darunter bleibt, wie sie war.
  const istBinaer = (request.headers.get("content-type") || "")
    .toLowerCase()
    .includes("zip");

  if (istBinaer && !["GET", "HEAD"].includes(request.method)) {
    try {
      const upstream = await fetch(url.toString(), {
        method: request.method,
        headers: {
          "Content-Type": "application/zip",
          ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
        },
        body: await request.arrayBuffer(),
        cache: "no-store",
      });

      return new NextResponse(upstream.body, {
        status: upstream.status,
        headers: {
          "Content-Type":
            upstream.headers.get("content-type") || "application/json",
          "Cache-Control": "no-store",
        },
      });
    } catch (error: any) {
      console.error(`[BFF] Upload fehlgeschlagen fuer ${url}:`, error?.message ?? error);
      return deny(502, "Bot API is unreachable. Is the bot running?");
    }
  }

  let body: string | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    body = await request.text();

    // ── Ohne Sitzung: die Konto-Felder ausdruecklich leeren ──────────
    //
    // Der Block darunter laeuft nur MIT `actorId`. Das reichte, solange
    // jede schreibende Route eine Anmeldung verlangte. Die
    // Cookie-Bestaetigung tut das nicht -- sie kommt von der
    // oeffentlichen Startseite --, und damit rutschte ein aus dem
    // Browser mitgeschicktes `user_id` unveraendert durch: der
    // „Nachweis" haette behauptet, ein fremdes Konto habe bestaetigt.
    //
    // Nachgemessen mit einer POST-Anfrage ohne Sitzungs-Cookie, bevor
    // diese Zeilen hier standen.
    if (body && !actorId) {
      try {
        const parsed = JSON.parse(body);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          delete parsed.actor;
          parsed.user_id = "";
          parsed.user_name = "";
          body = JSON.stringify(parsed);
        }
      } catch {
        // kein JSON, unveraendert weiterreichen
      }
    }

    // The `actor` must come from the session, never from the client — a
    // forged actor would bypass the rank check when assigning roles.
    if (body && actorId) {
      try {
        const parsed = JSON.parse(body);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          parsed.actor = actorId;
          // Redeeming binds a key to an account for good. The account has
          // to be the signed-in one: a user_id from the browser would let
          // anyone activate premium onto someone else's id.
          if (segments[0] === "premium" && segments[1] === "redeem") {
            parsed.user_id = actorId;
          }
          // Dasselbe für den Tester-Bereich: der Bot entscheidet
          // anhand der user_id, wer Tester ist und wessen Meldungen
          // jemand sieht. Käme sie aus dem Browser, schriebe sich
          // jeder eine fremde ID hinein.
          if (segments[0] === "tester") {
            parsed.user_id = actorId;
          }
          // Team-Bewerbungen: die Bewerbung gehoert der angemeldeten
          // Person. Kaeme die user_id aus dem Browser, koennte jeder
          // im Namen anderer bewerben -- und die Regel "eine
          // Bewerbung pro Person" waere mit einer erfundenen ID
          // beliebig oft zu umgehen.
          //
          // Name und Bild kommen aus derselben Quelle, damit im
          // Admin-Dashboard nicht steht, was jemand sich selbst
          // ausgedacht hat.
          if (segments[0] === "webapply" && segments[1] === "submit") {
            parsed.user_id = actorId;
            parsed.user_name = session?.user?.name ?? "";
            parsed.avatar = session?.user?.image ?? "";
          }
          if (segments[0] === "webapply" && segments[1] === "decide") {
            parsed.actor_name = session?.user?.name ?? "";
          }
          // Die Cookie-Bestaetigung. Sie ist der Nachweis nach Art. 7
          // Abs. 1 DSGVO -- und ein Nachweis, in den der Browser eine
          // beliebige Discord-ID schreiben darf, belegt nichts.
          // Deshalb kommen Konto und Name ausschliesslich aus der
          // Sitzung; ein mitgeschickter Wert wird ueberschrieben.
          //
          // Ist niemand angemeldet, stehen hier leere Zeichenketten.
          // Das ist der Normalfall: der Hinweis erscheint auf der
          // oeffentlichen Startseite.
          if (segments[0] === "cookies" && segments[1] === "consent") {
            parsed.user_id = actorId ?? "";
            parsed.user_name = session?.user?.name ?? "";
          }
          body = JSON.stringify(parsed);
        }
      } catch {
        // not JSON, forward unchanged
      }
    }
  }

  // Der `actor` als Abfrageparameter -- für JEDE Methode, nicht nur
  // DELETE.
  //
  // Vorher stand hier `request.method === "DELETE"`. Das reichte genau
  // so lange, wie ausschließlich schreibende Routen den Aufrufer
  // brauchten: POST und PATCH bekommen ihn im JSON-Körper, DELETE hat
  // keinen Körper und deshalb diesen Zweig. Eine **lesende** Route, die
  // eine Rechteprüfung macht, fiel durch beide Raster — sie bekam
  // `actor=""` und antwortete zuverlässig mit 403. Genau das ist beim
  // Nutzer-Nachschlag passiert: "Du darfst Nutzer nachschlagen nicht.",
  // egal wer angemeldet war.
  //
  // `set` statt `append`: ein aus dem Browser mitgeschickter Wert wird
  // überschrieben, nicht ergänzt. Sonst könnte jemand eine fremde ID in
  // die URL schreiben und damit fremde Rechte erben.
  if (actorId) {
    url.searchParams.set("actor", actorId);
  } else {
    // Ohne Sitzung darf erst recht kein Wert aus dem Browser
    // durchrutschen.
    url.searchParams.delete("actor");
  }

  // Der Tester-Bereich liest die user_id auch bei GET. Sie kommt
  // immer aus der Sitzung -- ein mitgeschickter Wert wird
  // überschrieben, nicht ergänzt.
  if (segments[0] === "tester" && actorId) {
    url.searchParams.set("user_id", actorId);
  }

  // Die Community-Vorlagen zeigen, wie DER ANGEMELDETE Nutzer
  // abgestimmt hat. Die ID kommt aus der Sitzung, nie aus dem Browser
  // -- sonst liest jeder die Stimmen eines anderen aus, indem er eine
  // fremde ID in die URL schreibt. Ein mitgeschickter Wert wird
  // überschrieben, nicht ergänzt.
  if (segments[0] === "templates" && request.method === "GET") {
    url.searchParams.set("user_id", actorId ?? "");
  }

  // Die Befehls-Statistik zeigt die Namen jedes Servers, auf dem der
  // Bot ist. Der Bot maskiert sie für alle außer Ownern -- dafür muss
  // er wissen, wer fragt. Die ID kommt aus der Sitzung, nie aus dem
  // Browser: ein mitgeschickter Wert wird überschrieben, sonst setzt
  // sich jeder eine Owner-ID in die URL.
  if (segments[0] === "admin" && segments[1] === "command-stats") {
    url.searchParams.set("actor", actorId ?? "");
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
