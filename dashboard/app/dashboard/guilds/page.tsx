import { loginUrl } from "@/lib/auth-navigation";
import React from "react";
import { ArrowRight, Bot, Plus, Server, ShieldCheck, Users } from "lucide-react";
import { api } from "@/lib/api";
import { GuildSummary } from "@/types/api";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { redirect } from "next/navigation";
import { GuildGrid, type GuildEntry } from "@/components/dashboard/guild-grid";
import { fetchDelegatedGuilds, type DelegatedGuild } from "@/lib/guild-auth";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BOT_INVITE_URL =
  process.env.NEXT_PUBLIC_BOT_INVITE_URL ||
  "https://discord.com/oauth2/authorize?client_id=1530349205372145715&permissions=8&scope=bot%20applications.commands";

export default async function GuildsPage() {
  const session = await getServerSession(authOptions);

  if (!session || !session.accessToken) {
    redirect(loginUrl("/dashboard/guilds"));
  }

  let botGuilds: GuildSummary[] = [];
  let userGuilds: any[] = [];
  let delegatedGuilds: DelegatedGuild[] = [];
  let userDiscordError: string | null = null;
  let botError: string | null = null;

  try {
    botGuilds = await api.listGuilds();
    if (session.user?.id) {
      delegatedGuilds = await fetchDelegatedGuilds(session.user.id);
    }
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

  // Role/user grants are additive. Do not duplicate a server somebody already
  // manages through Discord; append only the delegated cards.
  const known = new Set(entries.map((guild) => guild.id));
  for (const guild of delegatedGuilds) {
    if (known.has(guild.id)) continue;
    entries.push({
      id: guild.id,
      name: guild.name,
      icon: guild.icon,
      owner: guild.owner,
      hasBot: true,
      memberCount: guild.member_count,
    });
    known.add(guild.id);
  }

  await Promise.all(entries.filter(entry => entry.hasBot).map(async entry => {
    try {
      const premiumState = await api.getServerPremium(entry.id);
      entry.premium = Boolean(premiumState?.runtime);
      entry.premiumFrozen = Boolean(premiumState?.frozen);
    } catch {
      entry.premium = false;
    }
  }));

  const connected = entries.filter((g) => g.hasBot);
  const missing = entries.filter((g) => !g.hasBot);
  const error = botError || userDiscordError;

  return (
    <div className="space-y-6">
      <header className="cloudtix-workspace-page-heading"><div><p className="cloudtix-workspace-eyebrow">DEINE COMMUNITIES</p><h1>Deine Server.</h1><p>Wähle deine Community. Alles, was du für sie einrichtest, beginnt hier.</p></div><a href={BOT_INVITE_URL} target="_blank" rel="noopener noreferrer" className="cloudtix-workspace-action"><Plus size={15} />CloudTIX hinzufügen</a></header>
      <div className="cloudtix-workspace-stat-grid cloudtix-workspace-server-totals">{[
        { label: "Für dich verfügbar", value: entries.length, icon: Server, note: "Discord-Rechte und Dashboard-Freigaben" },
        { label: "Mit CloudTIX", value: connected.length, icon: Bot, note: "Bereit für deine Serververwaltung" },
        { label: "Noch ohne CloudTIX", value: missing.length, icon: Plus, note: "Füge den Bot hinzu und starte direkt" },
      ].map(metric => <div key={metric.label} className="cloudtix-workspace-stat"><metric.icon size={18} /><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.note}</small></div>)}</div>

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

      {!error && entries.length === 0 && userGuilds.length > 0 && (
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

      {!error && entries.length === 0 && userGuilds.length === 0 && (
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
