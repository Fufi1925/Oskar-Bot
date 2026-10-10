"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import React, { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  ChevronRight,
  Crown,
  ExternalLink,
  Plus,
  Search,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { compareGuildMembers } from "@/lib/guild-sorting";

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

function GuildAvatar({
  guild,
  muted = false,
}: {
  guild: GuildEntry;
  muted?: boolean;
}) {
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
        className={cn(
          "h-[46px] w-[46px] rounded-xl object-cover",
          muted && "grayscale opacity-60",
        )}
      />
    );
  }
  return (
    <div
      className={cn(
        "grid h-[46px] w-[46px] shrink-0 place-items-center rounded-xl border text-base font-bold",
        muted
          ? "border-white/[.06] bg-black/15 text-slate-500"
          : "border-white/10 bg-white/[.04] text-slate-200",
      )}
    >
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
      className="cloudtix-workspace-server-card"
      aria-label={`${guild.name} verwalten`}
    >
      <div className="cloudtix-workspace-server-card-top">
        <GuildAvatar guild={guild} />
        <span>
          <i />
          Verbunden
        </span>
      </div>
      <h3 title={guild.name}>{guild.name}</h3>
      <p>{guild.owner ? "Deine Community" : "Für dich freigegeben"}</p>
      <div className="cloudtix-workspace-server-card-details">
        <span>
          <Users size={13} />
          {memberText(guild)}
        </span>
        {(guild.premium || guild.premiumFrozen) && (
          <span>
            <Crown size={12} />
            {guild.premiumFrozen ? "Premium pausiert" : "Premium"}
          </span>
        )}
      </div>
      <div className="cloudtix-workspace-server-card-footer">
        <span>Workspace öffnen</span>
        <ChevronRight size={15} />
      </div>
    </Link>
  );
}

function MissingCard({
  guild,
  inviteUrl,
}: {
  guild: GuildEntry;
  inviteUrl: string;
}) {
  useWebsiteLocale();
  const href = `${inviteUrl}${inviteUrl.includes("?") ? "&" : "?"}guild_id=${guild.id}&disable_guild_select=true`;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="cloudtix-workspace-server-card is-missing"
      aria-label={`CloudTIX zu ${guild.name} hinzufügen`}
    >
      <div className="cloudtix-workspace-server-card-top">
        <GuildAvatar guild={guild} muted />
        <span>Noch ohne CloudTIX</span>
      </div>
      <h3 title={guild.name}>{guild.name}</h3>
      <p>Bereit für deine Einrichtung</p>
      <div className="cloudtix-workspace-server-card-details">
        <span>
          <Users size={13} />
          {memberText(guild)}
        </span>
      </div>
      <div className="cloudtix-workspace-server-card-footer">
        <span>
          <Plus size={13} />
          CloudTIX hinzufügen
        </span>
        <ExternalLink size={14} />
      </div>
    </a>
  );
}

export function GuildGrid({
  connected,
  missing,
  inviteUrl,
}: {
  connected: GuildEntry[];
  missing: GuildEntry[];
  inviteUrl: string;
}) {
  useWebsiteLocale();
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"all" | "connected" | "missing">("all");
  const [sort, setSort] = useState<"name" | "members">("members");

  const shownGuilds = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const guilds =
      view === "connected"
        ? connected
        : view === "missing"
          ? missing
          : [...connected, ...missing];
    return guilds
      .filter(
        (guild) =>
          !needle ||
          guild.name.toLowerCase().includes(needle) ||
          guild.id.includes(needle),
      )
      .sort(
        sort === "members"
          ? compareGuildMembers
          : (a, b) =>
              a.name.localeCompare(b.name, "de") || a.id.localeCompare(b.id),
      );
  }, [connected, missing, query, view, sort]);
  const total = connected.length + missing.length;

  return (
    <div className="space-y-7">
      <div className="cloudtix-workspace-server-filters">
        <div className="cloudtix-workspace-segmented">
          {(
            [
              ["all", "Alle", total],
              ["connected", "Verbunden", connected.length],
              ["missing", "Ohne CloudTIX", missing.length],
            ] as const
          ).map(([id, title, count]) => (
            <button
              key={id}
              type="button"
              aria-pressed={view === id}
              onClick={() => setView(id)}
            >
              {title}
              <small>{count}</small>
            </button>
          ))}
        </div>
        <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Server suchen"
              aria-label="Server suchen"
              className="h-10 w-full rounded-lg border border-white/[.065] cloudtix-workspace-field bg-[#191a1f] pl-9 pr-3 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-blue-400/30"
            />
          </div>
          <div className="flex items-center justify-between gap-3 sm:justify-end">
            <span className="text-xs text-slate-500">{total} Server</span>
            <div className="flex rounded-lg cloudtix-workspace-field bg-[#191a1f] p-1">
              <button
                type="button"
                aria-pressed={sort === "name"}
                onClick={() => setSort("name")}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-[11px] font-medium",
                  sort === "name"
                    ? "bg-white/[.07] text-white"
                    : "text-slate-500",
                )}
              >
                Name
              </button>
              <button
                type="button"
                aria-pressed={sort === "members"}
                title="Meiste Mitglieder zuerst"
                onClick={() => setSort("members")}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-[11px] font-medium",
                  sort === "members"
                    ? "bg-white/[.07] text-white"
                    : "text-slate-500",
                )}
              >
                Mitglieder
              </button>
            </div>
          </div>
        </div>
      </div>

      {shownGuilds.length > 0 && (
        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-slate-200">
              {view === "connected"
                ? "Verbundene Server"
                : view === "missing"
                  ? "Noch ohne CloudTIX"
                  : "Alle deine Server"}{" "}
              <span className="ml-2 text-xs text-slate-500">
                {shownGuilds.length}
              </span>
            </h2>
            <p className="text-xs text-slate-500">
              {sort === "members"
                ? "Meiste Mitglieder zuerst · unbekannte Zahlen zuletzt"
                : "Alphabetisch nach Servernamen"}
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {shownGuilds.map((guild) =>
              guild.hasBot ? (
                <ConnectedCard key={guild.id} guild={guild} />
              ) : (
                <MissingCard
                  key={guild.id}
                  guild={guild}
                  inviteUrl={inviteUrl}
                />
              ),
            )}
          </div>
        </section>
      )}
      {shownGuilds.length === 0 && (
        <div className="rounded-xl border border-white/[.06] cloudtix-workspace-card bg-[#202126] px-5 py-12 text-center">
          <Search className="mx-auto h-5 w-5 text-slate-600" />
          <p className="mt-3 text-sm text-slate-400">
            Kein passender Server gefunden.
          </p>
        </div>
      )}
    </div>
  );
}
