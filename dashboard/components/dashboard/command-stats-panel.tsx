"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  EyeOff,
  Hash,
  Loader2,
  RefreshCw,
  Search,
  Slash,
  Terminal,
  TrendingUp,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CommandEntry {
  command: string;
  uses: number;
  failures: number;
  failure_rate: number;
}

interface GuildEntry {
  guild_id: string;
  guild_name: string | null;
  guild_icon?: string | null;
  uses: number;
  masked?: boolean;
}

interface StatsPayload {
  days: number;
  total_uses: number;
  total_failures: number;
  unique_commands: number;
  registered_commands: number;
  commands: CommandEntry[];
  daily: Array<{ day: string; uses: number }>;
  guilds: GuildEntry[];
  unused: string[];
  guilds_masked?: boolean;
}

const CARD =
  "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";

/** Slash-Befehle werden mit führendem Schrägstrich gezählt. */
function isSlash(command: string) {
  return command.startsWith("/");
}

/** Eine Zahl mit deutschem Tausenderpunkt. */
function num(value: number) {
  return value.toLocaleString("de-DE");
}

/**
 * Welche Befehle die Leute wirklich benutzen.
 *
 * Der Reiter war bis zuletzt an drei Stellen kaputt:
 *
 *   1. Er hing an `metrics.view`, und die hatten sechs von einundvierzig
 *      Rollen — für fast jede Dashboard-Rolle war er unsichtbar.
 *   2. Wer ihn doch sah, bekam beim Klick 403: `command-stats` stand
 *      nicht in der Berechtigungstabelle des Proxys.
 *   3. Gezählt wurden nur Prefix-Befehle. Slash lief komplett vorbei.
 *
 * Seit dieser Runde trennt die Anzeige beide Wege, denn genau darum
 * geht es: `/ban` und `ban` sind derselbe Befehl, aber nicht dieselbe
 * Bedienung.
 */
export function CommandStatsPanel() {
  const [data, setData] = useState<StatsPayload | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [showUnused, setShowUnused] = useState(false);
  const [query, setQuery] = useState("");
  // "all" | "slash" | "prefix"
  const [kind, setKind] = useState<"all" | "slash" | "prefix">("all");

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.getCommandStats(days));
    } catch (err: any) {
      toast.error(err?.message || "Die Statistik ließ sich nicht laden.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  const commands = data?.commands ?? [];

  // Erst filtern, dann zählen: die Balkenlänge muss sich auf das
  // beziehen, was gerade zu sehen ist. Sonst sind bei aktivem Filter
  // alle Balken winzig, weil der Größte weggefiltert wurde.
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return commands.filter((entry) => {
      if (kind === "slash" && !isSlash(entry.command)) return false;
      if (kind === "prefix" && isSlash(entry.command)) return false;
      if (needle && !entry.command.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [commands, kind, query]);

  const slashCount = useMemo(
    () => commands.filter((entry) => isSlash(entry.command)).length,
    [commands]
  );
  const slashUses = useMemo(
    () =>
      commands
        .filter((entry) => isSlash(entry.command))
        .reduce((sum, entry) => sum + entry.uses, 0),
    [commands]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!data) return null;

  const maxUses = Math.max(...shown.map((entry) => entry.uses), 1);
  const maxDaily = Math.max(...data.daily.map((entry) => entry.uses), 1);
  const prefixUses = data.total_uses - slashUses;
  const slashShare = data.total_uses
    ? Math.round((slashUses / data.total_uses) * 100)
    : 0;

  return (
    <section className="space-y-6">
      {/* Kopf: worum es geht, und der Zeitraum */}
      <div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center shrink-0">
              <Terminal className="h-6 w-6 text-primary" />
            </div>
            <div className="min-w-0">
              <h3 className="text-xl font-black text-white">Befehls-Nutzung</h3>
              <p className="text-sm text-slate-400 mt-1">
                {num(data.total_uses)} Aufrufe · {data.unique_commands} von{" "}
                {data.registered_commands} Befehlen benutzt
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex gap-1.5 p-1.5 bg-[#131318]/70 border border-slate-800 rounded-2xl">
              {[7, 30, 90].map((value) => (
                <button
                  key={value}
                  onClick={() => setDays(value)}
                  className={cn(
                    "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all",
                    days === value
                      ? "bg-primary text-white"
                      : "text-slate-400 hover:text-white"
                  )}
                >
                  {value} Tage
                </button>
              ))}
            </div>
            <button
              onClick={load}
              title="Neu laden"
              className="p-3 rounded-2xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
            >
              <RefreshCw className="h-4 w-4 text-primary" />
            </button>
          </div>
        </div>
      </div>

      {data.total_uses === 0 ? (
        <div className={cn(CARD, "p-12 text-center")}>
          <Activity className="h-10 w-10 text-slate-700 mx-auto mb-4" />
          <p className="text-slate-400">
            In den letzten {data.days} Tagen wurde kein Befehl aufgezeichnet.
          </p>
          <p className="text-xs text-slate-600 mt-2">
            Gezählt wird erst seit dem Deploy dieser Funktion — was davor lief,
            fehlt.
          </p>
        </div>
      ) : (
        <>
          {/* Slash gegen Prefix. Die eigentliche Frage hinter dieser
              Seite: bedienen die Leute den Bot noch mit Prefix? */}
          <div className={CARD}>
            <p className="text-xs font-black uppercase tracking-widest text-slate-500 mb-4">
              Wie der Bot bedient wird
            </p>
            <div className="flex h-3 rounded-full overflow-hidden bg-slate-800/60">
              <div
                className="bg-primary transition-all duration-500"
                style={{ width: `${slashShare}%` }}
              />
              <div
                className="bg-amber-500/70 transition-all duration-500"
                style={{ width: `${100 - slashShare}%` }}
              />
            </div>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-4">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-primary shrink-0" />
                <span className="text-sm text-slate-300">
                  Slash <span className="text-slate-500">/</span>
                </span>
                <span className="text-sm font-bold text-white tabular-nums">
                  {num(slashUses)}
                </span>
                <span className="text-xs text-slate-600">
                  ({slashCount} Befehle)
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-amber-500/70 shrink-0" />
                <span className="text-sm text-slate-300">Prefix</span>
                <span className="text-sm font-bold text-white tabular-nums">
                  {num(prefixUses)}
                </span>
              </div>
              {data.total_failures > 0 && (
                <div className="flex items-center gap-2 sm:ml-auto">
                  <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0" />
                  <span className="text-sm text-slate-400">
                    {num(data.total_failures)} fehlgeschlagen
                  </span>
                </div>
              )}
            </div>
          </div>

          {data.daily.length > 1 && (
            <div className={CARD}>
              <p className="text-xs font-black uppercase tracking-widest text-slate-500 mb-4">
                Pro Tag
              </p>
              <div className="flex items-end gap-1 h-28">
                {data.daily.map((entry) => (
                  <div
                    key={entry.day}
                    className="flex-1 bg-primary/60 hover:bg-primary rounded-t transition-colors min-w-[3px]"
                    style={{
                      height: `${Math.max((entry.uses / maxDaily) * 100, 3)}%`,
                    }}
                    title={`${entry.day}: ${num(entry.uses)}`}
                  />
                ))}
              </div>
              <div className="flex justify-between mt-2 text-[10px] text-slate-600 tabular-nums">
                <span>{data.daily[0]?.day}</span>
                <span>{data.daily[data.daily.length - 1]?.day}</span>
              </div>
            </div>
          )}

          {/* Die Liste. Suchfeld und Umschalter, weil 235+ Befehle
              ohne beides eine Wand aus Zeilen sind. */}
          <div
            className={cn(
              "bg-[#131318] border border-slate-800 rounded-3xl overflow-hidden",
              "border-glow-card is-clipped"
            )}
          >
            <div className="px-4 sm:px-6 py-4 border-b border-white/5 flex flex-wrap items-center gap-3">
              <TrendingUp className="h-5 w-5 text-primary shrink-0" />
              <h4 className="font-black text-white text-sm uppercase tracking-wider">
                Am meisten benutzt
              </h4>

              <div className="flex gap-1 ml-auto p-1 bg-[#0e0e12] border border-slate-800 rounded-xl">
                {(
                  [
                    ["all", "Alle", null],
                    ["slash", "Slash", Slash],
                    ["prefix", "Prefix", Hash],
                  ] as const
                ).map(([value, label, Icon]) => (
                  <button
                    key={value}
                    onClick={() => setKind(value)}
                    className={cn(
                      "px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-wider transition-all flex items-center gap-1.5",
                      kind === value
                        ? "bg-primary/20 text-primary"
                        : "text-slate-500 hover:text-slate-300"
                    )}
                  >
                    {Icon && <Icon className="h-3 w-3" />}
                    {label}
                  </button>
                ))}
              </div>

              <div className="relative w-full sm:w-52">
                <Search className="h-3.5 w-3.5 text-slate-600 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Befehl suchen"
                  className="w-full bg-[#0e0e12] border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder:text-slate-600 outline-none focus:border-primary/50 transition-colors"
                />
              </div>
            </div>

            {shown.length === 0 ? (
              <p className="px-6 py-10 text-center text-sm text-slate-500">
                Kein Befehl passt zu dieser Suche.
              </p>
            ) : (
              <div className="divide-y divide-white/5 max-h-[28rem] overflow-y-auto">
                {shown.slice(0, 60).map((entry) => (
                  <div
                    key={entry.command}
                    className="px-4 sm:px-6 py-3 flex items-center gap-3 sm:gap-4 hover:bg-white/[0.02] transition-colors"
                  >
                    <span
                      className={cn(
                        "shrink-0 h-6 w-6 rounded-lg flex items-center justify-center",
                        isSlash(entry.command)
                          ? "bg-primary/15 text-primary"
                          : "bg-amber-500/10 text-amber-400/80"
                      )}
                      title={
                        isSlash(entry.command)
                          ? "Slash-Befehl"
                          : "Prefix-Befehl"
                      }
                    >
                      {isSlash(entry.command) ? (
                        <Slash className="h-3 w-3" />
                      ) : (
                        <Hash className="h-3 w-3" />
                      )}
                    </span>

                    <code className="text-sm font-mono text-white w-32 sm:w-44 truncate shrink-0">
                      {entry.command}
                    </code>

                    <div className="flex-1 h-5 bg-slate-800/60 rounded-lg overflow-hidden min-w-[2rem]">
                      <div
                        className={cn(
                          "h-full rounded-lg transition-all duration-500",
                          isSlash(entry.command)
                            ? "bg-primary"
                            : "bg-amber-500/70"
                        )}
                        style={{
                          width: `${Math.max(
                            (entry.uses / maxUses) * 100,
                            2
                          )}%`,
                        }}
                      />
                    </div>

                    <span className="text-sm font-bold text-white w-12 sm:w-16 text-right shrink-0 tabular-nums">
                      {num(entry.uses)}
                    </span>

                    {entry.failures > 0 && (
                      <span
                        className={cn(
                          "text-[10px] font-black w-12 text-right shrink-0 tabular-nums",
                          entry.failure_rate > 25
                            ? "text-red-400"
                            : "text-amber-400"
                        )}
                        title={`${num(entry.failures)} fehlgeschlagen`}
                      >
                        {entry.failure_rate}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {shown.length > 60 && (
              <p className="px-6 py-3 text-[11px] text-slate-600 border-t border-white/5">
                {shown.length - 60} weitere ausgeblendet — such nach dem Namen.
              </p>
            )}
          </div>

          {data.guilds.length > 0 && (
            <div className={CARD}>
              <div className="flex items-center gap-3 mb-4">
                <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Aktivste Server
                </p>
                {data.guilds_masked && (
                  <span className="flex items-center gap-1.5 text-[10px] font-bold text-slate-500 bg-white/[0.04] border border-white/5 rounded-full px-2.5 py-1">
                    <EyeOff className="h-3 w-3" />
                    verborgen
                  </span>
                )}
              </div>

              <div className="space-y-2">
                {data.guilds.slice(0, 8).map((guild, index) => (
                  <div
                    key={guild.guild_id || `masked-${index}`}
                    className="flex items-center gap-3"
                  >
                    <span
                      className={cn(
                        "h-7 w-7 rounded-lg shrink-0 flex items-center justify-center text-[10px] font-black",
                        guild.masked
                          ? "bg-slate-800/80 text-slate-600"
                          : "bg-primary/15 text-primary"
                      )}
                    >
                      {guild.masked ? "?" : index + 1}
                    </span>
                    <span
                      className={cn(
                        "text-sm truncate",
                        guild.masked
                          ? "text-slate-500 tracking-[0.2em]"
                          : "text-slate-300"
                      )}
                    >
                      {guild.guild_name || guild.guild_id}
                    </span>
                    <span className="text-sm font-bold text-primary shrink-0 ml-auto tabular-nums">
                      {num(guild.uses)}
                    </span>
                  </div>
                ))}
              </div>

              {data.guilds_masked && (
                <p className="text-[11px] text-slate-600 mt-4 leading-relaxed">
                  Welche Server das sind, sehen nur Inhaber und Admins. Die
                  Zahlen stimmen — nur die Namen sind verdeckt.
                </p>
              )}
            </div>
          )}
        </>
      )}

      {data.unused.length > 0 && (
        <div className={CARD}>
          <button
            onClick={() => setShowUnused(!showUnused)}
            className="flex items-center gap-3 w-full text-left"
          >
            <AlertTriangle className="h-5 w-5 text-slate-600 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="font-black text-white text-sm">
                {data.unused.length} Befehle nie benutzt
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                Kandidaten zum Entfernen — oder dafür, sie bekannter zu machen
              </p>
            </div>
            <span className="text-xs font-black uppercase tracking-widest text-slate-600 shrink-0">
              {showUnused ? "Zu" : "Zeigen"}
            </span>
          </button>

          {showUnused && (
            <div className="flex flex-wrap gap-1.5 mt-4">
              {data.unused.map((command) => (
                <code
                  key={command}
                  className={cn(
                    "text-[10px] font-mono px-2 py-1 rounded-lg",
                    isSlash(command)
                      ? "bg-primary/[0.07] text-slate-500"
                      : "bg-white/[0.04] text-slate-500"
                  )}
                >
                  {command}
                </code>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
