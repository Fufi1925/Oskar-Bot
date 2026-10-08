import { NextRequest, NextResponse } from "next/server";
import { createVerifyState, websiteOrigin } from "@/lib/verification-oauth";
import { configuredOAuthScopes } from "@/lib/dashboard-oauth-policy";

export const dynamic = "force-dynamic";

const API_BASE =
  process.env.API_BASE_URL ||
  `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

export async function GET(request: NextRequest) {
  const language = request.nextUrl.searchParams.get("lang") || request.cookies.get("website-language")?.value;
  const selectedLanguage = language === "de" ? "de" : "en";
  const guildId = request.nextUrl.searchParams.get("guild") || "";
  if (!/^\d{17,20}$/.test(guildId)) {
    return NextResponse.json(
      { detail: selectedLanguage === "de" ? "Ungültige Server-ID." : "Invalid server ID." },
      { status: 400 },
    );
  }
  const clientId = process.env.DISCORD_CLIENT_ID;
  if (!clientId) {
    return NextResponse.json(
      { detail: selectedLanguage === "de" ? "Discord OAuth ist nicht konfiguriert." : "Discord OAuth is not configured." },
      { status: 503 },
    );
  }

  const authorize = new URL("https://discord.com/oauth2/authorize");
  authorize.searchParams.set("client_id", clientId);
  authorize.searchParams.set(
    "redirect_uri",
    `${websiteOrigin()}/api/verify/callback`,
  );
  authorize.searchParams.set("response_type", "code");
  // guilds.join is optional and only appears after the owner confirmed User
  // Pull on the target server. Existing verifications are never upgraded.
  let scopes: string;
  try { scopes = await configuredOAuthScopes(); }
  catch {
    return NextResponse.json({ detail: selectedLanguage === "de" ? "Die OAuth-Einstellungen sind momentan nicht erreichbar. Bitte versuche es gleich erneut." : "OAuth settings are currently unavailable. Please try again shortly." }, { status: 503 });
  }
  try {
    const settingsResponse = await fetch(`${API_BASE}/verify/${guildId}`, {
      headers: {
        Authorization: `Bearer ${process.env.DASHBOARD_API_KEY || ""}`,
      },
      cache: "no-store",
    });
    if (settingsResponse.ok) {
      const settings = await settingsResponse.json();
      // Pull and its powerful guilds.join scope are available only while
      // the source server has active Premium. The bot returns the effective
      // enabled state, but checking both fields keeps this boundary explicit.
      if (settings.pull_premium && settings.user_pull_enabled) {
        scopes += " guilds.join";
      }
    }
  } catch {
    // Keep ordinary verification available if the optional lookup fails.
  }
  authorize.searchParams.set("scope", scopes);
  authorize.searchParams.set("state", createVerifyState(guildId, selectedLanguage, scopes));
  authorize.searchParams.set("prompt", "consent");
  return NextResponse.redirect(authorize);
}
