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

  // Automod moved to /automod: the old /guilds pair stored whatever key
  // the dashboard sent, and the dashboard sent names no listener used --
  // so nothing set in the tab ever reached the bot.
  getAutomod: (g: string) => request<any>(`/automod/${g}`),
  updateAutomod: (g: string, data: any) =>
    request<any>(`/automod/${g}`, { method: "PATCH", body: JSON.stringify(data) }),
  resetAutomod: (g: string, keepRules = true) =>
    request<any>(`/automod/${g}/reset`, {
      method: "POST",
      body: JSON.stringify({ keep_rules: keepRules }),
    }),

  getTickets: (guildId: string) => request<TicketConfig>(`/guilds/${guildId}/tickets`),
  updateTickets: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/tickets`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  
  // Leveling
  // Moved off /guilds to its own router: the old pair of routes exposed
  // five of twelve settings and nothing at all for rewards, multipliers,
  // exclusions or the member list.
  getLeveling: (guildId: string) => request<any>(`/leveling/${guildId}`),
  updateLeveling: (guildId: string, data: any) =>
    request<any>(`/leveling/${guildId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  getLevelingBoard: (guildId: string, page = 1, perPage = 25) =>
    request<any>(`/leveling/${guildId}/leaderboard?page=${page}&per_page=${perPage}`),
  setLevelingMember: (guildId: string, userId: string, data: any) =>
    request<any>(`/leveling/${guildId}/members/${userId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  resetLevelingMember: (guildId: string, userId: string) =>
    request<any>(`/leveling/${guildId}/members/${userId}`, { method: "DELETE" }),
  resetLevelingAll: (guildId: string) =>
    request<any>(`/leveling/${guildId}/members`, { method: "DELETE" }),
  addLevelReward: (guildId: string, level: number, roleId: string) =>
    request<any>(`/leveling/${guildId}/rewards`, {
      method: "POST",
      body: JSON.stringify({ level, role_id: roleId }),
    }),
  removeLevelReward: (guildId: string, level: number) =>
    request<any>(`/leveling/${guildId}/rewards/${level}`, { method: "DELETE" }),
  /** Hand out reward roles people already earned but never received. */
  syncLevelRewards: (guildId: string) =>
    request<any>(`/leveling/${guildId}/rewards/sync`, { method: "POST", body: "{}" }),
  addLevelMultiplier: (guildId: string, data: any) =>
    request<any>(`/leveling/${guildId}/multipliers`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  removeLevelMultiplier: (guildId: string, type: string, id: string) =>
    request<any>(`/leveling/${guildId}/multipliers/${type}/${id}`, { method: "DELETE" }),
  addLevelExcluded: (guildId: string, data: any) =>
    request<any>(`/leveling/${guildId}/excluded`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  removeLevelExcluded: (guildId: string, type: string, id: string) =>
    request<any>(`/leveling/${guildId}/excluded/${type}/${id}`, { method: "DELETE" }),
  /** What every level costs, worked out from the guild's own XP rate. */
  getLevelCurve: (guildId: string, upTo = 50) =>
    request<any>(`/leveling/${guildId}/curve?up_to=${upTo}`),
  /** Colour ramps, name styles and spacings for the automatic ladder. */
  getLadderOptions: (guildId: string) =>
    request<any>(`/leveling/${guildId}/ladder/options`),
  /** Work out the ladder without creating any roles. */
  previewLadder: (guildId: string, data: any) =>
    request<any>(`/leveling/${guildId}/ladder/preview`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  /** Create the roles, colour them, order them and wire them up. */
  createLadder: (guildId: string, data: any) =>
    request<any>(`/leveling/${guildId}/ladder`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  previewLevelUp: (guildId: string, data: any) =>
    request<any>(`/leveling/${guildId}/preview`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /**
   * Logging moved off /guilds onto its own router.
   *
   * The pair under /guilds knew six of the cog's nine categories and
   * could not touch the ignore lists at all.
   */
  getLogging: (guildId: string) => request<any>(`/logging/${guildId}`),
  updateLogging: (guildId: string, data: any) =>
    request<any>(`/logging/${guildId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  testLogging: (guildId: string, category: string) =>
    request<any>(`/logging/${guildId}/test/${category}`, { method: "POST" }),
  setAllLogging: (guildId: string, channel: string, includeNoisy = false) =>
    request<any>(`/logging/${guildId}/all`, {
      method: "POST",
      body: JSON.stringify({ channel, include_noisy: includeNoisy }),
    }),

  /**
   * The leaderboard as a flat array, for the standalone page.
   *
   * The old /guilds/{id}/leveling/leaderboard route read the abandoned
   * `user_xp` table, so it disagreed with everything else once anybody
   * had used an admin command.
   */
  getLeaderboard: async (guildId: string): Promise<LeaderboardEntry[]> => {
    const data = await request<any>(`/leveling/${guildId}/leaderboard?per_page=100`);
    return (data?.entries || []) as LeaderboardEntry[];
  },

  getWelcome: (guildId: string) => request<any>(`/guilds/${guildId}/welcome`),
  updateWelcome: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/welcome`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  /**
   * Anti-nuke moved off /guilds onto its own router.
   *
   * The pair under /guilds could only add a whitelist entry with every
   * action allowed — a complete bypass of all seventeen protections —
   * and did nothing at all when the table did not exist yet.
   */
  getAntiNuke: (guildId: string) => request<any>(`/antinuke/${guildId}`),
  updateAntiNuke: (guildId: string, data: any) =>
    request<any>(`/antinuke/${guildId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  setAntiNukeWhitelist: (
    guildId: string,
    userId: string,
    actions: Record<string, boolean>
  ) =>
    request<any>(`/antinuke/${guildId}/whitelist/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ actions }),
    }),
  removeAntiNukeWhitelist: (guildId: string, userId: string) =>
    request<any>(`/antinuke/${guildId}/whitelist/${userId}`, {
      method: "DELETE",
    }),

  // The verification tab moved to /verify: the old /guilds handlers knew
  // five columns and wrote 0 for "not set", which the read side then
  // handed back as if it were a real channel id.
  getVerify: (g: string) => request<any>(`/verify/${g}`),
  updateVerify: (g: string, data: any) =>
    request<any>(`/verify/${g}`, { method: "PATCH", body: JSON.stringify(data) }),
  postVerifyPanel: (g: string) =>
    request<any>(`/verify/${g}/panel`, { method: "POST", body: "{}" }),
  previewVerifyPanel: (g: string, draft: any = {}) =>
    request<any>(`/verify/${g}/preview`, {
      method: "POST",
      body: JSON.stringify(draft || {}),
    }),
  resetVerify: (g: string, keepTexts = true) =>
    request<any>(`/verify/${g}/reset`, {
      method: "POST",
      body: JSON.stringify({ keep_texts: keepTexts }),
    }),
  verifyMemberManually: (g: string, userId: string) =>
    request<any>(`/verify/${g}/verify/${userId}`, { method: "POST", body: "{}" }),
  unverifyMember: (g: string, userId: string) =>
    request<any>(`/verify/${g}/verify/${userId}`, { method: "DELETE" }),

  getVerification: (guildId: string) => request<any>(`/guilds/${guildId}/verification`),
  updateVerification: (guildId: string, data: any) => 
    request<{ status: string }>(`/guilds/${guildId}/verification`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // Join DM, no-prefix and reaction roles
  // Moved off /guilds: no-prefix leaked across servers, join DM had no
  // flag that survived a restart, and adding a reaction role never put
  // the reaction on the message.
  getJoinDM: (guildId: string) => request<any>(`/perks/${guildId}/joindm`),
  updateJoinDM: (guildId: string, data: any) =>
    request<any>(`/perks/${guildId}/joindm`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  testJoinDM: (guildId: string, draft?: any) =>
    request<any>(`/perks/${guildId}/joindm/test`, {
      method: "POST",
      body: JSON.stringify(draft || {}),
    }),

  getNoPrefix: (guildId: string) => request<any>(`/perks/${guildId}/noprefix`),
  addNoPrefixUser: (guildId: string, data: any) =>
    request<any>(`/perks/${guildId}/noprefix/users`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  removeNoPrefixUser: (guildId: string, userId: string, scope = "guild") =>
    request<any>(`/perks/${guildId}/noprefix/users/${userId}?scope=${scope}`, {
      method: "DELETE",
    }),
  addNoPrefixRole: (guildId: string, roleId: string) =>
    request<any>(`/perks/${guildId}/noprefix/roles`, {
      method: "POST",
      body: JSON.stringify({ role_id: roleId }),
    }),
  removeNoPrefixRole: (guildId: string, roleId: string) =>
    request<any>(`/perks/${guildId}/noprefix/roles/${roleId}`, { method: "DELETE" }),

  getReactionRolesV2: (guildId: string) =>
    request<any>(`/perks/${guildId}/reactionroles`),
  addReactionRoleV2: (guildId: string, data: any) =>
    request<any>(`/perks/${guildId}/reactionroles`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  removeReactionRoleV2: (
    guildId: string, messageId: string, emoji: string, channelId = ""
  ) =>
    request<any>(
      `/perks/${guildId}/reactionroles?message_id=${messageId}` +
        `&emoji=${encodeURIComponent(emoji)}&channel_id=${channelId}`,
      { method: "DELETE" }
    ),
  updateReactionRoleSettings: (guildId: string, data: any) =>
    request<any>(`/perks/${guildId}/reactionroles`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  /** Walk every entry: deleted messages, deleted roles, cleared reactions. */
  verifyReactionRoles: (guildId: string) =>
    request<any>(`/perks/${guildId}/reactionroles/verify`, {
      method: "POST",
      body: "{}",
    }),

  // Booster, sticky, nightmode, jail, counting, notify
  // Seven features that worked in chat but had no dashboard. Every write
  // tells the owning cog to reload -- several keep state in memory.
  getBooster: (g: string) => request<any>(`/extras/${g}/booster`),
  updateBooster: (g: string, data: any) =>
    request<any>(`/extras/${g}/booster`, { method: "PATCH", body: JSON.stringify(data) }),
  testBooster: (g: string, data: any) =>
    request<any>(`/extras/${g}/booster/test`, { method: "POST", body: JSON.stringify(data) }),

  getSticky: (g: string) => request<any>(`/extras/${g}/sticky`),
  setSticky: (g: string, data: any) =>
    request<any>(`/extras/${g}/sticky`, { method: "POST", body: JSON.stringify(data) }),
  removeSticky: (g: string, channelId: string) =>
    request<any>(`/extras/${g}/sticky/${channelId}`, { method: "DELETE" }),

  getNightmode: (g: string) => request<any>(`/extras/${g}/nightmode`),
  updateNightmode: (g: string, data: any) =>
    request<any>(`/extras/${g}/nightmode`, { method: "PATCH", body: JSON.stringify(data) }),
  toggleNightmode: (g: string, close: boolean) =>
    request<any>(`/extras/${g}/nightmode/toggle`, {
      method: "POST", body: JSON.stringify({ close }),
    }),

  getJail: (g: string) => request<any>(`/extras/${g}/jail`),
  updateJail: (g: string, data: any) =>
    request<any>(`/extras/${g}/jail`, { method: "PATCH", body: JSON.stringify(data) }),
  setupJail: (g: string) =>
    request<any>(`/extras/${g}/jail/setup`, { method: "POST", body: "{}" }),

  getCounting: (g: string) => request<any>(`/extras/${g}/counting`),
  updateCounting: (g: string, data: any) =>
    request<any>(`/extras/${g}/counting`, { method: "PATCH", body: JSON.stringify(data) }),
  resetCounting: (g: string, keepRecord = true) =>
    request<any>(`/extras/${g}/counting/reset`, {
      method: "POST",
      body: JSON.stringify({ keep_record: keepRecord }),
    }),
  announceCounting: (g: string) =>
    request<any>(`/extras/${g}/counting/announce`, { method: "POST", body: "{}" }),

  /**
   * Premium licence keys.
   *
   * `redeemKey` deliberately sends no user id: the proxy fills it in
   * from the session, so a key can only ever be bound to the account
   * that is actually signed in.
   */
  getMyPremium: (userId: string) => request<any>(`/premium/me/${userId}`),
  redeemKey: (key: string) =>
    request<any>(`/premium/redeem`, { method: "POST", body: JSON.stringify({ key }) }),
  listPremiumKeys: (limit = 100) =>
    request<any>(`/premium/keys?limit=${limit}`),
  createPremiumKey: (data: { days: number; user_id?: string; note?: string }) =>
    request<any>(`/premium/keys`, { method: "POST", body: JSON.stringify(data) }),
  revokePremiumKey: (keyHash: string, undo = false) =>
    request<any>(`/premium/revoke`, {
      method: "POST",
      body: JSON.stringify({ key_hash: keyHash, undo }),
    }),
  deletePremiumKey: (keyHash: string) =>
    request<any>(`/premium/delete`, {
      method: "POST",
      body: JSON.stringify({ key_hash: keyHash }),
    }),
  purgePremiumKeys: (what: "revoked" | "expired" | "unclaimed") =>
    request<any>(`/premium/purge`, {
      method: "POST",
      body: JSON.stringify({ what }),
    }),

  /**
   * YouTube subscriptions: a channel name, where to post, who to ping.
   *
   * Replaces the pair that stored a role and channel per "type" and
   * watched members' Discord streaming status instead of YouTube.
   */
  getNotify: (g: string) => request<any>(`/extras/${g}/notify`),
  addNotify: (g: string, data: any) =>
    request<any>(`/extras/${g}/notify`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateNotify: (g: string, channelId: string, data: any) =>
    request<any>(`/extras/${g}/notify/${channelId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  testNotify: (g: string, channelId: string) =>
    request<any>(`/extras/${g}/notify/${channelId}/test`, { method: "POST" }),
  removeNotify: (g: string, channelId: string) =>
    request<any>(`/extras/${g}/notify/${channelId}`, { method: "DELETE" }),


  // Anti-nuke alerts
  getNukeAlerts: (guildId: string) => request<any>(`/nukealert/${guildId}`),
  updateNukeAlerts: (guildId: string, data: any) =>
    request<any>(`/nukealert/${guildId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  /** Post a sample report, so a broken setup shows up before an attack. */
  testNukeAlert: (guildId: string) =>
    request<any>(`/nukealert/${guildId}/test`, { method: "POST", body: "{}" }),
  /** One-click link that adds the template bot and tells it we sent it. */
  getPartnerInvite: (guildId: string) =>
    request<any>(`/nukealert/${guildId}/partner-invite`),

  // Compose: design a message and post it as the bot
  /** Validate before sending — Discord's own 400 names no field. */
  checkMessage: (guildId: string, data: any) =>
    request<any>(`/compose/${guildId}/check`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  sendComposed: (guildId: string, data: any) =>
    request<any>(`/compose/${guildId}/send`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  /**
   * Which bots can post here. One answer everywhere except the support
   * server, where the status bot can post too.
   */
  getSenders: (guildId: string) => request<any>(`/compose/${guildId}/senders`),

  /**
   * Die eigenen Emojis des Bots, gruppiert.
   *
   * Serverunabhängig: es geht um die Emojis, die der Bot mitbringt,
   * nicht um die eines bestimmten Servers.
   */
  getBotEmojis: () => request<any>(`/compose/emojis`),
  // Die Begruessungs-Vorlagen kommen vom Bot, damit die Emoji-Codes
  // aus derselben Quelle stammen wie die Auswahl. Eine zweite Liste
  // hier liefe beim ersten neuen Emoji auseinander.
  getWelcomeTemplates: () => request<any>(`/compose/templates/welcome`),

  // ── Tester-Bereich ────────────────────────────────────────────────
  // Die user_id setzt der Proxy aus der Sitzung; sie hier mitzugeben
  // hätte keine Wirkung.
  testerStatus: () => request<any>(`/tester/status`),
  testerChangelog: (limit = 40) =>
    request<any>(`/tester/changelog?limit=${limit}`),
  testerFeedback: (limit = 100) =>
    request<any>(`/tester/feedback?limit=${limit}`),
  testerFeedbackFiltered: (limit = 100, state = "", kind = "") =>
    request<any>(
      `/tester/feedback?limit=${limit}` +
        `&state=${encodeURIComponent(state)}&kind=${encodeURIComponent(kind)}`
    ),
  testerDetail: (id: number) => request<any>(`/tester/feedback/${id}`),
  testerOptions: () => request<any>(`/tester/feedback-options`),
  testerSubmit: (payload: {
    kind: string;
    title: string;
    body: string;
    area?: string;
    priority?: string;
  }) =>
    request<any>(`/tester/feedback`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  testerComment: (id: number, text: string) =>
    request<any>(`/tester/feedback/${id}/comment`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  testerVote: (id: number) =>
    request<any>(`/tester/feedback/${id}/vote`, {
      method: "POST",
      body: "{}",
    }),
  testerUpdate: (id: number, patch: Record<string, unknown>) =>
    request<any>(`/tester/feedback/${id}`, {
      method: "POST",
      body: JSON.stringify(patch),
    }),
  testerMembers: () => request<any>(`/tester/members`),
  editComposed: (guildId: string, data: any) =>
    request<any>(`/compose/${guildId}/edit`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  fetchMessage: (guildId: string, channelId: string, messageId: string) =>
    request<any>(
      `/compose/${guildId}/fetch?channel_id=${channelId}&message_id=${messageId}`
    ),

  /** Why is nothing happening in Discord? Checks the running process. */
  diagnose: (guildId = "") =>
    request<any>(`/admin/diagnose${guildId ? `?guild_id=${guildId}` : ""}`),

  // Anonymous chat
  // The log deanonymises members, so every route here sits behind the
  // same permission as changing the settings.
  getAnonChat: (guildId: string) => request<any>(`/anonchat/${guildId}`),
  saveAnonChat: (guildId: string, data: any) =>
    request<any>(`/anonchat/${guildId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteAnonChat: (guildId: string, channelId: string) =>
    request<any>(`/anonchat/${guildId}/${channelId}`, { method: "DELETE" }),
  getAnonLog: (guildId: string, limit = 50, userId = "") =>
    request<any>(
      `/anonchat/${guildId}/log?limit=${limit}` +
        (userId ? `&user_id=${userId}` : "")
    ),
  blockAnonUser: (guildId: string, data: any) =>
    request<any>(`/anonchat/${guildId}/blocked`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  unblockAnonUser: (guildId: string, userId: string) =>
    request<any>(`/anonchat/${guildId}/blocked/${userId}`, { method: "DELETE" }),
  /** Run text through the same filters the relay uses. */
  previewAnonMessage: (guildId: string, data: any) =>
    request<any>(`/anonchat/${guildId}/preview`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Vanity roles
  // Moved off /guilds to their own router. The old routes stored the
  // trigger exactly as typed, so `.gg/MeinServer` and `discord.gg/meinserver` were
  // two separate setups that both looked correct in the dashboard.
  getVanityRoles: (guildId: string) => request<any>(`/vanity/${guildId}`),
  saveVanityRole: (guildId: string, data: any) =>
    request<any>(`/vanity/${guildId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteVanityRole: (guildId: string, vanity: string) =>
    request<any>(`/vanity/${guildId}/${encodeURIComponent(vanity)}`, {
      method: "DELETE",
    }),
  /** Who currently holds the role because of this trigger. */
  getVanityHolders: (guildId: string, vanity: string) =>
    request<any>(`/vanity/${guildId}/${encodeURIComponent(vanity)}/holders`),
  /** Walk every member once; presence events only fire on a change. */
  syncVanityRole: (guildId: string, vanity: string) =>
    request<any>(`/vanity/${guildId}/${encodeURIComponent(vanity)}/sync`, {
      method: "POST",
      body: "{}",
    }),
  /** Try a status against the trigger without touching anybody. */
  testVanityRole: (guildId: string, vanity: string, status: string) =>
    request<any>(`/vanity/${guildId}/${encodeURIComponent(vanity)}/test`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),

  // Admin broadcasts (owner only; lives under /admin)
  getBroadcasts: () => request<any>("/admin/broadcast"),
  getBroadcast: (id: number) => request<any>(`/admin/broadcast/${id}`),
  /** Work out where a broadcast would land, without sending. */
  previewBroadcast: (data: any) =>
    request<any>("/admin/broadcast/preview", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  /** Deliver to a single server first. */
  testBroadcast: (data: any) =>
    request<any>("/admin/broadcast/test", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  sendBroadcast: (data: any) =>
    request<any>("/admin/broadcast", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  cancelBroadcast: (id: number) =>
    request<any>(`/admin/broadcast/${id}/cancel`, { method: "POST", body: "{}" }),
  /** Retry only the servers where it did not arrive. */
  resendBroadcast: (id: number) =>
    request<any>(`/admin/broadcast/${id}/resend`, { method: "POST", body: "{}" }),

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

  // Join to create, voice roles and custom role commands moved to
  // /voice: the old /guilds handlers wrote fields the cogs never read.
  getJ2C: (guildId: string) => request<any>(`/voice/${guildId}/j2c`),
  updateJ2C: (guildId: string, data: any) =>
    request<any>(`/voice/${guildId}/j2c`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  postJ2CPanel: (guildId: string) =>
    request<any>(`/voice/${guildId}/j2c/panel`, { method: "POST", body: "{}" }),
  resetJ2C: (guildId: string) =>
    request<any>(`/voice/${guildId}/j2c/reset`, { method: "POST", body: "{}" }),


  getCustomRoles: (guildId: string) => request<any>(`/voice/${guildId}/customroles`),
  updateCustomRoles: (guildId: string, data: any) =>
    request<any>(`/voice/${guildId}/customroles`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  addCustomRole: (guildId: string, data: any) =>
    request<any>(`/voice/${guildId}/customroles`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteCustomRole: (guildId: string, name: string) =>
    request<any>(`/voice/${guildId}/customroles/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  getAutoReact: (guildId: string) => request<any>(`/guilds/${guildId}/autoreact`),
  updateAutoReact: (guildId: string, data: any) =>
    request<{ status: string }>(`/guilds/${guildId}/autoreact`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getVoiceRole: (guildId: string) => request<any>(`/voice/${guildId}/voicerole`),
  updateVoiceRole: (guildId: string, data: any) =>
    request<any>(`/voice/${guildId}/voicerole`, {
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
  /**
   * Send the welcome message into a channel to look at it.
   *
   * `draft` lets the dashboard preview unsaved changes: welcome_type,
   * welcome_message and embed_data are used as sent instead of what is
   * in the database.
   */
  testWelcome: (guildId: string, channelId?: string, draft?: any) =>
    request<any>(`/actions/${guildId}/welcome/test`, {
      method: "POST",
      body: JSON.stringify({ channel_id: channelId, ...(draft || {}) }),
    }),
  sendMessage: (guildId: string, data: any) =>
    request<any>(`/actions/${guildId}/message/send`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getAutomodStatus: (guildId: string) => request<any>(`/actions/${guildId}/automod/status`),

  // Giveaways
  // Giveaways moved to their own router: button entries, custom text,
  // DMs and rerolls.
  getGiveaways: (guildId: string) => request<any>(`/giveaways/${guildId}`),
  getGiveawayEntries: (guildId: string, messageId: string) =>
    request<any>(`/giveaways/${guildId}/${messageId}/entries`),
  /** Full detail: settings, entrants, per-user odds. */
  getGiveaway: (guildId: string, messageId: string) =>
    request<any>(`/giveaways/${guildId}/${messageId}`),
  /**
   * Change a running giveaway. Only the keys passed in are written, so a
   * caller can send `{ extend_minutes: 60 }` without touching anything else.
   */
  updateGiveaway: (guildId: string, messageId: string, data: any) =>
    request<any>(`/giveaways/${guildId}/${messageId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  /** Extra tickets or a guaranteed win for one entrant. Never public. */
  boostGiveawayEntrant: (guildId: string, messageId: string, data: any) =>
    request<any>(`/giveaways/${guildId}/${messageId}/boost`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  startGiveaway: (guildId: string, data: any) =>
    request<any>(`/giveaways/${guildId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  drawGiveaway: (guildId: string, messageId: string) =>
    request<any>(`/giveaways/${guildId}/${messageId}/end`, {
      method: "POST",
      body: "{}",
    }),
  rerollGiveaway: (guildId: string, messageId: string, count = 1) =>
    request<any>(`/giveaways/${guildId}/${messageId}/reroll`, {
      method: "POST",
      body: JSON.stringify({ count }),
    }),
  cancelGiveaway: (guildId: string, messageId: string) =>
    request<any>(`/giveaways/${guildId}/${messageId}`, { method: "DELETE" }),
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
  restoreBackup: (name: string) =>
    request<any>(`/admin/backups/${name}/restore`, { method: "POST", body: "{}" }),

  // Full backup — every server and every global setting in one file
  previewFullBackup: (config: any) =>
    request<any>("/admin/backups/preview-all", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  importFullBackup: (config: any, merge = false, includeGlobal = true) =>
    request<any>("/admin/backups/import-all", {
      method: "POST",
      body: JSON.stringify({ config, merge, include_global: includeGlobal }),
    }),

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

  // Per-guild server tools — every one of these reads the live guild.
  getServerOverview: (guildId: string) =>
    request<any>(`/servertools/${guildId}/overview`),
  runSecurityScan: (guildId: string) =>
    request<any>(`/servertools/${guildId}/security-scan`),
  getRoleAudit: (guildId: string) =>
    request<any>(`/servertools/${guildId}/roles/audit`),
  getChannelAudit: (guildId: string) =>
    request<any>(`/servertools/${guildId}/channels/audit`),
  getInviteAudit: (guildId: string) =>
    request<any>(`/servertools/${guildId}/invites/audit`),
  getWebhookAudit: (guildId: string) =>
    request<any>(`/servertools/${guildId}/webhooks/audit`),
  deleteWebhook: (guildId: string, webhookId: string) =>
    request<any>(`/servertools/${guildId}/webhooks/${webhookId}`, {
      method: "DELETE",
    }),

  // Actions — each one fixes something the scan reports.
  deleteGuildRole: (guildId: string, roleId: string) =>
    request<any>(`/servertools/${guildId}/roles/${roleId}`, { method: "DELETE" }),
  stripRoleAdmin: (guildId: string, roleId: string) =>
    request<any>(`/servertools/${guildId}/roles/${roleId}/strip-admin`, {
      method: "POST",
      body: "{}",
    }),
  cleanupUnusedRoles: (guildId: string) =>
    request<any>(`/servertools/${guildId}/roles/cleanup-unused`, {
      method: "POST",
      body: "{}",
    }),
  revokeInvite: (guildId: string, code: string) =>
    request<any>(`/servertools/${guildId}/invites/${code}`, { method: "DELETE" }),
  setVerificationLevel: (guildId: string, level: string) =>
    request<any>(`/servertools/${guildId}/verification-level`, {
      method: "POST",
      body: JSON.stringify({ level }),
    }),
  setChannelSlowmode: (guildId: string, channelId: string, seconds: number) =>
    request<any>(`/servertools/${guildId}/channels/${channelId}/slowmode`, {
      method: "POST",
      body: JSON.stringify({ seconds }),
    }),
  setLockdown: (guildId: string, lock: boolean) =>
    request<any>(`/servertools/${guildId}/lockdown`, {
      method: "POST",
      body: JSON.stringify({ lock }),
    }),

  // Ticket panels — one endpoint per section, so saving one part can
  // never blank another.
  getTicketPanels: (guildId: string) =>
    request<any>(`/tickets/${guildId}/panels`),
  getTicketNotify: (guildId: string) =>
    request<any>(`/tickets/${guildId}/notify`),
  saveTicketNotify: (guildId: string, data: any) =>
    request<any>(`/tickets/${guildId}/notify`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  updateTicketServer: (guildId: string, data: any) =>
    request<any>(`/tickets/${guildId}/server`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  createTicketPanel: (guildId: string, name: string) =>
    request<any>(`/tickets/${guildId}/panels`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  updateTicketPanel: (guildId: string, panelId: number, data: any) =>
    request<any>(`/tickets/${guildId}/panels/${panelId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteTicketPanel: (guildId: string, panelId: number) =>
    request<any>(`/tickets/${guildId}/panels/${panelId}`, { method: "DELETE" }),
  saveTicketCategory: (guildId: string, panelId: number, data: any) =>
    request<any>(`/tickets/${guildId}/panels/${panelId}/categories`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteTicketCategory: (guildId: string, categoryId: number) =>
    request<any>(`/tickets/${guildId}/categories/${categoryId}`, {
      method: "DELETE",
    }),
  postTicketPanel: (guildId: string, panelId: number) =>
    request<any>(`/tickets/${guildId}/panels/${panelId}/send`, {
      method: "POST",
      body: "{}",
    }),

  // Speedrun (Beta) — der Template-Bot baut, danach richtet dieser Bot ein.
  // Alles läuft über den University Bot; das Dashboard redet nie direkt
  // mit dem Template-Bot, weil dessen Partner-Token nicht in den Browser
  // gehört.
  speedrunPrecheck: (guildId: string, userId: string) =>
    request<any>(
      `/speedrun/${guildId}/precheck?user_id=${encodeURIComponent(userId)}`
    ),
  speedrunTemplates: (userId: string) =>
    request<any>(`/speedrun/templates?user_id=${encodeURIComponent(userId)}`),
  // Mit `template` kommt zurück, welche Schritte diese Vorlage
  // überhaupt hergibt. Ohne sie wären Schalter für Sachen an, die auf
  // diesem Server nie entstehen.
  speedrunSteps: (template = "") =>
    request<any>(
      template
        ? `/speedrun/steps?template=${encodeURIComponent(template)}`
        : `/speedrun/steps`
    ),
  speedrunStart: (guildId: string, data: any) =>
    request<any>(`/speedrun/${guildId}/start`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  speedrunFinish: (
    guildId: string,
    options: Record<string, boolean>,
    runId = ""
  ) =>
    request<any>(`/speedrun/${guildId}/finish`, {
      method: "POST",
      // run_id: der Bot lehnt ab, wenn der fertige Bau zu einem anderen
      // Durchlauf gehört. Sonst könnte ein 15 Minuten alter Job die
      // Einrichtung ein zweites Mal auslösen.
      body: JSON.stringify({ options, run_id: runId }),
    }),
  speedrunCancel: (guildId: string) =>
    request<any>(`/speedrun/${guildId}/cancel`, { method: "POST", body: "{}" }),

  // ── Ping-Reaktionen ──────────────────────────────────────────────
  pingReactions: () => request<any>(`/admin/ping-reactions`),
  pingReactionSave: (data: any) =>
    request<any>(`/admin/ping-reactions`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  pingReactionDelete: (userId: string) =>
    request<any>(`/admin/ping-reactions/${userId}`, { method: "DELETE" }),
  pingReactionToggle: (userId: string, enabled: boolean) =>
    request<any>(`/admin/ping-reactions/${userId}/toggle`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),

  // ── Support-Warteraum ────────────────────────────────────────────
  supportQueue: (guildId: string) =>
    request<any>(`/supportqueue/${guildId}`),
  supportQueueSave: (guildId: string, data: any) =>
    request<any>(`/supportqueue/${guildId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  supportQueueTest: (guildId: string) =>
    request<any>(`/supportqueue/${guildId}/test`, {
      method: "POST",
      body: "{}",
    }),

  // ── Community-Vorlagen ───────────────────────────────────────────
  templateScan: (guildId: string) =>
    request<any>(`/templates/${guildId}/scan`),
  templateUpload: (guildId: string, data: any) =>
    request<any>(`/templates/${guildId}/upload`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  templateList: (guildId: string, search = "", sort = "neu") =>
    request<any>(
      `/templates/${guildId}/list?search=${encodeURIComponent(search)}` +
        `&sort=${encodeURIComponent(sort)}`
    ),
  templateDetail: (guildId: string, id: number, key = "") =>
    request<any>(
      `/templates/${guildId}/template/${id}?key=${encodeURIComponent(key)}`
    ),
  templateDelete: (guildId: string, id: number) =>
    request<any>(`/templates/${guildId}/template/${id}`, { method: "DELETE" }),
  // Daumen hoch (1), runter (-1) oder Stimme zurückziehen (0).
  // Derselbe Daumen noch einmal nimmt sie ebenfalls zurück, das
  // entscheidet der Bot. Die Nutzer-ID setzt der Proxy aus der
  // Sitzung — sie steht bewusst NICHT in diesem Aufruf.
  // Der Stand des laufenden Umbaus. `since` ist die Zahl der bereits
  // gelesenen Protokollzeilen — zurück kommen nur die neuen.
  templateJob: (guildId: string, since = 0) =>
    request<any>(`/templates/${guildId}/job?since=${since}`),
  templateJobCancel: (guildId: string) =>
    request<any>(`/templates/${guildId}/job/cancel`, {
      method: "POST",
      body: "{}",
    }),
  templateVote: (guildId: string, id: number, vote: number) =>
    request<any>(`/templates/${guildId}/template/${id}/vote`, {
      method: "POST",
      body: JSON.stringify({ vote }),
    }),
  templatePreview: (guildId: string, data: any) =>
    request<any>(`/templates/${guildId}/preview`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  templateApply: (guildId: string, data: any) =>
    request<any>(`/templates/${guildId}/apply`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // Den eigenen Zugangscode noch einmal ansehen. Nur für den Server,
  // der die Vorlage hochgeladen hat — das prüft der Bot, nicht diese
  // Zeile.
  templateKey: (guildId: string, id: number) =>
    request<any>(`/templates/${guildId}/template/${id}/key`),

  // ── Vorlagen-Verwaltung (nur globale Admins) ─────────────────────
  templateAdminList: (search = "", sort = "neu") =>
    request<any>(
      `/templates/admin/list?search=${encodeURIComponent(search)}` +
        `&sort=${encodeURIComponent(sort)}`
    ),
  templateAdminPayload: (id: number) =>
    request<any>(`/templates/admin/${id}/payload`),
  templateAdminHistory: (id: number) =>
    request<any>(`/templates/admin/${id}/history`),
  templateAdminBlock: (id: number, blocked: boolean, reason = "") =>
    request<any>(`/templates/admin/${id}/block`, {
      method: "POST",
      body: JSON.stringify({ blocked, reason }),
    }),
  templateAdminDelete: (id: number) =>
    request<any>(`/templates/admin/${id}`, { method: "DELETE" }),

  // ── Teamliste ────────────────────────────────────────────────────
  teamlist: (guildId: string) => request<any>(`/teamlist/${guildId}`),
  teamlistSave: (guildId: string, data: any) =>
    request<any>(`/teamlist/${guildId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  teamlistGroups: (guildId: string, groups: any[]) =>
    request<any>(`/teamlist/${guildId}/groups`, {
      method: "PUT",
      body: JSON.stringify({ groups }),
    }),
  // Die Vorschau kommt vom Bot, nicht aus dem Browser: sonst gäbe es
  // das Format zweimal und beide liefen auseinander.
  teamlistPreview: (guildId: string) =>
    request<any>(`/teamlist/${guildId}/preview`),
  teamlistPublish: (guildId: string, channelId?: string) =>
    request<any>(`/teamlist/${guildId}/publish`, {
      method: "POST",
      body: JSON.stringify(channelId ? { channel_id: channelId } : {}),
    }),
  teamlistRemove: (guildId: string, deleteMessage = true) =>
    request<any>(
      `/teamlist/${guildId}?delete_message=${deleteMessage}`,
      { method: "DELETE" }
    ),

  // ── Musik ────────────────────────────────────────────────────────
  music: (guildId: string) => request<any>(`/music/${guildId}`),
  // Getrennt vom Rest: der Fortschrittsbalken fragt das im Sekundentakt
  // ab, und die Playlists jedes Mal mitzuschicken waere unnoetig.
  musicLive: (guildId: string) => request<any>(`/music/${guildId}/live`),
  musicSave: (guildId: string, data: any) =>
    request<any>(`/music/${guildId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  musicControl: (guildId: string, action: string, value?: number) =>
    request<any>(`/music/${guildId}/control`, {
      method: "POST",
      body: JSON.stringify({ action, value }),
    }),
  musicPlay: (guildId: string, playlistId: number) =>
    request<any>(`/music/${guildId}/play`, {
      method: "POST",
      body: JSON.stringify({ playlist_id: playlistId }),
    }),
  musicPlaylistCreate: (guildId: string, name: string, query?: string) =>
    request<any>(`/music/${guildId}/playlists`, {
      method: "POST",
      body: JSON.stringify({ name, query }),
    }),
  musicPlaylistAddTracks: (guildId: string, playlistId: number, query: string) =>
    request<any>(`/music/${guildId}/playlists/${playlistId}/tracks`, {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  musicPlaylistSave: (guildId: string, playlistId: number, data: any) =>
    request<any>(`/music/${guildId}/playlists/${playlistId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  musicPlaylistDelete: (guildId: string, playlistId: number) =>
    request<any>(`/music/${guildId}/playlists/${playlistId}`, {
      method: "DELETE",
    }),

  // Die Code-Sperre. Freigeschaltet wird ein Server, nicht ein Nutzer.
  speedrunAccess: (guildId: string) =>
    request<any>(`/speedrun/${guildId}/access`),
  speedrunUnlock: (guildId: string, code: string, userId: string) =>
    request<any>(`/speedrun/${guildId}/access`, {
      method: "POST",
      body: JSON.stringify({ code, user_id: userId }),
    }),

  // Verwaltung (nur globale Admins -- der Proxy prüft das).
  speedrunAdminGuilds: () => request<any>(`/speedrun/admin/guilds`),
  speedrunAdminHistory: (guildId = "", limit = 100) =>
    request<any>(
      `/speedrun/admin/history?guild_id=${encodeURIComponent(guildId)}&limit=${limit}`
    ),
  speedrunAdminRevoke: (guildId: string, actorId: string) =>
    request<any>(`/speedrun/admin/${guildId}/revoke`, {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId }),
    }),
  speedrunAdminBan: (guildId: string, actorId: string, reason: string) =>
    request<any>(`/speedrun/admin/${guildId}/ban`, {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId, reason }),
    }),
  speedrunAdminUnban: (guildId: string, actorId: string) =>
    request<any>(`/speedrun/admin/${guildId}/unban`, {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId }),
    }),
  speedrunStatus: (guildId: string, since = 0, sinceMain = 0) =>
    request<any>(
      `/speedrun/${guildId}/status?since=${since}&since_main=${sinceMain}`
    ),
};
