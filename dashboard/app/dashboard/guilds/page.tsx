import React from "react";
import Image from "next/image";
import Link from "next/link";
import { Users, ShieldCheck, ChevronRight, Hash, Bot, Plus, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { GuildSummary } from "@/types/api";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { redirect } from "next/navigation";
import { LanguageSwitcher } from "@/components/language-switcher";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BOT_INVITE_URL = process.env.NEXT_PUBLIC_BOT_INVITE_URL || "https://discord.com/oauth2/authorize?client_id=1530349205372145715&permissions=8&scope=bot%20applications.commands";

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
    const res = await fetch("https://discord.com/api/users/@me/guilds", {
      headers: { Authorization: `Bearer ${session.accessToken}` },
      next: { revalidate: 300 },
    });
    
    if (res.ok) {
      userGuilds = await res.json();
    } else {
      userDiscordError = "Deine Discord-Server konnten nicht geladen werden.";
    }
  } catch (err) {
    userDiscordError = "Fehler beim Verbinden mit Discord.";
  }

  const MANAGE_GUILD = BigInt(0x20);
  const ADMINISTRATOR = BigInt(0x8);
  const adminUserGuilds = userGuilds.filter((g: any) => {
    try {
      const perms = BigInt(g.permissions);
      return (perms & ADMINISTRATOR) === ADMINISTRATOR || 
             (perms & MANAGE_GUILD) === MANAGE_GUILD || 
             g.owner === true;
    } catch { return g.owner === true; }
  });

  const botGuildIds = new Set(botGuilds.map(g => String(g.id)));
  const botGuildMap = new Map(botGuilds.map(g => [String(g.id), g]));

  const guildsWithStatus = adminUserGuilds.map((g: any) => ({
    ...g,
    hasBot: botGuildIds.has(String(g.id)),
    botInfo: botGuildMap.get(String(g.id)),
  }));

  const botConnectedGuilds = guildsWithStatus.filter((g: any) => g.hasBot);
  const botMissingGuilds = guildsWithStatus.filter((g: any) => !g.hasBot);
  const error = botError || userDiscordError;

  const iconUrl = (id: string, icon: string | null) => 
    icon ? `https://cdn.discordapp.com/icons/${id}/${icon}.png?size=128` : null;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Deine Server</h1>
          <p className="text-slate-400 mt-2">
            Wähle einen Server um Einstellungen und Module zu verwalten.
          </p>
        </div>
        <div className="flex gap-3 text-sm font-medium">
          <LanguageSwitcher />
          <div className="px-4 py-2 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400">
            <Bot className="inline h-4 w-4 mr-1.5" />
            Verbunden: <span className="font-bold text-white">{botConnectedGuilds.length}</span>
          </div>
          <div className="px-4 py-2 bg-slate-800 rounded-xl border border-slate-700 text-slate-300">
            Admin-Rechte: <span className="font-bold text-white">{adminUserGuilds.length}</span>
          </div>
        </div>
      </div>

      {error && !userGuilds.length && (
        <div className="bg-blue-500/10 border border-blue-500/20 p-8 rounded-2xl text-center">
          <ShieldCheck className="h-12 w-12 text-blue-500 mx-auto mb-4 opacity-50" />
          <h3 className="text-white font-bold text-lg">Verbindungsfehler</h3>
          <p className="text-slate-400 mt-2">{error}</p>
        </div>
      )}

      {/* Bot Connected Servers */}
      {botConnectedGuilds.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-emerald-400 mb-4 flex items-center gap-2">
            <Bot className="h-5 w-5" />
            Bot verbundene Server
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {botConnectedGuilds.map((guild: any) => (
              <div 
                key={guild.id}
                className="bg-[#10233f] border border-emerald-500/10 rounded-3xl group hover:border-emerald-500/30 hover:bg-[#17375f] transition-all duration-300 overflow-hidden shadow-sm"
              >
                <div className="p-6">
                  <div className="flex items-start justify-between mb-6">
                    <div className="relative">
                      {guild.icon ? (
                        <Image
                          src={iconUrl(guild.id, guild.icon)!}
                          alt={guild.name}
                          width={64} height={64}
                          className="rounded-2xl border-2 border-slate-800 shadow-xl group-hover:scale-105 transition-transform"
                          unoptimized
                        />
                      ) : (
                        <div className="h-16 w-16 bg-emerald-500/20 rounded-2xl flex items-center justify-center border-2 border-slate-800 text-emerald-400 font-bold text-2xl shadow-xl">
                          {guild.name?.charAt(0)}
                        </div>
                      )}
                      <div className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-emerald-500 border-2 border-[#10233f]" title="Bot Online" />
                    </div>
                    <div className="flex flex-col items-end text-right">
                      <span className="text-[10px] uppercase font-bold text-slate-500 tracking-widest mb-1">GUILD ID</span>
                      <span className="text-xs font-mono text-slate-400 bg-black/20 px-2 py-1 rounded-lg border border-white/5 truncate max-w-[120px]">
                        {guild.id}
                      </span>
                    </div>
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white truncate group-hover:text-emerald-400 transition-colors">
                      {guild.name}
                    </h3>
                    <div className="flex items-center gap-4 mt-4 text-slate-400">
                      <div className="flex items-center gap-1.5 bg-slate-800/50 px-3 py-1.5 rounded-xl border border-white/5">
                        <Users className="h-4 w-4 text-slate-500" />
                        <span className="text-sm font-semibold text-slate-300">{guild.approximate_member_count?.toLocaleString() || guild.member_count?.toLocaleString() || "—"}</span>
                      </div>
                      <div className="flex items-center gap-1.5 bg-emerald-500/10 px-3 py-1.5 rounded-xl border border-emerald-500/20">
                        <span className="text-sm font-semibold text-emerald-400">Verbunden</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="px-6 py-4 bg-slate-800/20 border-t border-slate-800/80 group-hover:bg-emerald-500/5 transition-colors">
                  <Button className="w-full justify-between group/btn py-6" variant="secondary" asChild>
                    <Link href={`/dashboard/guild/${guild.id}`}>
                      <span>Server verwalten</span>
                      <ChevronRight className="h-4 w-4 group-hover/btn:translate-x-1 transition-transform" />
                    </Link>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Servers without Bot */}
      {botMissingGuilds.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-slate-400 mb-4 flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Server ohne Bot
            <span className="text-sm font-normal text-slate-500">({botMissingGuilds.length} Server)</span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {botMissingGuilds.map((guild: any) => (
              <div 
                key={guild.id}
                className="bg-[#10233f]/50 border border-slate-800/50 rounded-3xl group hover:border-slate-700 transition-all duration-300 overflow-hidden opacity-75 hover:opacity-100"
              >
                <div className="p-6">
                  <div className="flex items-start justify-between mb-6">
                    <div className="relative">
                      {guild.icon ? (
                        <Image
                          src={iconUrl(guild.id, guild.icon)!}
                          alt={guild.name}
                          width={64} height={64}
                          className="rounded-2xl border-2 border-slate-800 shadow-xl group-hover:scale-105 transition-transform grayscale group-hover:grayscale-0"
                          unoptimized
                        />
                      ) : (
                        <div className="h-16 w-16 bg-slate-800 rounded-2xl flex items-center justify-center border-2 border-slate-700 text-slate-500 font-bold text-2xl">
                          {guild.name?.charAt(0)}
                        </div>
                      )}
                      <div className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-slate-600 border-2 border-[#10233f]" title="Bot nicht verbunden" />
                    </div>
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-slate-300 truncate">{guild.name}</h3>
                    <div className="flex items-center gap-4 mt-4 text-slate-400">
                      <div className="flex items-center gap-1.5 bg-slate-800/50 px-3 py-1.5 rounded-xl border border-white/5">
                        <Users className="h-4 w-4 text-slate-500" />
                        <span className="text-sm font-semibold text-slate-300">{guild.approximate_member_count?.toLocaleString() || "—"}</span>
                      </div>
                      <div className="flex items-center gap-1.5 bg-blue-500/10 px-3 py-1.5 rounded-xl border border-blue-500/20">
                        <span className="text-sm font-semibold text-blue-400">Bot fehlt</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="px-6 py-4 bg-slate-800/10 border-t border-slate-800/50">
                  <Button className="w-full justify-center gap-2 py-6" variant="outline" asChild>
                    <a href={BOT_INVITE_URL} target="_blank" rel="noopener noreferrer">
                      <Plus className="h-4 w-4" />
                      Bot einladen
                      <ExternalLink className="h-3 w-3 opacity-50" />
                    </a>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!error && adminUserGuilds.length === 0 && userGuilds.length > 0 && (
        <div className="bg-slate-800/30 border border-slate-800 border-dashed p-16 rounded-3xl text-center">
          <ShieldCheck className="h-16 w-16 text-slate-600 mx-auto mb-6 opacity-50" />
          <h3 className="text-white font-bold text-xl">Keine Admin-Rechte</h3>
          <p className="text-slate-400 mt-2">Du hast auf keinem Server Administrator- oder Server-verwalten Rechte.</p>
        </div>
      )}

      {!error && userGuilds.length === 0 && (
        <div className="bg-slate-800/30 border border-slate-800 border-dashed p-16 rounded-3xl text-center">
          <Users className="h-16 w-16 text-slate-600 mx-auto mb-6 opacity-50" />
          <h3 className="text-white font-bold text-xl">Keine Server gefunden</h3>
          <p className="text-slate-400 mt-2">Du bist auf keinem Discord-Server Mitglied.</p>
        </div>
      )}
    </div>
  );
}
