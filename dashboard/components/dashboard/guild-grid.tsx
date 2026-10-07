"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import React, { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Bot, ChevronRight, Crown, ExternalLink, Plus, Search, Users } from "lucide-react";
import { cn } from "@/lib/utils";

export interface GuildEntry {
  id: string;
  name: string;
  icon: string | null;
  owner: boolean;
  hasBot: boolean;
  memberCount: number | null;
  premium?: boolean;
  premiumFrozen?: boolean;
}

function iconUrl(id: string, icon: string | null) {
  if (!icon) return null;
  if (/^https?:\/\//i.test(icon)) return icon;
  return `https://cdn.discordapp.com/icons/${id}/${icon}.png?size=128`;
}

function GuildAvatar({ guild, muted = false }: { guild: GuildEntry; muted?: boolean }) {
  useWebsiteLocale();
  const src = iconUrl(guild.id, guild.icon);
  if (src) {
    return (
      <Image
        src={src}
        alt=""
        width={46}
        height={46}
        unoptimized
        className={cn("h-[46px] w-[46px] rounded-xl object-cover", muted && "grayscale opacity-60")}
      />
    );
  }
  return (
    <div className={cn(
      "grid h-[46px] w-[46px] shrink-0 place-items-center rounded-xl border text-base font-bold",
      muted ? "border-white/[.06] bg-black/15 text-slate-500" : "border-blue-400/15 bg-blue-500/10 text-blue-300",
    )}>
      {guild.name.slice(0, 1).toUpperCase()}
    </div>
  );
}

function memberText(guild: GuildEntry) {
  if (guild.memberCount === null) return "Mitglieder unbekannt";
  return `${guild.hasBot ? "" : "ca. "}${guild.memberCount.toLocaleString(websiteLocale())} Mitglieder`;
}

function ConnectedCard({ guild }: { guild: GuildEntry }) {
  useWebsiteLocale();
  return (
    <Link
      href={`/dashboard/guild/${guild.id}`}
      className="group flex min-w-0 items-center gap-3 rounded-xl border border-white/[.065] bg-[#202126] p-3.5 transition-colors hover:border-blue-400/25 hover:bg-[#23252b]"
    >
      <GuildAvatar guild={guild} />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <p className="truncate text-sm font-semibold text-slate-100">{guild.name}</p>
          {guild.premium && (
            <span className="shrink-0 rounded-md bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-bold text-amber-300">
              Premium
            </span>
          )}
        </div>
        <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1"><Users className="h-3 w-3" />{memberText(guild)}</span>
          {guild.owner && <span className="inline-flex items-center gap-1 text-amber-400/75"><Crown className="h-3 w-3" />Besitzer</span>}
        </div>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-blue-300" />
    </Link>
  );
}

function MissingCard({ guild, inviteUrl }: { guild: GuildEntry; inviteUrl: string }) {
  useWebsiteLocale();
  const href = `${inviteUrl}${inviteUrl.includes("?") ? "&" : "?"}guild_id=${guild.id}&disable_guild_select=true`;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="group flex min-w-0 items-center gap-3 rounded-xl border border-dashed border-white/[.07] bg-black/[.09] p-3.5 transition-colors hover:border-white/[.14] hover:bg-white/[.025]"
    >
      <GuildAvatar guild={guild} muted />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-400 group-hover:text-slate-200">{guild.name}</p>
        <p className="mt-1 text-[11px] text-slate-600">{memberText(guild)}</p>
      </div>
      <span className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-blue-500/10 px-2.5 py-1.5 text-[11px] font-semibold text-blue-300">
        <Plus className="h-3.5 w-3.5" /> Bot hinzufügen <ExternalLink className="h-3 w-3 opacity-60" />
      </span>
    </a>
  );
}

export function GuildGrid({ connected, missing, inviteUrl }: {
  connected: GuildEntry[];
  missing: GuildEntry[];
  inviteUrl: string;
}) {
  useWebsiteLocale();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"name" | "members">("name");

  const filterAndSort = (guilds: GuildEntry[]) => {
    const needle = query.trim().toLowerCase();
    return guilds
      .filter((guild) => !needle || guild.name.toLowerCase().includes(needle) || guild.id.includes(needle))
      .sort((a, b) => sort === "name"
        ? a.name.localeCompare(b.name, "de")
        : (b.memberCount ?? -1) - (a.memberCount ?? -1));
  };

  const shownConnected = useMemo(() => filterAndSort([...connected]), [connected, query, sort]);
  const shownMissing = useMemo(() => filterAndSort([...missing]), [missing, query, sort]);
  const total = connected.length + missing.length;

  return (
    <div className="space-y-7">
      <div className="flex flex-col gap-3 rounded-xl border border-white/[.06] bg-[#202126] p-3 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Server suchen"
            aria-label="Server suchen"
            className="h-10 w-full rounded-lg border border-white/[.065] bg-[#191a1f] pl-9 pr-3 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-blue-400/30"
          />
        </div>
        <div className="flex items-center justify-between gap-3 sm:justify-end">
          <span className="text-xs text-slate-500">{total} Server</span>
          <div className="flex rounded-lg bg-[#191a1f] p-1">
            <button onClick={() => setSort("name")} className={cn("rounded-md px-2.5 py-1.5 text-[11px] font-medium", sort === "name" ? "bg-white/[.07] text-white" : "text-slate-500")}>Name</button>
            <button onClick={() => setSort("members")} className={cn("rounded-md px-2.5 py-1.5 text-[11px] font-medium", sort === "members" ? "bg-white/[.07] text-white" : "text-slate-500")}>Mitglieder</button>
          </div>
        </div>
      </div>

      {shownConnected.length > 0 && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <Bot className="h-4 w-4 text-emerald-400" />
            <h2 className="text-sm font-semibold text-slate-200">Verbundene Server</h2>
            <span className="text-xs text-slate-600">{shownConnected.length}</span>
          </div>
          <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
            {shownConnected.map((guild) => <ConnectedCard key={guild.id} guild={guild} />)}
          </div>
        </section>
      )}

      {shownMissing.length > 0 && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <Plus className="h-4 w-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-300">Bot noch nicht hinzugefügt</h2>
            <span className="text-xs text-slate-600">{shownMissing.length}</span>
          </div>
          <div className="grid gap-2.5 lg:grid-cols-2">
            {shownMissing.map((guild) => <MissingCard key={guild.id} guild={guild} inviteUrl={inviteUrl} />)}
          </div>
        </section>
      )}

      {shownConnected.length === 0 && shownMissing.length === 0 && (
        <div className="rounded-xl border border-white/[.06] bg-[#202126] px-5 py-12 text-center">
          <Search className="mx-auto h-5 w-5 text-slate-600" />
          <p className="mt-3 text-sm text-slate-400">Kein passender Server gefunden.</p>
        </div>
      )}
    </div>
  );
}
