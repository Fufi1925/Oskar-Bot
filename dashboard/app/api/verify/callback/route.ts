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
  let refreshToken = "";
  let guildsJoinAuthorized = false;
  let failureReason = "verification_failed";
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
    if (!tokenResponse.ok) {
      failureReason = "oauth_token_failed";
      throw new Error(`Discord token exchange failed: ${tokenResponse.status}`);
    }
    const token = await tokenResponse.json();
    accessToken = String(token.access_token || "");
    refreshToken = String(token.refresh_token || "");
    guildsJoinAuthorized = String(token.scope || "")
      .split(/[\s,]+/)
      .includes("guilds.join");
    if (!accessToken) throw new Error("Discord returned no access token");

    const headers = { Authorization: `Bearer ${accessToken}` };
    const [userResponse, guildsResponse] = await Promise.all([
      fetch(`${DISCORD}/users/@me`, { headers, cache: "no-store" }),
      fetch(`${DISCORD}/users/@me/guilds?limit=200`, {
        headers,
        cache: "no-store",
      }),
    ]);
    if (!userResponse.ok || !guildsResponse.ok) {
      failureReason = "oauth_identity_failed";
      throw new Error("Discord identity request failed");
    }
    const user = await userResponse.json();
    const guilds = await guildsResponse.json();

    const completionBody = JSON.stringify({
      guild_id: state.guildId,
      user: { id: user.id },
      // Only an authenticated encrypted refresh token is retained when the
      // user expressly grants guilds.join. The access token is never stored.
      refresh_token: refreshToken,
      guilds_join_authorized: guildsJoinAuthorized,
      guilds: Array.isArray(guilds)
        ? guilds.map((guild: any) => ({
            id: String(guild.id),
            name: String(guild.name || guild.id),
          }))
        : [],
    });
    const complete = () =>
      fetch(`${API_BASE}/verify/oauth/complete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${process.env.DASHBOARD_API_KEY}`,
        },
        body: completionBody,
        cache: "no-store",
      });
    let completion = await complete();
    // A Railway deploy can briefly restart the bot between Discord's callback
    // and role assignment. Retry one transient server error, never an OAuth or
    // validation error, and keep the whole callback bounded.
    if (completion.status >= 500) {
      await new Promise((resolve) => setTimeout(resolve, 300));
      completion = await complete();
    }
    if (!completion.ok) {
      failureReason = `bot_completion_${completion.status}`;
      throw new Error(`Bot completion failed: ${completion.status}`);
    }
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
      reason: failureReason,
    });
  } finally {
    // Do not call Discord's token-revocation endpoint here. Verification and
    // dashboard login use the same Discord application; revoking this grant
    // can invalidate the user's existing dashboard authorization and leave the
    // UI looking signed out. The access token is never persisted and expires
    // on Discord's normal short lifetime.
    accessToken = "";
  }
}
