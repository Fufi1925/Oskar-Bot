"use client";

/**
 * Backup — Sicherungen dieses Servers.
 *
 * ── Warum ein Knopf und keine Auswahlfelder ─────────────────────────
 *
 * Ausdrückliche Vorgabe: „einfach ein Knopf, Backup wird erstellt,
 * keine Fragen“. Was hineingehört, steht fest — Aufbau des Servers
 * und die Dashboard-Einstellungen. Eine Auswahl, die niemand ändert,
 * ist nur ein Klick mehr vor dem eigentlichen Klick.
 *
 * Einzige Ausnahme: Nachrichten. Die kosten Minuten statt Sekunden,
 * und das muss man wollen.
 *
 * ── Warum kein Live-Protokoll ───────────────────────────────────────
 *
 * Auch Vorgabe. Statt einer Zeilenflut steht ein Satz da, woran
 * gerade gearbeitet wird. Wer wissen will, was schiefging, findet den
 * Bericht danach.
 *
 * ── Die zwei Fragen beim Wiederherstellen ───────────────────────────
 *
 * Erst „alles löschen?“, dann „Einstellungen auch?“. In dieser
 * Reihenfolge, weil die erste die folgenreichere ist: sie entfernt
 * Kanäle samt Nachrichten und lässt sich nicht rückgängig machen.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, ArrowRight, Check, Clock, Crown, Database, Hash,
  Loader2, MessageSquare, Plus, RefreshCw, RotateCcw, Shield, Timer,
  Trash2, Users, X,
} from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl";
const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-3.5 py-2.5 " +
  "text-sm text-white focus:border-primary/50 focus:outline-none transition-colors";

interface Sicherung {
  id: number;
  kennung: string;
  erstellt_at: number;
  erstellt_von: string;
  groesse: number;
  kanaele: number;
  rollen: number;
  nachrichten: number;
  mit_einstellungen: boolean;
  mit_nachrichten: boolean;
  quelle: string;
  notiz: string;
}

/** Deutsche Schreibweise: Komma statt Punkt. */
function groesse(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toLocaleString("de-DE", {
      maximumFractionDigits: 0,
    })} KB`;
  }
  return `${(bytes / 1024 / 1024).toLocaleString("de-DE", {
    maximumFractionDigits: 1,
  })} MB`;
}

function zeitpunkt(sekunden: number): string {
  if (!sekunden) return "—";
  return new Date(sekunden * 1000).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Die Rückfragen beim Wiederherstellen.
 *
 * Ein eigenes Fenster statt `window.confirm`: es sind zwei Fragen mit
 * Folgen, und die zweite hängt nicht von der ersten ab. Zwei
 * Systemdialoge hintereinander liest niemand.
 */
function WiederherstellenFenster({
  sicherung,
  premium,
  onAbbruch,
  onStart,
}: {
  sicherung: Sicherung;
  premium: boolean;
  onAbbruch: () => void;
  onStart: (o: {
    alles_loeschen: boolean;
    mit_einstellungen: boolean;
    mit_nachrichten: boolean;
  }) => void;
}) {
  const [allesLoeschen, setAllesLoeschen] = useState(false);
  const [mitEinstellungen, setMitEinstellungen] = useState(true);
  const [mitNachrichten, setMitNachrichten] = useState(false);

  const hatNachrichten = sicherung.nachrichten > 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="wiederherstellen-titel"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-lg overflow-hidden rounded-3xl border border-slate-700 bg-[#131318] shadow-2xl">
        <div className="border-b border-slate-800 px-6 py-5">
          <h2
            id="wiederherstellen-titel"
            className="text-lg font-bold text-white"
          >
            {sicherung.kennung} wiederherstellen
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Vom {zeitpunkt(sicherung.erstellt_at)} · {sicherung.kanaele} Kanäle
            · {sicherung.rollen} Rollen
          </p>
        </div>

        <div className="space-y-3 px-6 py-5">
          {/* Frage 1 — die folgenreichere, deshalb zuerst. */}
          <button
            onClick={() => setAllesLoeschen((v) => !v)}
            className={cn(
              "flex w-full gap-3 rounded-2xl border p-4 text-left transition",
              allesLoeschen
                ? "border-red-500/40 bg-red-500/[0.06]"
                : "border-slate-800 bg-[#0f0f13] hover:bg-white/[0.02]"
            )}
          >
            <div
              className={cn(
                "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
                allesLoeschen
                  ? "border-red-400 bg-red-500"
                  : "border-slate-600"
              )}
            >
              {allesLoeschen && <Check className="h-3.5 w-3.5 text-white" />}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white">
                Alles zuerst löschen
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">
                Entfernt alle Kanäle und Rollen, die der Bot löschen darf,
                und baut die Sicherung sauber neu auf.
                {allesLoeschen && (
                  <span className="mt-1.5 block font-semibold text-red-300">
                    Nachrichten in den gelöschten Kanälen sind damit
                    unwiderruflich weg.
                  </span>
                )}
              </p>
              {!allesLoeschen && (
                <p className="mt-1 text-xs text-slate-600">
                  Aus: Fehlendes wird ergänzt, Vorhandenes bleibt stehen.
                </p>
              )}
            </div>
          </button>

          {/* Frage 2 — unabhängig von Frage 1. */}
          <button
            onClick={() => setMitEinstellungen((v) => !v)}
            className={cn(
              "flex w-full gap-3 rounded-2xl border p-4 text-left transition",
              mitEinstellungen
                ? "border-primary/40 bg-primary/[0.06]"
                : "border-slate-800 bg-[#0f0f13] hover:bg-white/[0.02]"
            )}
          >
            <div
              className={cn(
                "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
                mitEinstellungen
                  ? "border-primary bg-primary"
                  : "border-slate-600"
              )}
            >
              {mitEinstellungen && <Check className="h-3.5 w-3.5 text-white" />}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white">
                Dashboard-Einstellungen auch wiederherstellen
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">
                Automod, Tickets, Begrüßung und alles andere, was in dieser
                Sicherung steckt.
              </p>
            </div>
          </button>

          {/* Frage 3 — nur wenn Nachrichten drin sind. */}
          {hatNachrichten && (
            <button
              onClick={() => premium && setMitNachrichten((v) => !v)}
              disabled={!premium}
              className={cn(
                "flex w-full gap-3 rounded-2xl border p-4 text-left transition",
                mitNachrichten
                  ? "border-amber-400/40 bg-amber-400/[0.06]"
                  : "border-slate-800 bg-[#0f0f13] hover:bg-white/[0.02]",
                !premium && "cursor-not-allowed opacity-50"
              )}
            >
              <div
                className={cn(
                  "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
                  mitNachrichten
                    ? "border-amber-400 bg-amber-400"
                    : "border-slate-600"
                )}
              >
                {mitNachrichten && <Check className="h-3.5 w-3.5 text-black" />}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-semibold text-white">
                  Nachrichten zurückschreiben
                  <Crown className="h-3.5 w-3.5 text-amber-400" />
                </div>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">
                  {sicherung.nachrichten.toLocaleString("de-DE")} Nachrichten.
                  Das dauert mehrere Minuten — Discord lässt nur wenige
                  gleichzeitig durch.
                </p>
                {mitNachrichten && (
                  <p className="mt-1.5 text-xs leading-relaxed text-amber-300/80">
                    Sie werden mit Name und Bild des ursprünglichen Autors
                    neu gepostet. Es sind neue Nachrichten mit neuem Datum —
                    Discord lässt keinen Bot als jemand anderes schreiben.
                  </p>
                )}
              </div>
            </button>
          )}
        </div>

        <div className="flex flex-col gap-2 border-t border-slate-800 px-6 py-4 sm:flex-row-reverse">
          <button
            onClick={() =>
              onStart({
                alles_loeschen: allesLoeschen,
                mit_einstellungen: mitEinstellungen,
                mit_nachrichten: mitNachrichten,
              })
            }
            className={cn(
              "inline-flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition",
              allesLoeschen
                ? "bg-red-500 text-white hover:bg-red-400"
                : "bg-primary text-white hover:brightness-110"
            )}
          >
            {allesLoeschen ? "Löschen und wiederherstellen" : "Wiederherstellen"}
            <ArrowRight className="h-4 w-4" />
          </button>
          <button
            onClick={onAbbruch}
            className="inline-flex flex-1 items-center justify-center rounded-xl border border-slate-800 bg-[#0f0f13] px-4 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-white/[0.04]"
          >
            Abbrechen
          </button>
        </div>
      </div>
    </div>
  );
}

export function BackupPanel({ guildId }: { guildId: string }) {
  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);
  const [gewaehlt, setGewaehlt] = useState<Sicherung | null>(null);
  const [mitNachrichten, setMitNachrichten] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const laden = useCallback(async (still = false) => {
    if (!still) setLaedt(true);
    try {
      setDaten(await api.backupList(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Die Sicherungen ließen sich nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, [guildId]);

  useEffect(() => {
    laden();
  }, [laden]);

  const lauf = daten?.lauf;
  const laeuft = Boolean(lauf?.aktiv);

  // Solange etwas läuft, alle zwei Sekunden nachfragen.
  //
  // Kein Dauerstrom: ein Satz alle zwei Sekunden reicht, um zu
  // zeigen, dass sich etwas tut, und kostet fast nichts.
  useEffect(() => {
    if (!laeuft) {
      if (timer.current) window.clearInterval(timer.current);
      return;
    }
    timer.current = window.setInterval(() => laden(true), 2000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [laeuft, laden]);

  const premium = Boolean(daten?.premium);
  const sicherungen: Sicherung[] = daten?.backups ?? [];
  const grenze = Number(daten?.grenze ?? 1);
  const voll = sicherungen.length >= grenze;
  const auto = daten?.auto ?? {};

  const erstellen = async () => {
    setBeschaeftigt(true);
    try {
      await api.backupCreate(guildId, mitNachrichten && premium);
      toast.success("Sicherung wird erstellt.");
      await laden(true);
    } catch (err: any) {
      toast.error(err?.message || "Das Erstellen ist fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const loeschen = async (s: Sicherung) => {
    if (!window.confirm(`${s.kennung} endgültig löschen?`)) return;
    setBeschaeftigt(true);
    try {
      await api.backupDelete(guildId, s.kennung);
      toast.success("Gelöscht.");
      await laden(true);
    } catch (err: any) {
      toast.error(err?.message || "Das Löschen ist fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const wiederherstellen = async (optionen: any) => {
    if (!gewaehlt) return;
    const kennung = gewaehlt.kennung;
    setGewaehlt(null);
    setBeschaeftigt(true);
    try {
      await api.backupRestore(guildId, kennung, optionen);
      toast.success("Wiederherstellung läuft.");
      await laden(true);
    } catch (err: any) {
      toast.error(err?.message || "Das Wiederherstellen ist fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const autoSetzen = async (felder: any) => {
    setBeschaeftigt(true);
    try {
      const res = await api.backupAuto(guildId, felder);
      setDaten((d: any) => ({ ...d, auto: res.auto }));
    } catch (err: any) {
      toast.error(err?.message || "Das Speichern ist fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  if (laedt) {
    return (
      <div className={cn(CARD, "flex items-center gap-3 p-6 text-slate-400")}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Wird geladen …
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {gewaehlt && (
        <WiederherstellenFenster
          sicherung={gewaehlt}
          premium={premium}
          onAbbruch={() => setGewaehlt(null)}
          onStart={wiederherstellen}
        />
      )}

      {/* ── Läuft gerade etwas? ─────────────────────────────────── */}
      {laeuft && (
        <div className="flex items-center gap-3 rounded-3xl border border-primary/30 bg-primary/[0.06] p-4">
          <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />
          <div className="min-w-0">
            <div className="text-sm font-bold text-white">
              {lauf.art === "wiederherstellen"
                ? "Wird wiederhergestellt"
                : "Sicherung wird erstellt"}
            </div>
            <div className="mt-0.5 truncate text-xs text-slate-400">
              {lauf.schritt || "Wird vorbereitet"}
            </div>
          </div>
        </div>
      )}

      {/* ── Der Knopf ───────────────────────────────────────────── */}
      <div className={cn(CARD, "p-5 sm:p-6")}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1">
            <h3 className="font-bold text-white">Sicherung erstellen</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-400">
              Kanäle, Kategorien, Rollen, Rechte und alle
              Dashboard-Einstellungen dieses Servers. Dauert ein paar
              Sekunden.
            </p>

            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span
                className={cn(
                  "rounded-lg px-2 py-1 font-bold",
                  voll
                    ? "bg-amber-400/10 text-amber-300"
                    : "bg-[#0f0f13] text-slate-400"
                )}
              >
                {sicherungen.length} von {grenze}
              </span>
              {!premium && (
                <Link
                  href="/premium"
                  className="inline-flex items-center gap-1 rounded-lg bg-amber-400/10 px-2 py-1 font-bold text-amber-300 transition hover:bg-amber-400/20"
                >
                  <Crown className="h-3 w-3" />
                  Mit Premium bis {daten?.limits?.premium ?? 10}
                </Link>
              )}
            </div>

            {/* Nachrichten: die einzige Entscheidung vor dem Klick. */}
            {premium && (
              <label className="mt-3 flex cursor-pointer items-start gap-2.5">
                <input
                  type="checkbox"
                  checked={mitNachrichten}
                  onChange={(e) => setMitNachrichten(e.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0 accent-amber-400"
                />
                <span className="text-xs leading-relaxed text-slate-400">
                  Die letzten{" "}
                  {(daten?.limits?.nachrichten ?? 500).toLocaleString("de-DE")}{" "}
                  Nachrichten je Kanal mitsichern.{" "}
                  <span className="text-amber-300/80">
                    Dauert dann mehrere Minuten statt Sekunden.
                  </span>
                </span>
              </label>
            )}
          </div>

          <button
            onClick={erstellen}
            disabled={beschaeftigt || laeuft || voll}
            title={voll ? "Lösche zuerst eine alte Sicherung." : undefined}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white transition hover:brightness-110 disabled:opacity-40"
          >
            {beschaeftigt || laeuft ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Backup erstellen
          </button>
        </div>

        {voll && (
          <p className="mt-3 rounded-2xl border border-amber-400/25 bg-amber-400/[0.05] p-3 text-xs leading-relaxed text-amber-200/80">
            {premium
              ? `Alle ${grenze} Plätze belegt. Lösche eine alte Sicherung, dann geht es weiter.`
              : "Ohne Premium ist eine Sicherung möglich. Lösche die vorhandene — oder hol dir Premium für bis zu " +
                `${daten?.limits?.premium ?? 10}.`}
          </p>
        )}
      </div>

      {/* ── Die Liste ───────────────────────────────────────────── */}
      <div className={cn(CARD, "overflow-hidden")}>
        <div className="flex items-center justify-between border-b border-slate-800 bg-[#0f0f13] px-5 py-3">
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">
            Vorhandene Sicherungen
          </span>
          <button
            onClick={() => laden()}
            className="text-slate-500 transition hover:text-slate-300"
            title="Neu laden"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>

        {sicherungen.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <div className="mx-auto mb-3 w-fit rounded-2xl bg-[#0f0f13] p-3">
              <Database className="h-5 w-5 text-slate-700" />
            </div>
            <p className="text-sm font-bold text-slate-400">
              Noch keine Sicherung.
            </p>
            <p className="mt-1 text-xs text-slate-600">
              Ein Klick auf „Backup erstellen“ genügt.
            </p>
          </div>
        ) : (
          sicherungen.map((s, i) => (
            <div
              key={s.kennung}
              className={cn(
                "flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center",
                i > 0 && "border-t border-slate-800"
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-bold text-white">
                    {s.kennung}
                  </span>
                  {s.quelle === "auto" && (
                    <span className="rounded-md border border-sky-500/20 bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-sky-300">
                      Automatisch
                    </span>
                  )}
                  {s.mit_nachrichten && (
                    <span className="rounded-md border border-amber-400/20 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-amber-400">
                      Mit Nachrichten
                    </span>
                  )}
                </div>

                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {zeitpunkt(s.erstellt_at)}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Hash className="h-3 w-3" />
                    {s.kanaele} Kanäle
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Users className="h-3 w-3" />
                    {s.rollen} Rollen
                  </span>
                  {s.nachrichten > 0 && (
                    <span className="inline-flex items-center gap-1">
                      <MessageSquare className="h-3 w-3" />
                      {s.nachrichten.toLocaleString("de-DE")}
                    </span>
                  )}
                  <span>{groesse(s.groesse)}</span>
                </div>
              </div>

              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => setGewaehlt(s)}
                  disabled={beschaeftigt || laeuft}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 bg-[#0f0f13] px-3.5 py-2 text-xs font-bold text-slate-200 transition hover:bg-white/[0.04] disabled:opacity-40"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Wiederherstellen
                </button>
                <button
                  onClick={() => loeschen(s)}
                  disabled={beschaeftigt || laeuft}
                  className="inline-flex items-center justify-center rounded-xl border border-red-500/25 bg-red-500/[0.06] p-2 text-red-300 transition hover:bg-red-500/15 disabled:opacity-40"
                  title="Löschen"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── Automatik ───────────────────────────────────────────── */}
      <div className={cn(CARD, "relative p-5 sm:p-6")}>
        {!premium && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-3xl bg-[#0a0a0c]/75 backdrop-blur-[2px]">
            <div className="mx-4 max-w-sm rounded-2xl border-2 border-amber-400 bg-[#131318] p-5 text-center shadow-2xl">
              <div className="mx-auto mb-3 w-fit rounded-2xl bg-amber-400/15 p-3">
                <Crown className="h-6 w-6 text-amber-400" />
              </div>
              <div className="text-lg font-bold text-amber-400">
                Premium erforderlich
              </div>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">
                Mit Premium sichert der Bot automatisch — in einem Abstand,
                den du festlegst.
              </p>
              <Link
                href="/dashboard/premium/beta"
                className="mt-4 inline-flex items-center gap-2 rounded-2xl bg-amber-400 px-4 py-2.5 text-sm font-bold text-black transition hover:brightness-110"
              >
                Premium holen
              </Link>
            </div>
          </div>
        )}

        <div className={cn(!premium && "select-none")}>
          <div className="flex items-center gap-2">
            <Timer className="h-4 w-4 text-amber-400" />
            <h3 className="font-bold text-white">Automatisch sichern</h3>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Der Bot legt in festem Abstand von selbst eine Sicherung an.
          </p>

          <label className="mt-4 flex cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              checked={Boolean(auto.aktiv)}
              disabled={!premium || beschaeftigt}
              onChange={(e) => autoSetzen({ aktiv: e.target.checked })}
              className="h-4 w-4 accent-amber-400"
            />
            <span className="text-sm font-medium text-white">
              Automatik einschalten
            </span>
          </label>

          {auto.aktiv && (
            <div className="mt-4 space-y-4 rounded-2xl border border-slate-800 bg-[#0f0f13] p-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500">
                  Abstand
                </label>
                <select
                  value={String(auto.stunden ?? 24)}
                  disabled={!premium || beschaeftigt}
                  onChange={(e) =>
                    autoSetzen({ stunden: Number(e.target.value) })
                  }
                  className={cn(INPUT, "mt-1.5")}
                >
                  <option value="6">Alle 6 Stunden</option>
                  <option value="12">Alle 12 Stunden</option>
                  <option value="24">Täglich</option>
                  <option value="72">Alle 3 Tage</option>
                  <option value="168">Wöchentlich</option>
                  <option value="720">Monatlich</option>
                </select>
              </div>

              <label className="flex cursor-pointer items-start gap-2.5">
                <input
                  type="checkbox"
                  checked={Boolean(auto.alte_loeschen)}
                  disabled={!premium || beschaeftigt}
                  onChange={(e) =>
                    autoSetzen({ alte_loeschen: e.target.checked })
                  }
                  className="mt-0.5 h-4 w-4 shrink-0 accent-amber-400"
                />
                <span className="text-xs leading-relaxed text-slate-400">
                  Wenn alle Plätze belegt sind, die{" "}
                  <strong className="text-slate-300">älteste löschen</strong>.
                  <span className="mt-0.5 block text-slate-600">
                    Aus: Die Automatik setzt aus, sobald es voll ist.
                  </span>
                </span>
              </label>

              <label className="flex cursor-pointer items-start gap-2.5">
                <input
                  type="checkbox"
                  checked={Boolean(auto.mit_nachrichten)}
                  disabled={!premium || beschaeftigt}
                  onChange={(e) =>
                    autoSetzen({ mit_nachrichten: e.target.checked })
                  }
                  className="mt-0.5 h-4 w-4 shrink-0 accent-amber-400"
                />
                <span className="text-xs leading-relaxed text-slate-400">
                  Auch Nachrichten mitsichern.
                  <span className="mt-0.5 block text-slate-600">
                    Dauert deutlich länger und braucht mehr Platz.
                  </span>
                </span>
              </label>

              {auto.letzter_lauf > 0 && (
                <p className="text-xs text-slate-600">
                  Zuletzt: {zeitpunkt(auto.letzter_lauf)}
                </p>
              )}
              {auto.letzter_fehler && (
                <div className="flex gap-2 rounded-xl border border-amber-500/25 bg-amber-500/[0.05] p-3">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                  <p className="text-xs leading-relaxed text-amber-200/80">
                    Letzter Versuch: {auto.letzter_fehler}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Was nicht geht ──────────────────────────────────────── */}
      <div className="flex gap-3 rounded-3xl border border-slate-800 bg-[#0f0f13] p-4">
        <Shield className="mt-0.5 h-4 w-4 shrink-0 text-slate-600" />
        <p className="text-xs leading-relaxed text-slate-500">
          Mitglieder und ihre Rollenzuordnung sind nicht dabei: Discord
          erlaubt keinem Bot, jemanden wieder in einen Server zu holen.
          Nachrichten lassen sich nur als Neuposts wiederherstellen, nicht
          als Originale.
        </p>
      </div>
    </div>
  );
}
