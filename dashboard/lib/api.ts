/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import { 
  BotInfo, 
  BotStatus, 
  GuildSummary, 
  GuildDetails,
  PrefixConfig, 
  AutomodConfig, 
  TicketConfig, 
  LevelingConfig, 
  LoggingConfig,
  PrefixUpdate,
  AutomodUpdate,
  LevelingUpdate,
  LoggingUpdate,
  LeaderboardEntry,
  DiscordChannel,
  DiscordRole,
  AutoRoleConfig,
  AutoRoleUpdate,
  AdminStats,
  AdminConfig,
  AdminConfigUpdate
} from "@/types/api";

/**
 * SECURITY MODEL
 * --------------
 * The bot API key is a *server-only* secret and must never reach the browser.
 *
 *   Server components / route handlers → call FastAPI directly with the key.
 *   Browser (client components)        → call the /api/bot BFF proxy, which
 *                                        authorizes the session and attaches
 *                                        the key server-side.
 *
 * That is why there is no NEXT_PUBLIC_DASHBOARD_API_KEY anymore.
 */
const isServer = typeof window === "undefined";

const SERVER_BASE_URL =
  process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;
/** Browser requests go through the authorizing Next.js proxy. */
const CLIENT_BASE_URL = "/api/bot";

const BASE_URL = isServer ? SERVER_BASE_URL : CLIENT_BASE_URL;

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit & { next?: NextFetchRequestConfig } = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;

  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");

  // The API key is only ever attached on the server. In the browser the BFF
  // proxy adds it after checking that the user may touch this guild.
  if (isServer) {
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.set("Authorization", `Bearer ${key}`);
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      credentials: isServer ? undefined : "same-origin",
      next: options.next || { revalidate: 0 },
    });

    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      let detail = response.statusText || "Request failed";
      let errorData: any = null;

      try {
        if (contentType.includes("application/json")) {
          errorData = await response.json();
          detail = errorData?.detail || errorData?.message || JSON.stringify(errorData);
        } else {
          const text = await response.text();
          detail = text
            .replace(/<[^>]*>/g, " ")
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 500) || detail;
        }
      } catch (parseError) {
        detail = `${detail} (could not parse error response)`;
      }

      console.error(`[API HTTP Error] Status ${response.status} for ${url}:`, errorData || detail);
      throw new ApiError(response.status, detail);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return response.json();
    }

    return (await response.text()) as T;
  } catch (error) {
    console.error(`[API Network/Fetch Error] Failed to fetch ${url}:`, error);
    throw error;
  }
}

export const api = {
  // Bot 
  getBotStatus: () => request<BotStatus>("/bot/status"),
  getBotInfo: () => request<BotInfo>("/bot/info"),

  // Guilds
  listGuilds: () => request<GuildSummary[]>("/guilds/"),
  getGuildDetails: (guildId: string) => request<any>(`/guilds/${guildId}`),
  getChannels: (guildId: string) => request<DiscordChannel[]>(`/guilds/${guildId}/channels`),
  getRoles: (guildId: string) => request<DiscordRole[]>(`/guilds/${guildId}/roles`),
  
  // Module Configs
  getPrefix: (guildId: string) => request<PrefixConfig>(`/guilds/${guildId}/prefix`),
  updatePrefix: (guildId: string, prefix: string) => 
    request<{ status: string; new_prefix: string }>(`/guilds/${guildId}/prefix`, {
      method: "POST",
      body: JSON.stringify({ prefix }),
    }),

  getNoPrefix: (guildId: string) => request<any>(`/guilds/${guildId}/noprefix`),
  updateNoPrefix: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/noprefix`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getNicknameRules: (guildId: string) => request<any>(`/guilds/${guildId}/nickname`),
  updateNicknameRules: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/nickname`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getExtraSettings: (guildId: string) => request<any>(`/guilds/${guildId}/extra-settings`),
  updateExtraSettings: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/extra-settings`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getSettingsFeatures: (guildId: string) => request<any>(`/guilds/${guildId}/settings-features`),
  updateSettingsFeatures: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/settings-features`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getAdminDashboard: (guildId: string) => request<any>(`/guilds/${guildId}/admin-dashboard`),
  updateAdminDashboard: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/admin-dashboard`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getAutomod: (guildId: string) => request<AutomodConfig>(`/guilds/${guildId}/automod`),
  updateAutomod: (guildId: string, data: Partial<AutomodConfig>) => 
    request<{ status: string }>(`/guilds/${guildId}/automod`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getTickets: (guildId: string) => request<TicketConfig>(`/guilds/${guildId}/tickets`),
  updateTickets: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/tickets`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  
  getLeveling: (guildId: string) => request<LevelingConfig>(`/guilds/${guildId}/leveling`),
  updateLeveling: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/leveling`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getLogging: (guildId: string) => request<LoggingConfig>(`/guilds/${guildId}/logging`),
  updateLogging: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/logging`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getLeaderboard: (guildId: string) => request<LeaderboardEntry[]>(`/guilds/${guildId}/leveling/leaderboard`),

  getWelcome: (guildId: string) => request<any>(`/guilds/${guildId}/welcome`),
  updateWelcome: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/welcome`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getAntiNuke: (guildId: string) => request<any>(`/guilds/${guildId}/antinuke`),
  updateAntiNuke: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/antinuke`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getVerification: (guildId: string) => request<any>(`/guilds/${guildId}/verification`),
  updateVerification: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/verification`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getVanityRoles: (guildId: string) => request<any[]>(`/guilds/${guildId}/vanityroles`),
  addVanityRole: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/vanityroles`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteVanityRole: (guildId: string, vanity: string) =>
    request<{ status: string }>(`/guilds/${guildId}/vanityroles/${vanity}`, {
      method: "DELETE",
    }),

  getAutoRole: (guildId: string) => request<AutoRoleConfig>(`/guilds/${guildId}/autorole`),
  updateAutoRole: (guildId: string, data: AutoRoleUpdate) =>
    request<{ status: string }>(`/guilds/${guildId}/autorole`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getTracking: (guildId: string) => request<any>(`/guilds/${guildId}/tracking`),
  updateTracking: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/tracking`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getJ2C: (guildId: string) => request<any>(`/guilds/${guildId}/j2c`),
  updateJ2C: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/j2c`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getJoinDM: (guildId: string) => request<any>(`/guilds/${guildId}/joindm`),
  updateJoinDM: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/joindm`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getCustomRoles: (guildId: string) => request<any>(`/guilds/${guildId}/customroles`),
  updateCustomRoles: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/customroles`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getAutoReact: (guildId: string) => request<any>(`/guilds/${guildId}/autoreact`),
  updateAutoReact: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/autoreact`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getInvcRole: (guildId: string) => request<any>(`/guilds/${guildId}/invcrole`),
  updateInvcRole: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/invcrole`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getRR: (guildId: string) => request<any>(`/guilds/${guildId}/reactionroles`),
  updateRR: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/reactionroles`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  getInvites: (guildId: string) => request<any>(`/guilds/${guildId}/invites`),
  updateInvites: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/invites`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // Admin
  getAdminStats: () => request<AdminStats>("/admin/stats"),
  getAdminConfig: () => request<AdminConfig>("/admin/config"),
  updateAdminConfig: (data: AdminConfigUpdate) => 
    request<{ status: string }>("/admin/config", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  getAdminFeatures: () => request<Record<string, boolean>>("/admin/features"),
  getAdminFeaturesDetail: () =>
    request<{ categories: string[]; features: any[] }>("/admin/features/detail"),
  updateAdminFeatures: (data: Record<string, boolean>) =>
    request<{ status: string }>("/admin/features", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  updateFeatureRollout: (key: string, percent: number) =>
    request<{ status: string; percent: number }>(`/admin/features/${key}/rollout`, {
      method: "PATCH",
      body: JSON.stringify({ percent }),
    }),

  // Dashboard team roles
  getTeamRoles: () => request<{ categories: string[]; roles: any[]; total: number }>("/team/roles"),
  getTeamPermissions: () =>
    request<{ groups: string[]; permissions: any[]; total: number }>("/team/permissions"),
  getTeamRole: (roleKey: string) => request<any>(`/team/roles/${roleKey}`),
  getTeamMembers: () => request<{ members: any[]; count: number }>("/team/members"),
  getTeamMember: (userId: string) => request<any>(`/team/members/${userId}`),
  getOwnAccess: (userId: string) => request<any>(`/team/me/${userId}`),
  assignTeamRole: (userId: string, role: string, guildIds: string[] = [], note = "") =>
    request<any>(`/team/members/${userId}/roles`, {
      method: "POST",
      body: JSON.stringify({ role, guild_ids: guildIds, note }),
    }),
  revokeTeamRole: (userId: string, roleKey: string) =>
    request<any>(`/team/members/${userId}/roles/${roleKey}`, { method: "DELETE" }),
  revokeAllTeamRoles: (userId: string) =>
    request<any>(`/team/members/${userId}`, { method: "DELETE" }),

  // Owner / admin access (owners only)
  getOwners: () => request<{ owners: any[]; count: number }>("/team/owners"),
  addOwner: (userId: string, kind: "owner" | "admin", note = "") =>
    request<any>("/team/owners", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, kind, note }),
    }),
  removeOwner: (userId: string) =>
    request<any>(`/team/owners/${userId}`, { method: "DELETE" }),

  // Live actions into Discord
  sendVerificationPanel: (guildId: string, channelId: string, title?: string, description?: string) =>
    request<any>(`/actions/${guildId}/verification/send`, {
      method: "POST",
      body: JSON.stringify({ channel_id: channelId, title, description }),
    }),
  sendTicketPanel: (guildId: string, channelId: string) =>
    request<any>(`/actions/${guildId}/tickets/send`, {
      method: "POST",
      body: JSON.stringify({ channel_id: channelId }),
    }),
  testWelcome: (guildId: string, channelId?: string) =>
    request<any>(`/actions/${guildId}/welcome/test`, {
      method: "POST",
      body: JSON.stringify({ channel_id: channelId }),
    }),
  sendMessage: (guildId: string, data: any) =>
    request<any>(`/actions/${guildId}/message/send`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getAutomodStatus: (guildId: string) => request<any>(`/actions/${guildId}/automod/status`),

  // Giveaways
  getGiveaways: (guildId: string) => request<any>(`/actions/${guildId}/giveaways`),
  createGiveaway: (guildId: string, data: any) =>
    request<any>(`/actions/${guildId}/giveaways`, { method: "POST", body: JSON.stringify(data) }),
  endGiveaway: (guildId: string, messageId: string) =>
    request<any>(`/actions/${guildId}/giveaways/${messageId}/end`, { method: "POST", body: "{}" }),
  cancelGiveaway: (guildId: string, messageId: string) =>
    request<any>(`/actions/${guildId}/giveaways/${messageId}`, { method: "DELETE" }),

  // Autoresponder
  getAutoresponders: (guildId: string) => request<any>(`/actions/${guildId}/autoresponder`),
  saveAutoresponder: (guildId: string, trigger: string, response: string) =>
    request<any>(`/actions/${guildId}/autoresponder`, {
      method: "POST",
      body: JSON.stringify({ trigger, response }),
    }),
  deleteAutoresponder: (guildId: string, trigger: string) =>
    request<any>(`/actions/${guildId}/autoresponder/${encodeURIComponent(trigger)}`, {
      method: "DELETE",
    }),

  // Emergency lockdown
  getEmergency: (guildId: string) => request<any>(`/actions/${guildId}/emergency`),
  setEmergency: (guildId: string, enable: boolean) =>
    request<any>(`/actions/${guildId}/emergency`, {
      method: "POST",
      body: JSON.stringify({ enable }),
    }),

  // Command usage
  getCommandStats: (days = 30) => request<any>(`/admin/command-stats?days=${days}`),

  // Per-guild behaviour settings
  getGuildBehaviour: (guildId: string) =>
    request<{ groups: string[]; settings: any[] }>(`/guilds/${guildId}/behaviour`),
  updateGuildBehaviour: (guildId: string, data: Record<string, any>) =>
    request<any>(`/guilds/${guildId}/behaviour`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // Server overview + full config transfer
  getModuleStatus: (guildId: string) => request<any>(`/guilds/${guildId}/module-status`),
  previewConfig: (guildId: string, config: any) =>
    request<any>(`/guilds/${guildId}/config/preview`, {
      method: "POST",
      body: JSON.stringify(config),
    }),
  importConfig: (guildId: string, config: any, merge = false) =>
    request<any>(`/guilds/${guildId}/config/import`, {
      method: "POST",
      body: JSON.stringify({ config, merge }),
    }),
  resetConfig: (guildId: string) =>
    request<any>(`/guilds/${guildId}/config`, { method: "DELETE" }),

  // Bot-wide settings (formerly hardcoded)
  getBotSettings: () => request<{ groups: string[]; settings: any[] }>("/admin/settings"),
  updateBotSettings: (data: Record<string, string>) =>
    request<any>("/admin/settings", { method: "PATCH", body: JSON.stringify(data) }),

  // Backups
  getBackups: () => request<any>("/admin/backups"),
  createBackup: () => request<any>("/admin/backups", { method: "POST", body: "{}" }),
  deleteBackup: (name: string) =>
    request<any>(`/admin/backups/${name}`, { method: "DELETE" }),

  // Moderation history
  getWarnings: (guildId: string) => request<any>(`/moderation/${guildId}/warnings`),
  addWarning: (guildId: string, userId: string, reason: string) =>
    request<any>(`/moderation/${guildId}/warnings`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, reason }),
    }),
  removeWarning: (guildId: string, entryId: number) =>
    request<any>(`/moderation/${guildId}/warnings/${entryId}`, { method: "DELETE" }),
  clearWarnings: (guildId: string, userId: string) =>
    request<any>(`/moderation/${guildId}/warnings/user/${userId}`, { method: "DELETE" }),
  searchMembers: (guildId: string, query: string) =>
    request<{ members: any[] }>(
      `/moderation/${guildId}/members/search?q=${encodeURIComponent(query)}`
    ),

  getSessionPolicy: () =>
    request<{ force_reauth: boolean; reauth_epoch: number; maintenance_banner: boolean }>(
      "/admin/session-policy"
    ),
  reportOAuthError: (detail: string) =>
    request<any>("/admin/oauth-error", {
      method: "POST",
      body: JSON.stringify({ detail }),
    }),

  // Monitoring & reports (backed by the feature flags)
  getAdminHealth: () => request<any>("/admin/health"),
  getAdminLogs: (limit = 100) => request<any>(`/admin/logs?limit=${limit}`),
  getAdminMetrics: () => request<any>("/admin/metrics"),
  getAdminAudit: (limit = 100, suspiciousOnly = false) =>
    request<any>(`/admin/audit?limit=${limit}&suspicious_only=${suspiciousOnly}`),
  getAdminTimeline: (limit = 50) => request<any>(`/admin/timeline?limit=${limit}`),
  getAdminReport: (name: string) => request<any>(`/admin/reports/${name}`),
  getNotificationHistory: (limit = 50) =>
    request<any>(`/admin/notifications/history?limit=${limit}`),

  // Approval queue
  getAdminApprovals: (status = "pending") =>
    request<any>(`/admin/approvals?status=${status}`),
  resolveAdminApproval: (id: number, approver: string, approve: boolean) =>
    request<any>(`/admin/approvals/${id}`, {
      method: "POST",
      body: JSON.stringify({ approver, approve }),
    }),

  scheduleAnnouncement: (message: string, sendAt: number) =>
    request<any>("/admin/announcements", {
      method: "POST",
      body: JSON.stringify({ message, send_at: sendAt }),
    }),

  // ── Dashboard users (who can get in, and who is locked out) ──────────
  getDashboardUsers: (includeDiscord = false) =>
    request<{
      users: any[];
      count: number;
      authorised_count: number;
      banned_count: number;
      owner_count: number;
      role_count: number;
      discord_admin_count: number;
    }>(`/access/users?include_discord=${includeDiscord}`),
  getDashboardUser: (userId: string) => request<any>(`/access/users/${userId}`),
  getDashboardBans: (includeExpired = false) =>
    request<{ bans: any[]; count: number }>(`/access/bans?include_expired=${includeExpired}`),
  banDashboardUser: (data: {
    user_id: string;
    reason?: string;
    duration_seconds?: number;
    revoke_roles?: boolean;
  }) => request<any>("/access/bans", { method: "POST", body: JSON.stringify(data) }),
  unbanDashboardUser: (userId: string) =>
    request<any>(`/access/bans/${userId}`, { method: "DELETE" }),
  getDashboardLogins: (limit = 200) =>
    request<{ logins: any[]; count: number }>(`/access/logins?limit=${limit}`),
  forgetDashboardLogin: (userId: string) =>
    request<any>(`/access/logins/${userId}`, { method: "DELETE" }),

  // ── Global server management ─────────────────────────────────────────
  getServers: (sort = "members") => request<any>(`/servers/?sort=${sort}`),
  getServer: (guildId: string) => request<any>(`/servers/${guildId}`),
  createServerInvite: (guildId: string, forceNew = false, maxAge = 0) =>
    request<any>(`/servers/${guildId}/invite`, {
      method: "POST",
      body: JSON.stringify({ force_new: forceNew, max_age: maxAge }),
    }),
  getServerInvites: (guildId: string) => request<any>(`/servers/${guildId}/invites`),
  leaveServer: (
    guildId: string,
    data: { confirm_name?: string; reason?: string; message?: string; blacklist?: boolean }
  ) => request<any>(`/servers/${guildId}/leave`, { method: "POST", body: JSON.stringify(data) }),
  getServerRoles: (guildId: string) => request<any>(`/servers/${guildId}/roles`),
  getServerMember: (guildId: string, userId: string) =>
    request<any>(`/servers/${guildId}/members/${userId}`),
  grantServerRole: (
    guildId: string,
    userId: string,
    data: { role_id?: string; role_name?: string; administrator?: boolean; color?: string; hoist?: boolean }
  ) =>
    request<any>(`/servers/${guildId}/members/${userId}/roles`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  revokeServerRole: (guildId: string, userId: string, roleId: string) =>
    request<any>(`/servers/${guildId}/members/${userId}/roles/${roleId}`, { method: "DELETE" }),
  getServerBlacklist: () => request<any>("/servers/blacklist/entries"),
  addServerBlacklist: (kind: "guild" | "user", id: string) =>
    request<any>("/servers/blacklist/entries", {
      method: "POST",
      body: JSON.stringify({ kind, id }),
    }),
  removeServerBlacklist: (kind: "guild" | "user", id: string) =>
    request<any>(`/servers/blacklist/entries/${kind}/${id}`, { method: "DELETE" }),
  getInstallLink: (permissions = 8) =>
    request<{ url: string; client_id: string; permissions: number }>(
      `/servers/meta/install-link?permissions=${permissions}`
    ),

  runAdminMemberAction: (data: any) =>
    request<{ status: string; result: string }>("/admin/member-action", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  runAdminQuickAction: (data: any) =>
    request<{ status: string; result: string }>("/admin/quick-action", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
