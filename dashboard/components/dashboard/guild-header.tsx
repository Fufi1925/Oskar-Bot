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

function Stat({ icon: Icon, label, value, tint }: any) {
  return (
    <div className="flex items-center gap-3 bg-slate-800/50 px-5 py-3 rounded-2xl border border-white/5 shadow-inner">
      <div className={cn("p-2 rounded-lg bg-slate-900/50", tint)}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider leading-none mb-1">
          {label}
        </p>
        <p className="text-xl font-bold text-white leading-none">
          {Number(value ?? 0).toLocaleString("de-DE")}
        </p>
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

  return (
    <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 lg:p-8 shadow-xl shadow-black/20 border-glow-card">
      <div className="flex flex-col lg:flex-row lg:items-center gap-5 lg:gap-8">
        <div className="relative shrink-0">
          {guild.icon ? (
            <Image
              src={guild.icon}
              alt={guild.name}
              width={120}
              height={120}
              className="h-20 w-20 lg:h-[120px] lg:w-[120px] rounded-2xl lg:rounded-3xl border-4 border-slate-800 shadow-2xl object-cover"
            />
          ) : (
            <div className="h-20 w-20 lg:h-[120px] lg:w-[120px] bg-primary rounded-2xl lg:rounded-3xl flex items-center justify-center text-2xl lg:text-4xl font-bold text-white shadow-2xl border-4 border-slate-800">
              {guild.name.charAt(0)}
            </div>
          )}

          {/* The dot now says something. It used to be green always. */}
          <div
            title={state.hint}
            className={cn(
              "absolute -bottom-2 -right-2 p-2 rounded-xl shadow-lg border-2 border-[#131318] ring-4",
              state.tone,
              state.ring
            )}
          >
            <div
              className={cn(
                "h-3 w-3 rounded-full bg-white",
                state.label === "Online" && "animate-pulse"
              )}
            />
          </div>
        </div>

        <div className="flex-1 min-w-0 space-y-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-black text-white tracking-tight break-words">
                {guild.name}
              </h1>
              <button
                onClick={copyId}
                title="ID kopieren"
                className="px-3 py-1 bg-slate-800 rounded-lg text-[10px] uppercase font-black text-slate-500 tracking-tighter border border-white/5 hover:text-slate-300 hover:border-white/10 transition-colors"
              >
                {copied ? "Kopiert" : `ID: ${guild.id}`}
              </button>
            </div>

            <p className="text-slate-400 mt-1.5 text-sm flex items-center gap-2 flex-wrap">
              <span className={cn("h-1.5 w-1.5 rounded-full", state.tone)} />
              <span className="text-slate-300 font-medium">{state.label}</span>
              <span className="text-slate-600">·</span>
              {/* Said correctly: a team member is not the owner. */}
              <span>{isOwner ? "Du bist Serverinhaber" : "Du verwaltest diesen Server"}</span>
            </p>
          </div>

          <div className="flex flex-wrap gap-4">
            <Stat icon={Users} label="Mitglieder" value={guild.member_count} tint="text-blue-400" />
            <Stat icon={Shield} label="Rollen" value={guild.role_count} tint="text-emerald-400" />
            <Stat icon={Hash} label="Kanäle" value={guild.channel_count} tint="text-purple-400" />
          </div>
        </div>

        <div className="flex lg:flex-col gap-3 shrink-0">
          <button
            onClick={refresh}
            disabled={busy}
            title="Zahlen und Status neu laden"
            className="flex items-center justify-center gap-2 px-6 py-3 rounded-2xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Aktualisieren
          </button>
        </div>
      </div>
    </div>
  );
}
