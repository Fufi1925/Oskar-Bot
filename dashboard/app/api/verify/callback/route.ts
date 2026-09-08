import { NextRequest, NextResponse } from "next/server";
import {
  createVerifyResult,
  readVerifyState,
  websiteOrigin,
  type VerifyResult,
} from "@/lib/verification-oauth";

export const dynamic = "force-dynamic";

const DISCORD = "https://discord.com/api/v10";
const API_BASE =
  process.env.API_BASE_URL ||
  `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

function resultRedirect(result: Omit<VerifyResult, "exp">) {
  const token = createVerifyResult(result);
  const response = NextResponse.redirect(
    `${websiteOrigin()}/verify/${encodeURIComponent(result.guild_id)}?result=${encodeURIComponent(token)}`,
  );
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

export async function GET(request: NextRequest) {
  const state = readVerifyState(
    request.nextUrl.searchParams.get("state") || "",
  );
  if (!state) {
    return NextResponse.json(
      { detail: "Dieser Verifizierungslink ist ungültig oder abgelaufen." },
      { status: 400 },
    );
  }
  if (request.nextUrl.searchParams.get("error")) {
    return resultRedirect({
      guild_id: state.guildId,
      status: "error",
      reason: "oauth_cancelled",
    });
  }

  const code = request.nextUrl.searchParams.get("code") || "";
  const clientId = process.env.DISCORD_CLIENT_ID || "";
  const clientSecret = process.env.DISCORD_CLIENT_SECRET || "";
  if (!code || !clientId || !clientSecret || !process.env.DASHBOARD_API_KEY) {
    return resultRedirect({
      guild_id: state.guildId,
      status: "error",
      reason: "oauth_unavailable",
    });
  }

  let accessToken = "";
  try {
    const tokenResponse = await fetch(`${DISCORD}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        grant_type: "authorization_code",
        code,
        redirect_uri: `${websiteOrigin()}/api/verify/callback`,
      }),
      cache: "no-store",
    });
    if (!tokenResponse.ok)
      throw new Error(`Discord token exchange failed: ${tokenResponse.status}`);
    const token = await tokenResponse.json();
    accessToken = String(token.access_token || "");
    if (!accessToken) throw new Error("Discord returned no access token");

    const headers = { Authorization: `Bearer ${accessToken}` };
    const [userResponse, guildsResponse] = await Promise.all([
      fetch(`${DISCORD}/users/@me`, { headers, cache: "no-store" }),
      fetch(`${DISCORD}/users/@me/guilds?limit=200`, {
        headers,
        cache: "no-store",
      }),
    ]);
    if (!userResponse.ok || !guildsResponse.ok)
      throw new Error("Discord identity request failed");
    const user = await userResponse.json();
    const guilds = await guildsResponse.json();

    const completion = await fetch(`${API_BASE}/verify/oauth/complete`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${process.env.DASHBOARD_API_KEY}`,
      },
      body: JSON.stringify({
        guild_id: state.guildId,
        user: { id: user.id },
        guilds: Array.isArray(guilds)
          ? guilds.map((guild: any) => ({
              id: String(guild.id),
              name: String(guild.name || guild.id),
            }))
          : [],
      }),
      cache: "no-store",
    });
    if (!completion.ok)
      throw new Error(`Bot completion failed: ${completion.status}`);
    const outcome = await completion.json();
    return resultRedirect({
      guild_id: state.guildId,
      guild_name: outcome.guild_name,
      guild_icon: outcome.guild_icon,
      status: outcome.status,
      reason: outcome.reason,
      role_name: outcome.role_name,
      blocked: outcome.blocked,
    });
  } catch (error) {
    console.error("OAuth verification failed", error);
    return resultRedirect({
      guild_id: state.guildId,
      status: "error",
      reason: "verification_failed",
    });
  } finally {
    // Verification needs the token for seconds, not months. Revoke it as soon
    // as identity and memberships have been checked; nothing is persisted.
    if (accessToken) {
      await fetch(`${DISCORD}/oauth2/token/revoke`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          client_id: clientId,
          client_secret: clientSecret,
          token: accessToken,
          token_type_hint: "access_token",
        }),
      }).catch(() => undefined);
    }
  }
}
