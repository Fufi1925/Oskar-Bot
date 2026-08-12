"use client";

import React, { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Bot, ChevronRight, Crown, ExternalLink, Plus, Search, Shield, Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface GuildEntry {
  id: string;
  name: string;
  icon: string | null;
  owner: boolean;
  hasBot: boolean;
  /** Real member count from the bot; null when the bot is not in the guild. */
  memberCount: number | null;
}

function iconUrl(id: string, icon: string | null) {
  return icon ? `https://cdn.discordapp.com/icons/${id}/${icon}.png?size=128` : null;
}

function Avatar({
  guild, size = 64, muted = false,
}: { guild: GuildEntry; size?: number; muted?: boolean }) {
  const url = iconUrl(guild.id, guild.icon);
  if (url) {
    return (
      <Image
        src={url}
        alt={guild.name}
        width={size}
        height={size}
        unoptimized
        className={cn(
          "rounded-2xl border-2 border-slate-800 shadow-xl transition-transform group-hover:scale-105",
          muted && "grayscale group-hover:grayscale-0"
        )}
      />
    );
  }
  return (
    <div
      style={{ width: size, height: size }}
      className={cn(
        "rounded-2xl flex items-center justify-center border-2 border-slate-800 font-bold text-2xl shadow-xl",
        muted
          ? "bg-slate-800 text-slate-500"
          : "bg-emerald-500/20 text-emerald-400"
      )}
    >
      {guild.name?.charAt(0)?.toUpperCase()}
    </div>
  );
}

/**
 * Server picker for the user dashboard.
 *
 * Member counts come from the bot (guild.member_count), not from Discord's
 * OAuth guild list — that one omits approximate_member_count unless the
 * request asks for it, which is why every card used to show a dash.
 */
export function GuildGrid({
  connected,
  missing,
  inviteUrl,
}: {
  connected: GuildEntry[];
  missing: GuildEntry[];
  inviteUrl: string;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"members" | "name">("members");

  const filter = (list: GuildEntry[]) => {
    const q = query.trim().toLowerCase();
    const out = q
      ? list.filter(
          (g) => g.name.toLowerCase().includes(q) || g.id.includes(q)
        )
      : [...list];

    out.sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name)
        : (b.memberCount ?? -1) - (a.memberCount ?? -1)
    );
    return out;
  };

  const shownConnected = useMemo(() => filter(connected), [connected, query, sort]);
  const shownMissing = useMemo(() => filter(missing), [missing, query, sort]);

  const totalMembers = connected.reduce((sum, g) => sum + (g.memberCount ?? 0), 0);
  const nothingMatches =
    query.trim() !== "" && shownConnected.length === 0 && shownMissing.length === 0;

  return (
    <div className="space-y-8">
      {/* ── Summary ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Verbunden", value: connected.length, icon: Bot, accent: "emerald" },
          {
            label: "Mitglieder gesamt",
            value: totalMembers.toLocaleString("de-DE"),
            icon: Users,
            accent: "blue",
          },
          {
            label: "Ohne Bot",
            value: missing.length,
            icon: Plus,
            accent: "slate",
          },
          {
            label: "Du bist Owner",
            value: [...connected, ...missing].filter((g) => g.owner).length,
            icon: Crown,
            accent: "amber",
          },
        ].map((s) => (
          <div
            key={s.label}
            className="bg-[#131318] border border-slate-800 rounded-2xl p-5 flex items-center justify-between gap-3 border-glow-card glow-r-2xl"
          >
            <div className="min-w-0">
              <p className="text-2xl font-black text-white tabular-nums truncate">
                {s.value}
              </p>
              <p className="text-[10px] uppercase tracking-widest text-slate-500 font-black mt-1">
                {s.label}
              </p>
            </div>
            <s.icon
              className={cn(
                "h-5 w-5 shrink-0",
                s.accent === "emerald" && "text-emerald-400",
                s.accent === "blue" && "text-blue-400",
                s.accent === "amber" && "text-amber-400",
                s.accent === "slate" && "text-slate-500"
              )}
            />
          </div>
        ))}
      </div>

      {/* ── Search + sort ───────────────────────────────────── */}
      {connected.length + missing.length > 3 && (
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Server suchen…"
              className="w-full bg-[#131318] border border-slate-800 rounded-2xl pl-11 pr-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50 transition-colors"
            />
          </div>
          <div className="flex gap-2">
            {(
              [
                ["members", "Mitglieder"],
                ["name", "Name"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setSort(id)}
                className={cn(
                  "px-4 py-3 rounded-2xl text-xs font-black uppercase tracking-widest border transition-all",
                  sort === id
                    ? "bg-blue-500/15 border-blue-500/40 text-blue-400"
                    : "bg-[#131318] border-slate-800 text-slate-400 hover:text-slate-200"
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {nothingMatches && (
        <p className="text-center text-slate-500 py-12">
          Kein Server passt zu &quot;{query}&quot;.
        </p>
      )}

      {/* ── Connected ───────────────────────────────────────── */}
      {shownConnected.length > 0 && (
        <section>
          <h2 className="text-lg font-bold text-emerald-400 mb-4 flex items-center gap-2">
            <Bot className="h-5 w-5" />
            Bot verbundene Server
            <span className="text-sm font-normal text-slate-500">
              ({shownConnected.length})
            </span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {shownConnected.map((guild) => (
              <div
                key={guild.id}
                className="bg-[#131318] border border-emerald-500/10 rounded-3xl group hover:border-emerald-500/30 hover:bg-[#17375f] transition-all duration-300 overflow-hidden shadow-sm flex flex-col border-glow-card is-clipped"
              >
                <div className="p-6 flex-grow">
                  <div className="flex items-start justify-between mb-6">
                    <div className="relative">
                      <Avatar guild={guild} />
                      <div
                        className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-emerald-500 border-2 border-[#131318]"
                        title="Bot online"
                      />
                    </div>
                    {guild.owner && (
                      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/25 text-[10px] font-black uppercase tracking-widest text-amber-400">
                        <Crown className="h-3 w-3" />
                        Owner
                      </span>
                    )}
                  </div>

                  <h3 className="text-xl font-bold text-white truncate group-hover:text-emerald-400 transition-colors">
                    {guild.name}
                  </h3>

                  <div className="flex items-center gap-3 mt-4 flex-wrap">
                    <div className="flex items-center gap-1.5 bg-slate-800/50 px-3 py-1.5 rounded-xl border border-white/5">
                      <Users className="h-4 w-4 text-blue-400" />
                      <span className="text-sm font-black text-slate-200 tabular-nums">
                        {guild.memberCount !== null
                          ? guild.memberCount.toLocaleString("de-DE")
                          : "—"}
                      </span>
                      <span className="text-[10px] uppercase tracking-widest text-slate-500 font-black">
                        Mitglieder
                      </span>
                    </div>
                  </div>
                </div>

                <div className="px-6 py-4 bg-slate-800/20 border-t border-slate-800/80 group-hover:bg-emerald-500/5 transition-colors">
                  <Button
                    className="w-full justify-between group/btn py-6"
                    variant="secondary"
                    asChild
                  >
                    <Link href={`/dashboard/guild/${guild.id}`}>
                      <span>Server verwalten</span>
                      <ChevronRight className="h-4 w-4 group-hover/btn:translate-x-1 transition-transform" />
                    </Link>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Without the bot ─────────────────────────────────── */}
      {shownMissing.length > 0 && (
        <section>
          <h2 className="text-lg font-bold text-slate-400 mb-4 flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Server ohne Bot
            <span className="text-sm font-normal text-slate-500">
              ({shownMissing.length})
            </span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {shownMissing.map((guild) => (
              <div
                key={guild.id}
                className="bg-[#131318]/50 border border-slate-800/50 rounded-3xl group hover:border-slate-700 transition-all duration-300 overflow-hidden opacity-75 hover:opacity-100 flex flex-col border-glow-card is-clipped"
              >
                <div className="p-6 flex-grow">
                  <div className="flex items-start justify-between mb-6">
                    <div className="relative">
                      <Avatar guild={guild} muted />
                      <div
                        className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-slate-600 border-2 border-[#131318]"
                        title="Bot nicht verbunden"
                      />
                    </div>
                    {guild.owner && (
                      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-[10px] font-black uppercase tracking-widest text-slate-400">
                        <Crown className="h-3 w-3" />
                        Owner
                      </span>
                    )}
                  </div>

                  <h3 className="text-xl font-bold text-slate-300 truncate">
                    {guild.name}
                  </h3>
                  <p className="text-xs text-slate-500 mt-2">
                    Mitgliederzahl sichtbar, sobald der Bot auf dem Server ist.
                  </p>
                </div>

                <div className="px-6 py-4 bg-slate-800/10 border-t border-slate-800/50">
                  <Button
                    className="w-full justify-center gap-2 py-6"
                    variant="outline"
                    asChild
                  >
                    <a href={inviteUrl} target="_blank" rel="noopener noreferrer">
                      <Plus className="h-4 w-4" />
                      Bot einladen
                      <ExternalLink className="h-3 w-3 opacity-50" />
                    </a>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
