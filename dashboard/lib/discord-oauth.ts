export const DISCORD_USER_SCOPES = "identify connections guilds guilds.members.read";

// One-time cutover: cookies from before the expanded consent must sign in again.
export const DASHBOARD_AUTH_VERSION = "discord-expanded-scopes-2026-10-v1";

export function hasDashboardConsent(scope: string): boolean {
  const granted = new Set(scope.split(/\s+/));
  return DISCORD_USER_SCOPES.split(" ").every(value => granted.has(value));
}
