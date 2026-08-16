import React from "react";
import { ShieldCheck, Users } from "lucide-react";
import { api } from "@/lib/api";
import { GuildSummary } from "@/types/api";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { redirect } from "next/navigation";
import { LanguageSwitcher } from "@/components/language-switcher";
import { GuildGrid, type GuildEntry } from "@/components/dashboard/guild-grid";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BOT_INVITE_URL =
  process.env.NEXT_PUBLIC_BOT_INVITE_URL ||
  "https://discord.com/oauth2/authorize?client_id=1530349205372145715&permissions=8&scope=bot%20applications.commands";

export default async function GuildsPage() {
  const session = await getServerSession(authOptions);

  if (!session || !session.accessToken) {
    redirect("/");
  }

  let botGuilds: GuildSummary[] = [];
  let userGuilds: any[] = [];
  let userDiscordError: string | null = null;
  let botError: string | null = null;

  try {
    botGuilds = await api.listGuilds();
  } catch (err: any) {
    botError = err.message || "Bot-Server konnten nicht geladen werden.";
  }

  try {
    // with_counts=true makes Discord include approximate_member_count. Without
    // it the field is simply absent, which is why the cards showed a dash for
    // servers the bot is not on.
    const res = await fetch(
      "https://discord.com/api/users/@me/guilds?with_counts=true",
      {
        headers: { Authorization: `Bearer ${session.accessToken}` },
        next: { revalidate: 300 },
      }
    );

    if (res.ok) {
      userGuilds = await res.json();
    } else {
      userDiscordError = "Deine Discord-Server konnten nicht geladen werden.";
    }
  } catch {
    userDiscordError = "Fehler beim Verbinden mit Discord.";
  }

  const MANAGE_GUILD = BigInt(0x20);
  const ADMINISTRATOR = BigInt(0x8);
  const adminUserGuilds = userGuilds.filter((g: any) => {
    try {
      const perms = BigInt(g.permissions);
      return (
        (perms & ADMINISTRATOR) === ADMINISTRATOR ||
        (perms & MANAGE_GUILD) === MANAGE_GUILD ||
        g.owner === true
      );
    } catch {
      return g.owner === true;
    }
  });

  // The bot knows the exact member count; Discord's OAuth list only ever
  // returns an approximation, and only for guilds it decides to include it for.
  const botGuildMap = new Map(botGuilds.map((g) => [String(g.id), g]));

  const entries: GuildEntry[] = adminUserGuilds.map((g: any) => {
    const info = botGuildMap.get(String(g.id));
    const fromBot = info?.member_count;
    const fromDiscord = g.approximate_member_count;

    return {
      id: String(g.id),
      name: g.name,
      icon: g.icon ?? null,
      owner: g.owner === true,
      hasBot: Boolean(info),
      memberCount:
        typeof fromBot === "number" && fromBot > 0
          ? fromBot
          : typeof fromDiscord === "number"
          ? fromDiscord
          : null,
    };
  });

  const connected = entries.filter((g) => g.hasBot);
  const missing = entries.filter((g) => !g.hasBot);
  const error = botError || userDiscordError;

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-start justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-2xl font-bold text-white">Deine Server</h1>
          <p className="mt-1.5 text-[14px] text-slate-400">
            {connected.length > 0
              ? "Wähle einen Server, um seine Einstellungen zu verwalten."
              : "Füge den Bot auf einem Server hinzu, um loszulegen."}
          </p>
        </div>
        <LanguageSwitcher />
      </div>

      {error && !userGuilds.length && (
        <div className="rounded-2xl border border-slate-800 bg-[#131318] px-6 py-10 text-center">
          <ShieldCheck className="mx-auto mb-3 h-7 w-7 text-slate-700" />
          <h3 className="text-[15px] font-bold text-white">Verbindungsfehler</h3>
          <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">
            {error}
          </p>
        </div>
      )}

      {botError && userGuilds.length > 0 && (
        <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-[13px] leading-relaxed text-amber-200/90">
          Der Bot ist gerade nicht erreichbar. Welche Server verbunden sind,
          lässt sich deshalb nicht sicher sagen — die Mitgliederzahlen unten
          sind Schätzungen von Discord.
        </div>
      )}

      {entries.length > 0 && (
        <GuildGrid
          connected={connected}
          missing={missing}
          inviteUrl={BOT_INVITE_URL}
        />
      )}

      {!error && adminUserGuilds.length === 0 && userGuilds.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-[#131318] px-6 py-12 text-center">
          <ShieldCheck className="mx-auto mb-3 h-7 w-7 text-slate-700" />
          <h3 className="text-[15px] font-bold text-white">
            Kein Server zum Verwalten
          </h3>
          <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">
            Hier erscheinen nur Server, auf denen du „Server verwalten“ oder
            Administrator bist. Auf deinen Servern hast du diese Rechte
            gerade nicht.
          </p>
        </div>
      )}

      {!error && userGuilds.length === 0 && (
        <div className="rounded-2xl border border-slate-800 bg-[#131318] px-6 py-12 text-center">
          <Users className="mx-auto mb-3 h-7 w-7 text-slate-700" />
          <h3 className="text-[15px] font-bold text-white">
            Keine Server gefunden
          </h3>
          <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">
            Discord meldet keinen einzigen Server für dein Konto.
          </p>
        </div>
      )}
    </div>
  );
}
