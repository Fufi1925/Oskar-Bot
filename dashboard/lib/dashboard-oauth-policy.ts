import { DISCORD_USER_SCOPES } from "@/lib/discord-oauth";

/** Trusted server read. Never invent a scope selection when the policy is unavailable. */
export async function configuredOAuthScopes(): Promise<string> {
  const key = process.env.DASHBOARD_API_KEY;
  if (!key) throw new Error("OAuth policy unavailable");
  const base = process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;
  const response = await fetch(`${base}/dashboard-settings/oauth-policy`, {
    headers: { Authorization: `Bearer ${key}` }, cache: "no-store", signal: AbortSignal.timeout(3000),
  });
  if (!response.ok) throw new Error("OAuth policy unavailable");
  const data = await response.json();
  const allowed = DISCORD_USER_SCOPES.split(" ");
  if (!Array.isArray(data.scopes) || data.scopes.some((scope: unknown) => typeof scope !== "string" || !allowed.includes(scope)) ||
    !data.scopes.includes("identify") || !data.scopes.includes("guilds")) throw new Error("Invalid OAuth policy");
  return allowed.filter(scope => data.scopes.includes(scope)).join(" ");
}
