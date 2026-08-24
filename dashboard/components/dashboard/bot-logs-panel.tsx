"use client";

/**
 * Bot-Logs: alles, was der Bot selbst protokolliert, an einer Stelle.
 *
 * Der Unterschied zu „Logs" darunter
 * ----------------------------------
 * Die neun Kategorien dort sind das, was auf DISCORD passiert:
 * Nachrichten, Rollen, Kanäle. Hier steht, was der BOT tut — ein
 * Softban durch den Honeypot, eine bestandene Verifizierung, eine
 * Automod-Strafe.
 *
 * Diese Einstellungen lagen über sechs Seiten verstreut. Wer wissen
 * wollte, wohin der Bot überall schreibt, musste sie einzeln
 * durchklicken.
 *
 * Die Hervorhebung beim Ankommen
 * ------------------------------
 * Kommt jemand über den Verweis von einer Modul-Seite („diese
 * Einstellung ist umgezogen"), steht in der Adresse `?highlight=<key>`.
 * Der betroffene Abschnitt klappt dann auf und leuchtet kurz gelb —
 * sonst landet man auf einer Liste mit sechs Einträgen und sucht,
 * welcher gemeint war.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ExternalLink,
  Info,
  Loader2,
  RefreshCw,
  ScrollText,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

interface Quelle {
  key: string;
  label: string;
  beschreibung: string;
  gruppe: string;
  seite: string;
  abschnitt: string;
  channel_id: string | null;
  channel_name: string | null;
  channel_missing: boolean;
  enabled: boolean;
  aktiv: boolean;
  can_send: boolean;
}

export function BotLogsPanel({ guildId }: { guildId: string }) {
  const params = useSearchParams();
  const hervorgehoben = params?.get("highlight") || "";

  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [speichert, setSpeichert] = useState("");
  const [offen, setOffen] = useState<string[]>([]);
  const [leuchtet, setLeuchtet] = useState("");
  const refs = useRef<Record<string, HTMLDivElement | null>>({});

  const laden = useCallback(async () => {
    try {
      setDaten(await api.botLogs(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Konnte die Protokolle nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, [guildId]);

  useEffect(() => {
    laden();
  }, [laden]);

  // Aus einem anderen Reiter hergekommen: aufklappen, hinscrollen,
  // kurz gelb leuchten lassen.
  useEffect(() => {
    if (!hervorgehoben || !daten) return;
    setOffen((bisher) =>
      bisher.includes(hervorgehoben) ? bisher : [...bisher, hervorgehoben]
    );
    setLeuchtet(hervorgehoben);

    const knoten = refs.current[hervorgehoben];
    if (knoten) {
      knoten.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    // Nach ein paar Sekunden ausblenden. Ein dauerhaft gelber Rahmen
    // sieht aus wie eine Warnung, und das ist es nicht.
    const timer = setTimeout(() => setLeuchtet(""), 4000);
    return () => clearTimeout(timer);
  }, [hervorgehoben, daten]);

  const umschalten = (key: string) => {
    setOffen((bisher) =>
      bisher.includes(key) ? bisher.filter((k) => k !== key) : [...bisher, key]
    );
  };

  const speichern = async (key: string, aenderung: any) => {
    setSpeichert(key);
    try {
      setDaten(await api.botLogSave(guildId, key, aenderung));
      toast.success("Gespeichert.");
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setSpeichert("");
    }
  };

  if (laedt) {
    return (
      <div className={cn(CARD, "flex items-center gap-3 text-slate-400")}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Wird geladen …
      </div>
    );
  }

  if (!daten) {
    return (
      <div className={CARD}>
        <p className="text-sm text-slate-400">
          Die Übersicht ist nicht erreichbar. Läuft der Bot?
        </p>
      </div>
    );
  }

  const kanaele = daten.channels || [];

  return (
    <div className="space-y-5">
      {/* ── Kopf ──────────────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-primary/15 p-2.5">
              <ScrollText className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h3 className="font-bold text-white">Was der Bot protokolliert</h3>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-400">
                Alles, was <strong className="text-slate-200">der Bot selbst</strong>{" "}
                tut — Softbans durch den Honeypot, Verifizierungen,
                Automod-Strafen. Früher lag jede dieser Einstellungen auf einer
                eigenen Seite.
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-2.5 text-center">
              <div className="text-lg font-bold text-white">
                {daten.active}
                <span className="text-sm text-slate-500">/{daten.total}</span>
              </div>
              <div className="text-xs text-slate-500">aktiv</div>
            </div>
            <button
              onClick={laden}
              className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-3 text-slate-300 transition hover:bg-white/[0.04]"
              title="Neu laden"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* ── Die Quellen, nach Gruppen ─────────────────────────────── */}
      {(daten.groups || []).map((gruppe: any) => (
        <div key={gruppe.name} className="space-y-2.5">
          <h4 className="px-1 text-xs font-bold uppercase tracking-widest text-slate-500">
            {gruppe.name}
          </h4>

          {gruppe.items.map((q: Quelle) => {
            const istOffen = offen.includes(q.key);
            const istHell = leuchtet === q.key;

            return (
              <div
                key={q.key}
                ref={(el) => {
                  refs.current[q.key] = el;
                }}
                className={cn(
                  "overflow-hidden rounded-3xl border bg-[#131318] transition-all duration-500",
                  istHell
                    ? "border-amber-400 ring-2 ring-amber-400/40"
                    : "border-slate-800"
                )}
              >
                {/* Kopfzeile — immer sichtbar */}
                <button
                  onClick={() => umschalten(q.key)}
                  className="flex w-full items-center gap-3 p-4 text-left transition hover:bg-white/[0.02]"
                >
                  <span
                    className={cn(
                      "h-2.5 w-2.5 shrink-0 rounded-full",
                      q.aktiv
                        ? "bg-emerald-400"
                        : q.channel_missing || !q.can_send
                          ? "bg-red-400"
                          : "bg-slate-700"
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-white">{q.label}</span>
                      {q.channel_name && (
                        <span className="rounded-lg bg-[#0f0f13] px-2 py-0.5 font-mono text-xs text-slate-400">
                          #{q.channel_name}
                        </span>
                      )}
                      {q.channel_missing && (
                        <span className="rounded-lg bg-red-500/15 px-2 py-0.5 text-xs text-red-300">
                          Kanal gelöscht
                        </span>
                      )}
                      {q.channel_id && !q.can_send && (
                        <span className="rounded-lg bg-red-500/15 px-2 py-0.5 text-xs text-red-300">
                          Bot darf nicht schreiben
                        </span>
                      )}
                      {!q.channel_id && (
                        <span className="text-xs text-slate-600">Kein Kanal</span>
                      )}
                    </div>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      {q.beschreibung}
                    </p>
                  </div>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 shrink-0 text-slate-500 transition-transform",
                      istOffen && "rotate-180"
                    )}
                  />
                </button>

                {/* Aufgeklappt */}
                {istOffen && (
                  <div className="space-y-4 border-t border-slate-800 p-4">
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Kanal
                      </label>
                      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                        <select
                          value={q.channel_id || ""}
                          disabled={speichert === q.key}
                          onChange={(e) =>
                            speichern(q.key, {
                              channel_id: e.target.value || null,
                            })
                          }
                          className="flex-1 rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50 disabled:opacity-50"
                        >
                          <option value="">Nicht protokollieren</option>
                          {kanaele.map((k: any) => (
                            <option key={k.id} value={k.id}>
                              #{k.name}
                            </option>
                          ))}
                        </select>

                        <Link
                          href={`/dashboard/guild/${guildId}/${q.seite}`}
                          className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-slate-300 transition hover:bg-white/[0.04]"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          Modul öffnen
                        </Link>
                      </div>
                    </div>

                    {/* Nur wo es einen eigenen Schalter gibt. Bei den
                        anderen ist „kein Kanal“ das Ausschalten. */}
                    {q.enabled !== undefined && q.channel_id && (
                      <p className="text-xs text-slate-600">
                        {q.aktiv
                          ? "Läuft. Einträge landen in dem Kanal oben."
                          : "Das Modul selbst ist ausgeschaltet — es kommt nichts an, egal welcher Kanal hier steht."}
                      </p>
                    )}

                    {speichert === q.key && (
                      <p className="flex items-center gap-1.5 text-xs text-slate-500">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Wird gespeichert …
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}

      {/* ── Was hier absichtlich fehlt ────────────────────────────── */}
      {(daten.excluded || []).length > 0 && (
        <div className={cn(CARD, "border-slate-800/60")}>
          <div className="flex gap-3">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
            <div className="text-xs leading-relaxed text-slate-500">
              <span className="font-semibold text-slate-400">
                Nicht hier zu finden:
              </span>
              <ul className="mt-1.5 space-y-1">
                {daten.excluded.map((e: any) => (
                  <li key={e.label}>
                    <strong className="text-slate-400">{e.label}</strong> —{" "}
                    {e.reason}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
