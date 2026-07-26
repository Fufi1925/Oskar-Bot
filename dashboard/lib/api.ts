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
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { detail: "An unknown error occurred" };
      }
      console.error(`[API HTTP Error] Status ${response.status} for ${url}:`, errorData);
      throw new ApiError(response.status, errorData.detail || response.statusText);
    }

    return response.json();
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
