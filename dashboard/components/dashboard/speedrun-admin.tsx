"use client";

/**
 * Speedrun-Zugänge verwalten.
 *
 * Der Speedrun-Reiter ist gesperrt, bis jemand den Beta-Code eingibt.
 * Freigeschaltet wird damit ein *Server*, nicht ein Konto. Hier steht,
 * welche Server das getan haben, wer es war und wann — und hier lässt
 * sich der Zugang wieder nehmen.
 *
 * Zwei Handgriffe, die absichtlich verschieden sind:
 *
 *   **Entziehen**  Der Code muss neu eingegeben werden. Für den Fall,
 *                  dass ein Server den Besitzer wechselt oder jemand
 *                  den Code weitergegeben hat.
 *
 *   **Sperren**    Kein Code hilft mehr. Für den Fall, dass jemand
 *                  Unsinn treibt.
 *
 * Beides bricht einen laufenden Speedrun sofort ab. Wer jemandem den
 * Zugang nimmt, will nicht, dass der angefangene Umbau trotzdem noch
 * zehn Minuten weiterläuft.
 *
 * Die Rechteprüfung liegt nicht hier, sondern im Proxy (`/api/bot`) und
 * im Bot. Eine Oberfläche, die einen Knopf versteckt, ist keine Sperre.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import {
  Ban,
  CheckCircle2,
  Clock,
  Gauge,
  History,
  Loader2,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldOff,
  Unlock,
  Users,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";

/** Wie ein Ereignis im Verlauf heißt und aussieht. */
const EVENTS: Record<string, { label: string; tone: string }> = {
  unlocked: { label: "freigeschaltet", tone: "text-emerald-400" },
  denied: { label: "abgelehnt", tone: "text-amber-400" },
  revoked: { label: "entzogen", tone: "text-amber-300" },
  banned: { label: "gesperrt", tone: "text-red-400" },
  unbanned: { label: "entsperrt", tone: "text-sky-400" },
  run_started: { label: "Lauf gestartet", tone: "text-slate-400" },
};

function when(seconds?: number | null) {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Stat({
  icon: Icon,
  value,
  label,
  tone,
}: {
  icon: React.ElementType;
  value: React.ReactNode;
  label: string;
  tone?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-[#0d1b31] p-4">
      <Icon className={cn("h-4 w-4 mb-2", tone || "text-slate-500")} />
      <p className="text-xl font-black text-white tabular-nums">{value}</p>
      <p className="text-[11px] text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}

export function SpeedrunAdmin() {
  const { data: session } = useSession();
  const actorId = session?.user?.id ?? "";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [guilds, setGuilds] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState("");
  // Welcher Server gerade seinen Verlauf zeigt.
  const [openLog, setOpenLog] = useState("");

  const load = useCallback(async () => {
    // allSettled: fällt der Verlauf aus, soll die Liste trotzdem
    // stehen. Mit Promise.all verlöre man beide, sobald einer hakt.
    const [list, log] = await Promise.allSettled([
      api.speedrunAdminGuilds(),
      api.speedrunAdminHistory("", 150),
    ]);

    if (list.status === "fulfilled") {
      setGuilds(list.value?.guilds ?? []);
      setStats(list.value?.stats ?? null);
      setError("");
    } else {
      setError(list.reason?.message || "Die Liste ließ sich nicht laden.");
    }

    if (log.status === "fulfilled") setEvents(log.value?.events ?? []);

    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return guilds;
    return guilds.filter(
      (guild) =>
        String(guild.guild_id).includes(needle) ||
        String(guild.name || "").toLowerCase().includes(needle)
    );
  }, [guilds, query]);

  const act = async (
    guildId: string,
    what: "revoke" | "ban" | "unban",
    reason = ""
  ) => {
    setBusyId(guildId + what);
    try {
      if (what === "revoke") {
        const answer = await api.speedrunAdminRevoke(guildId, actorId);
        toast.success(
          answer?.run_cancelled
            ? "Entzogen — ein laufender Speedrun wurde abgebrochen."
            : "Entzogen. Der Code muss neu eingegeben werden."
        );
      } else if (what === "ban") {
        const answer = await api.speedrunAdminBan(guildId, actorId, reason);
        toast.success(
          answer?.run_cancelled
            ? "Gesperrt — ein laufender Speedrun wurde abgebrochen."
            : "Gesperrt. Kein Code hilft mehr."
        );
      } else {
        await api.speedrunAdminUnban(guildId, actorId);
        toast.success("Entsperrt. Der Code muss neu eingegeben werden.");
      }
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBusyId("");
    }
  };

  const confirmRevoke = (guild: any) => {
    const name = guild.name || guild.guild_id;
    if (
      confirm(
        `Zugang für „${name}“ entziehen?\n\n` +
          "Der Code muss danach neu eingegeben werden. " +
          "Ein laufender Speedrun wird sofort abgebrochen."
      )
    ) {
      act(guild.guild_id, "revoke");
    }
  };

  const confirmBan = (guild: any) => {
    const name = guild.name || guild.guild_id;
    const reason = prompt(
      `„${name}“ dauerhaft sperren?\n\n` +
        "Danach hilft kein Code mehr. Ein laufender Speedrun wird sofort " +
        "abgebrochen.\n\nBegründung (wird dem Server angezeigt):"
    );
    // Abbrechen im Dialog gibt null zurück -- ein leerer Text ist
    // dagegen eine bewusste Eingabe und geht durch.
    if (reason === null) return;
    act(guild.guild_id, "ban", reason.trim());
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const logFor = (guildId: string) =>
    events.filter((entry) => String(entry.guild_id) === String(guildId));

  return (
    <section className="space-y-6">
      {/* ── Kopf ─────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex gap-3">
          <div className="h-10 w-10 rounded-2xl bg-cyan-400/15 grid place-items-center shrink-0">
            <Gauge className="h-5 w-5 text-cyan-300" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white">Speedrun-Zugänge</p>
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              Welche Server den Beta-Code eingegeben haben. Entziehen heißt:
              neu eingeben. Sperren heißt: kein Code hilft mehr. Beides bricht
              einen laufenden Speedrun ab.
            </p>
          </div>
          <button
            onClick={() => {
              setLoading(true);
              load();
            }}
            className="ml-auto shrink-0 h-9 w-9 rounded-xl border border-slate-800 grid place-items-center text-slate-400 hover:text-white hover:border-slate-700 transition-colors"
            title="Neu laden"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <div className="rounded-xl bg-red-500/[0.06] border border-red-500/20 p-3.5 flex gap-2.5">
            <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-200/80 leading-relaxed">{error}</p>
          </div>
        )}

        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat
              icon={Unlock}
              value={stats.unlocked}
              label="freigeschaltet"
              tone="text-emerald-400"
            />
            <Stat
              icon={ShieldOff}
              value={stats.banned}
              label="gesperrt"
              tone="text-red-400"
            />
            <Stat icon={Gauge} value={stats.runs} label="Läufe gesamt" />
            <Stat icon={Users} value={stats.total} label="Server bekannt" />
          </div>
        )}
      </div>

      {/* ── Liste ────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex items-center gap-3 flex-wrap">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Server
          </p>
          <label className="relative ml-auto">
            <Search className="h-3.5 w-3.5 text-slate-600 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Name oder ID"
              className="w-44 sm:w-60 bg-[#0d1b31] border border-slate-800 rounded-xl pl-8 pr-3 py-2 text-[12px] text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-slate-700"
            />
          </label>
        </div>

        {shown.length === 0 ? (
          <p className="text-[12px] text-slate-500 py-6 text-center">
            {guilds.length === 0
              ? "Noch hat kein Server den Code eingegeben."
              : "Nichts gefunden."}
          </p>
        ) : (
          <div className="space-y-2.5">
            {shown.map((guild) => {
              const open = openLog === guild.guild_id;
              const entries = open ? logFor(guild.guild_id) : [];
              return (
                <div
                  key={guild.guild_id}
                  className={cn(
                    "rounded-2xl border p-4 transition-colors",
                    guild.banned
                      ? "border-red-500/25 bg-red-500/[0.04]"
                      : "border-slate-800 bg-[#0d1b31]"
                  )}
                >
                  <div className="flex items-start gap-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <p className="font-black text-white text-sm flex items-center gap-2 flex-wrap">
                        {guild.name || "Unbekannter Server"}
                        {guild.banned ? (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-black tracking-widest bg-red-500/15 text-red-300">
                            GESPERRT
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-black tracking-widest bg-emerald-500/15 text-emerald-300">
                            FREI
                          </span>
                        )}
                        {!guild.bot_present && (
                          <span
                            className="px-1.5 py-0.5 rounded text-[9px] font-black tracking-widest bg-slate-700/40 text-slate-400"
                            title="Der Bot ist auf diesem Server nicht mehr."
                          >
                            BOT WEG
                          </span>
                        )}
                      </p>
                      <p className="text-[11px] text-slate-600 font-mono mt-1">
                        {guild.guild_id}
                        {guild.members ? ` · ${guild.members} Mitglieder` : ""}
                      </p>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2.5 text-[11px] text-slate-500">
                        <span>
                          Freigeschaltet:{" "}
                          <span className="text-slate-400">
                            {when(guild.unlocked_at)}
                          </span>
                        </span>
                        {guild.unlocked_by && (
                          <span>
                            von{" "}
                            <span className="text-slate-400 font-mono">
                              {guild.unlocked_by}
                            </span>
                          </span>
                        )}
                        <span>
                          Läufe:{" "}
                          <span className="text-slate-400 tabular-nums">
                            {guild.runs}
                          </span>
                        </span>
                        {guild.last_run_at && (
                          <span>
                            zuletzt{" "}
                            <span className="text-slate-400">
                              {when(guild.last_run_at)}
                            </span>
                          </span>
                        )}
                      </div>

                      {guild.banned && (
                        <p className="text-[11px] text-red-200/70 mt-2 leading-relaxed">
                          Gesperrt am {when(guild.banned_at)}
                          {guild.banned_by ? ` von ${guild.banned_by}` : ""}
                          {guild.ban_reason ? ` — ${guild.ban_reason}` : ""}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 flex-wrap shrink-0">
                      <button
                        onClick={() => setOpenLog(open ? "" : guild.guild_id)}
                        className="px-3 py-1.5 rounded-lg border border-slate-800 text-slate-400 text-[10px] font-black uppercase tracking-wider hover:text-white hover:border-slate-700 transition-colors inline-flex items-center gap-1.5"
                      >
                        <History className="h-3 w-3" />
                        Verlauf
                      </button>

                      {guild.banned ? (
                        <button
                          onClick={() => act(guild.guild_id, "unban")}
                          disabled={busyId === guild.guild_id + "unban"}
                          className="px-3 py-1.5 rounded-lg border border-sky-500/30 text-sky-300/90 text-[10px] font-black uppercase tracking-wider hover:bg-sky-500/10 transition-colors inline-flex items-center gap-1.5 disabled:opacity-50"
                        >
                          {busyId === guild.guild_id + "unban" ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <RotateCcw className="h-3 w-3" />
                          )}
                          Entsperren
                        </button>
                      ) : (
                        <>
                          <button
                            onClick={() => confirmRevoke(guild)}
                            disabled={busyId === guild.guild_id + "revoke"}
                            className="px-3 py-1.5 rounded-lg border border-amber-500/30 text-amber-300/90 text-[10px] font-black uppercase tracking-wider hover:bg-amber-500/10 transition-colors inline-flex items-center gap-1.5 disabled:opacity-50"
                          >
                            {busyId === guild.guild_id + "revoke" ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <RotateCcw className="h-3 w-3" />
                            )}
                            Entziehen
                          </button>
                          <button
                            onClick={() => confirmBan(guild)}
                            disabled={busyId === guild.guild_id + "ban"}
                            className="px-3 py-1.5 rounded-lg border border-red-500/30 text-red-300/90 text-[10px] font-black uppercase tracking-wider hover:bg-red-500/10 transition-colors inline-flex items-center gap-1.5 disabled:opacity-50"
                          >
                            {busyId === guild.guild_id + "ban" ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Ban className="h-3 w-3" />
                            )}
                            Sperren
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {open && (
                    <div className="mt-3 pt-3 border-t border-slate-800/70 space-y-1">
                      {entries.length === 0 ? (
                        <p className="text-[11px] text-slate-600">
                          Für diesen Server steht nichts im Verlauf.
                        </p>
                      ) : (
                        entries.map((entry) => {
                          const meta = EVENTS[entry.event] ?? {
                            label: entry.event,
                            tone: "text-slate-400",
                          };
                          return (
                            <div
                              key={entry.id}
                              className="flex items-baseline gap-2.5 text-[11px]"
                            >
                              <span className="text-slate-600 font-mono shrink-0 tabular-nums">
                                {when(entry.at)}
                              </span>
                              <span className={cn("font-bold shrink-0", meta.tone)}>
                                {meta.label}
                              </span>
                              <span className="text-slate-500 truncate">
                                {entry.user_id
                                  ? `Nutzer ${entry.user_id}`
                                  : entry.actor_id
                                  ? `Admin ${entry.actor_id}`
                                  : ""}
                                {entry.detail ? ` · ${entry.detail}` : ""}
                              </span>
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Verlauf über alle Server ─────────────────────── */}
      <div className={cn(CARD, "space-y-3")}>
        <p className="text-xs font-black uppercase tracking-widest text-slate-500">
          Letzte Ereignisse
        </p>
        {events.length === 0 ? (
          <p className="text-[12px] text-slate-500">Noch nichts passiert.</p>
        ) : (
          <div className="space-y-1 max-h-[320px] overflow-y-auto">
            {events.slice(0, 80).map((entry) => {
              const meta = EVENTS[entry.event] ?? {
                label: entry.event,
                tone: "text-slate-400",
              };
              const guild = guilds.find(
                (item) => String(item.guild_id) === String(entry.guild_id)
              );
              return (
                <div
                  key={entry.id}
                  className="flex items-baseline gap-2.5 text-[11px] py-0.5"
                >
                  <Clock className="h-3 w-3 text-slate-700 shrink-0 self-center" />
                  <span className="text-slate-600 font-mono shrink-0 tabular-nums">
                    {when(entry.at)}
                  </span>
                  <span className={cn("font-bold shrink-0", meta.tone)}>
                    {meta.label}
                  </span>
                  <span className="text-slate-500 truncate">
                    {guild?.name || entry.guild_id}
                    {entry.detail ? ` · ${entry.detail}` : ""}
                  </span>
                </div>
              );
            })}
          </div>
        )}
        <p className="text-[10px] text-slate-600 leading-relaxed">
          <CheckCircle2 className="h-3 w-3 inline mr-1 -mt-0.5" />
          Auch Fehlversuche stehen hier. Ein Server mit vierzig abgelehnten
          Eingaben ist etwas anderes als einer mit einem Vertipper.
        </p>
      </div>
    </section>
  );
}
