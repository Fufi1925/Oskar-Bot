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

function Stat({ icon: Icon, label, value }: any) {
  return (
    <div className="flex items-center gap-2.5">
      <Icon className="h-4 w-4 shrink-0 text-slate-600" />
      <div className="min-w-0">
        <span className="text-[15px] font-semibold text-white">
          {Number(value ?? 0).toLocaleString("de-DE")}
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
    <div className="rounded-2xl border border-slate-800 bg-[#131318] p-4 sm:p-5">
      <div className="flex items-start gap-4">
        {/* Das Serverbild. 56px statt 120 -- es ist eine Kennung,
            kein Titelbild, und auf dem Telefon nahm es ein Drittel
            der Breite ein. */}
        <div className="relative shrink-0">
          {guild.icon ? (
            <Image
              src={guild.icon}
              alt=""
              width={56}
              height={56}
              className="h-14 w-14 rounded-xl object-cover"
            />
          ) : (
            <div className="grid h-14 w-14 place-items-center rounded-xl bg-indigo-500/15 text-[20px] font-bold text-indigo-300">
              {guild.name.charAt(0)}
            </div>
          )}
          <span
            title={state.hint}
            className={cn(
              "absolute -bottom-1 -right-1 h-4 w-4 rounded-full border-2 border-[#131318]",
              state.tone,
            )}
          />
        </div>

        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[20px] sm:text-[24px] font-bold tracking-tight text-white">
            {guild.name}
          </h1>

          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-slate-500">
            <span className="text-slate-400">{state.label}</span>
            <span className="text-slate-700">·</span>
            <span>
              {isOwner ? "Du bist Serverinhaber" : "Du verwaltest diesen Server"}
            </span>
            <span className="text-slate-700">·</span>
            <button
              type="button"
              onClick={copyId}
              title="Server-ID kopieren"
              className="font-mono transition-colors hover:text-slate-300"
            >
              {copied ? "ID kopiert" : guild.id}
            </button>
          </div>
        </div>

        {/* Nur ein Symbol: „Aktualisieren“ ausgeschrieben in
            Versalien war der lauteste Knopf auf der Seite, obwohl er
            am seltensten gebraucht wird. */}
        <button
          type="button"
          onClick={refresh}
          disabled={busy}
          title="Zahlen und Status neu laden"
          aria-label="Aktualisieren"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-slate-800 text-slate-500 transition-colors hover:border-slate-700 hover:text-white disabled:opacity-40"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Die drei Zahlen. Auf dem Telefon untereinander statt in
          drei Kästen nebeneinander, die dort ohnehin umbrechen. */}
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-slate-800 pt-4">
        <Stat icon={Users} label="Mitglieder" value={guild.member_count} />
        <Stat icon={Shield} label="Rollen" value={guild.role_count} />
        <Stat icon={Hash} label="Kanäle" value={guild.channel_count} />
      </div>
    </div>
  );
}
