import { NextRequest, NextResponse } from "next/server";
import { createVerifyState, websiteOrigin } from "@/lib/verification-oauth";

export const dynamic = "force-dynamic";

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
  // Deliberately minimal: identify who clicked and compare their guild ids.
  authorize.searchParams.set("scope", "identify guilds");
  authorize.searchParams.set("state", createVerifyState(guildId));
  authorize.searchParams.set("prompt", "consent");
  return NextResponse.redirect(authorize);
}
