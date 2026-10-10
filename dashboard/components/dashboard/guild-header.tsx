"use client";

/**
 * The header above the guild tabs.
 *
 * What this replaces, and why each piece had to go:
 *
 *   * &bdquo;Aktualisieren&ldquo; was a <Link> to the page you were
 *     already on. The layout is `revalidate = 0`, so there was nothing
 *     stale to refresh -- Next saw the same route and did nothing
 *     visible. A button that looks like it does something and does not
 *     is worse than no button.
 *   * &bdquo;Server Settings&ldquo; was a second way into the
 *     Einstellungen tab, which is already in the tab bar right below it.
 *   * The green dot was hardcoded. It pulsed &bdquo;Active&ldquo; whether
 *     the bot was connected, lagging or completely offline, which is
 *     exactly the moment somebody looks at it.
 *   * &bdquo;Serverinhaber-Dashboard&ldquo; was shown to everyone,
 *     including team members who are not the owner.
 *
 * Now: the dot reflects the real gateway latency, refresh actually
 * refetches, and the counts say what they are worth.
 */

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import React, { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Hash, Loader2, RefreshCw, Shield, Users } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Guild {
  id: string;
  name: string;
  icon: string | null;
  owner_id: string;
  member_count: number;
  role_count: number;
  channel_count: number;
}

/** How the gateway latency reads to somebody who is not an engineer. */
function health(latency: number | null) {
  if (latency === null) {
    return {
      tone: "bg-slate-600",
      ring: "ring-slate-500/30",
      label: "Unbekannt",
      hint: "Der Status konnte nicht abgefragt werden.",
    };
  }
  if (latency <= 0 || latency > 5000) {
    // discord.py reports Infinity as a huge number before the first
    // heartbeat, and 0 before the connection is up at all.
    return {
      tone: "bg-red-500",
      ring: "ring-red-500/30",
      label: "Offline",
      hint: "Der Bot ist gerade nicht mit Discord verbunden.",
    };
  }
  if (latency > 500) {
    return {
      tone: "bg-amber-500",
      ring: "ring-amber-500/30",
      label: "Träge",
      hint: `${Math.round(latency)} ms zu Discord — Befehle brauchen länger.`,
    };
  }
  return {
    tone: "bg-emerald-500",
    ring: "ring-emerald-500/30",
    label: "Online",
    hint: `${Math.round(latency)} ms zu Discord.`,
  };
}

function Stat({ icon: Icon, label, value }: any) {
  useWebsiteLocale();
  return (
    <div className="flex items-center gap-2.5">
      <Icon className="h-4 w-4 shrink-0 text-slate-600" />
      <div className="min-w-0">
        <span className="text-[15px] font-semibold text-white">
          {Number(value ?? 0).toLocaleString(websiteLocale())}
        </span>{" "}
        <span className="text-[13px] text-slate-500">{label}</span>
      </div>
    </div>
  );
}

export function GuildHeader({
  guild,
  isOwner,
}: {
  guild: Guild;
  isOwner: boolean;
}) {
  useWebsiteLocale();
  const router = useRouter();
  const [latency, setLatency] = useState<number | null>(null);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const ping = useCallback(async () => {
    try {
      const status = await api.getBotStatus();
      setLatency(typeof status?.latency === "number" ? status.latency : null);
    } catch {
      // A failed status call means the API is unreachable, which for
      // this dot is the same thing as the bot being down.
      setLatency(-1);
    } finally {
      setChecked(true);
    }
  }, []);

  useEffect(() => {
    ping();
    // Slow on purpose: this is a health dot, not a monitor.
    const timer = setInterval(ping, 60_000);
    return () => clearInterval(timer);
  }, [ping]);

  /**
   * Refresh for real.
   *
   * router.refresh() refetches the server components, which is what the
   * old <Link> to the same route did not do.
   */
  const refresh = async () => {
    setBusy(true);
    try {
      await ping();
      router.refresh();
      toast.success("Aktualisiert.");
    } finally {
      // The refetch is not awaitable, so this is a deliberate short
      // delay rather than a guess at when it finished.
      setTimeout(() => setBusy(false), 600);
    }
  };

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(guild.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Kopieren hat nicht geklappt.");
    }
  };

  const state = health(checked ? latency : null);

  return <section className="cloudtix-workspace-guild-header" aria-label="Dein ausgewählter Server">
    <div className="cloudtix-workspace-guild-identity">{guild.icon ? <Image src={guild.icon} alt="" width={48} height={48} unoptimized /> : <b>{guild.name.charAt(0).toUpperCase()}</b>}<div><h2 title={guild.name}>{guild.name}</h2><div className="cloudtix-workspace-guild-meta"><span title={state.hint}><i className={state.tone} />{state.label}</span><span>{isOwner ? "Serverinhaber" : "Serververwaltung"}</span><button type="button" onClick={copyId} title="Server-ID kopieren">{copied ? "ID kopiert" : guild.id}</button></div></div></div>
    <div className="cloudtix-workspace-guild-stats">{[{ icon: Users, label: "Mitglieder", value: guild.member_count }, { icon: Shield, label: "Rollen", value: guild.role_count }, { icon: Hash, label: "Kanäle", value: guild.channel_count }].map(stat => <div key={stat.label}><stat.icon size={13} /><strong>{Number(stat.value ?? 0).toLocaleString(websiteLocale())}</strong><span>{stat.label}</span></div>)}</div>
    <button type="button" onClick={refresh} disabled={busy} aria-label="Serverdaten aktualisieren" title="Zahlen und Status neu laden" className="cloudtix-workspace-guild-refresh">{busy ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}</button>
  </section>;
}
