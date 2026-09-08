import { NextRequest, NextResponse } from "next/server";
import { createVerifyState, websiteOrigin } from "@/lib/verification-oauth";

export const dynamic = "force-dynamic";

const API_BASE =
  process.env.API_BASE_URL ||
  `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

export async function GET(request: NextRequest) {
  const guildId = request.nextUrl.searchParams.get("guild") || "";
  if (!/^\d{17,20}$/.test(guildId)) {
    return NextResponse.json(
      { detail: "Ungültige Server-ID." },
      { status: 400 },
    );
  }
  const clientId = process.env.DISCORD_CLIENT_ID;
  if (!clientId) {
    return NextResponse.json(
      { detail: "Discord OAuth ist nicht konfiguriert." },
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
  let scopes = "identify guilds";
  try {
    const settingsResponse = await fetch(`${API_BASE}/verify/${guildId}`, {
      headers: {
        Authorization: `Bearer ${process.env.DASHBOARD_API_KEY || ""}`,
      },
      cache: "no-store",
    });
    if (settingsResponse.ok) {
      const settings = await settingsResponse.json();
      if (settings.user_pull_enabled) {
        scopes += " guilds.join";
      }
    }
  } catch {
    // Keep ordinary verification available if the optional lookup fails.
  }
  authorize.searchParams.set("scope", scopes);
  authorize.searchParams.set("state", createVerifyState(guildId));
  authorize.searchParams.set("prompt", "consent");
  return NextResponse.redirect(authorize);
}
