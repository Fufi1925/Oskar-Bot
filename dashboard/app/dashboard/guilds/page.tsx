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
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Deine Server</h1>
          <p className="text-slate-400 mt-2">
            Wähle einen Server um Einstellungen und Module zu verwalten.
          </p>
        </div>
        <LanguageSwitcher />
      </div>

      {error && !userGuilds.length && (
        <div className="bg-blue-500/10 border border-blue-500/20 p-8 rounded-2xl text-center">
          <ShieldCheck className="h-12 w-12 text-blue-500 mx-auto mb-4 opacity-50" />
          <h3 className="text-white font-bold text-lg">Verbindungsfehler</h3>
          <p className="text-slate-400 mt-2">{error}</p>
        </div>
      )}

      {botError && userGuilds.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/25 p-4 rounded-2xl text-sm text-amber-200/90">
          Der Bot ist gerade nicht erreichbar — Mitgliederzahlen und der
          Verbunden-Status können unvollständig sein.
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
        <div className="bg-slate-800/30 border border-slate-800 border-dashed p-16 rounded-3xl text-center">
          <ShieldCheck className="h-16 w-16 text-slate-600 mx-auto mb-6 opacity-50" />
          <h3 className="text-white font-bold text-xl">Keine Admin-Rechte</h3>
          <p className="text-slate-400 mt-2">
            Du hast auf keinem Server Administrator- oder Server-verwalten Rechte.
          </p>
        </div>
      )}

      {!error && userGuilds.length === 0 && (
        <div className="bg-slate-800/30 border border-slate-800 border-dashed p-16 rounded-3xl text-center">
          <Users className="h-16 w-16 text-slate-600 mx-auto mb-6 opacity-50" />
          <h3 className="text-white font-bold text-xl">Keine Server gefunden</h3>
          <p className="text-slate-400 mt-2">
            Du bist auf keinem Discord-Server Mitglied.
          </p>
        </div>
      )}
    </div>
  );
}
