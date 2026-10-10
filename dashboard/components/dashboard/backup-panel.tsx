"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import { localizedConfirm } from "@/lib/i18n/browser-language";
import { WebsiteSelect } from "@/components/ui/website-select";

/** Server backups, automatic schedules, previews and restore confirmation. */

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Activity, AlertTriangle, ArrowRight, Check, ChevronDown, Clock, Crown,
  Database, Eye, Hash, Loader2, Lock, MessageSquare, Mic, Plus,
  RefreshCw, RotateCcw, Search, Settings, Shield, Timer, Trash2, Users, X,
} from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD = "cloudtix-workspace-card bg-[#131318] border border-slate-800 rounded-3xl";
const INPUT =
  "w-full cloudtix-workspace-field bg-[#0e0e12] border border-slate-800 rounded-xl px-3.5 py-2.5 " +
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
    return `${(bytes / 1024).toLocaleString(websiteLocale(), {
      maximumFractionDigits: 0,
    })} KB`;
  }
  return `${(bytes / 1024 / 1024).toLocaleString(websiteLocale(), {
    maximumFractionDigits: 1,
  })} MB`;
}

function zeitpunkt(sekunden: number): string {
  if (!sekunden) return "—";
  return new Date(sekunden * 1000).toLocaleString(websiteLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Was Gratis kann und was Premium kann.
 *
 * Steht hier als Daten, nicht als Fließtext: so lässt es sich als
 * Tabelle zeigen, und beide Spalten stehen zwangsläufig nebeneinander
 * statt in zwei Absätzen, die auseinanderlaufen.
 */
const VERGLEICH = [
  { was: "Sicherungen gleichzeitig", gratis: "1", premium: "10" },
  { was: "Selbst sichern", gratis: true, premium: true },
  { was: "Wiederherstellen", gratis: true, premium: true },
  { was: "Dashboard-Einstellungen", gratis: true, premium: true },
  { was: "Automatisch sichern", gratis: false, premium: "Ab 6 Stunden" },
  { was: "Nachrichten mitsichern", gratis: false, premium: "500 je Kanal" },
];

function JaNein({ wert }: { wert: string | boolean }) {
  useWebsiteLocale();
  if (wert === true) return <Check className="h-4 w-4 text-emerald-400" />;
  if (wert === false)
    return <X className="h-4 w-4 text-slate-700" aria-label="nicht enthalten" />;
  return <span className="text-sm text-slate-300">{wert}</span>;
}

/** Ein Kanalsymbol nach Art. */
function KanalIcon({ kind }: { kind: string }) {
  useWebsiteLocale();
  if (kind === "voice" || kind === "stage")
    return <Mic className="h-3 w-3 shrink-0 text-slate-600" />;
  return <Hash className="h-3 w-3 shrink-0 text-slate-600" />;
}

/**
 * Die Vorschau einer Sicherung.
 *
 * Lädt erst beim Aufklappen: eine Sicherung mit 99 Kanälen ist nichts,
 * was man für zehn Einträge auf Vorrat holt.
 */
function Vorschau({
  guildId,
  kennung,
}: {
  guildId: string;
  kennung: string;
}) {
  useWebsiteLocale();
  const [daten, setDaten] = useState<any>(null);
  const [fehler, setFehler] = useState("");

  useEffect(() => {
    let abgebrochen = false;
    (async () => {
      try {
        const antwort = await api.backupVorschau(guildId, kennung);
        if (!abgebrochen) setDaten(antwort);
      } catch (err: any) {
        if (!abgebrochen)
          setFehler(err?.message || "Die Vorschau ließ sich nicht laden.");
      }
    })();
    return () => {
      abgebrochen = true;
    };
  }, [guildId, kennung]);

  if (fehler) {
    return (
      <div className="border-t border-slate-800 cloudtix-workspace-card bg-[#0f0f13] px-5 py-4">
        <p className="text-xs text-red-300">{fehler}</p>
      </div>
    );
  }

  if (!daten) {
    return (
      <div className="flex items-center gap-2 border-t border-slate-800 cloudtix-workspace-card bg-[#0f0f13] px-5 py-4 text-xs text-slate-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Wird geladen …
      </div>
    );
  }

  return (
    <div className="space-y-4 border-t border-slate-800 cloudtix-workspace-card bg-[#0f0f13] px-5 py-4">
      {daten.guild_name && (
        <p className="text-xs text-slate-500">
          Server hieß damals:{" "}
          <span className="font-medium text-slate-300">
            {daten.guild_name}
          </span>
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── Kanäle ────────────────────────────────────────────── */}
        <div>
          <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
            Kanäle
          </div>
          <div className="mt-2 max-h-64 space-y-2.5 overflow-y-auto pr-1">
            {daten.ohne_kategorie?.length > 0 && (
              <div>
                <div className="text-[11px] font-semibold text-slate-500">
                  Ohne Kategorie
                </div>
                <div className="mt-1 space-y-0.5">
                  {daten.ohne_kategorie.map((k: any) => (
                    <div
                      key={k.name}
                      className="flex items-center gap-1.5 text-xs text-slate-400"
                    >
                      <KanalIcon kind={k.kind} />
                      <span className="truncate">{k.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {daten.kategorien?.map((kat: any) => (
              <div key={kat.name}>
                <div className="truncate text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  {kat.name}
                </div>
                {kat.channels.length === 0 ? (
                  <div className="mt-1 text-xs italic text-slate-700">
                    leer
                  </div>
                ) : (
                  <div className="mt-1 space-y-0.5">
                    {kat.channels.map((k: any) => (
                      <div
                        key={k.name}
                        className="flex items-center gap-1.5 text-xs text-slate-400"
                      >
                        <KanalIcon kind={k.kind} />
                        <span className="truncate">{k.name}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {!daten.kategorien?.length && !daten.ohne_kategorie?.length && (
              <p className="text-xs italic text-slate-700">Keine Kanäle.</p>
            )}
          </div>
        </div>

        {/* ── Rollen ────────────────────────────────────────────── */}
        <div>
          <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
            Rollen
          </div>
          <div className="mt-2 flex max-h-64 flex-wrap gap-1.5 overflow-y-auto pr-1">
            {daten.rollen?.length ? (
              daten.rollen.map((r: any) => (
                <span
                  key={r.name}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 cloudtix-workspace-card bg-[#131318] px-2 py-1 text-xs"
                  title={`${r.rechte} Rechte`}
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: r.colour || "#4b5563" }}
                  />
                  <span className="max-w-[140px] truncate text-slate-300">
                    {r.name}
                  </span>
                </span>
              ))
            ) : (
              <p className="text-xs italic text-slate-700">Keine Rollen.</p>
            )}
          </div>
        </div>
      </div>

      {/* ── Einstellungen ───────────────────────────────────────── */}
      <div>
        <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
          Dashboard-Einstellungen
        </div>
        {daten.einstellungen?.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {daten.einstellungen.map((e: any) => (
              <span
                key={e.key}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 cloudtix-workspace-card bg-[#131318] px-2 py-1 text-xs text-slate-300"
              >
                <Settings className="h-3 w-3 text-slate-600" />
                {e.label}
                <span className="text-slate-600">{e.zeilen}</span>
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-1 text-xs italic text-slate-700">
            Keine Einstellungen gesichert.
          </p>
        )}
      </div>

      {/* ── Nachrichten ─────────────────────────────────────────── */}
      {daten.nachrichten_kanaele?.length > 0 && (
        <div>
          <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
            Nachrichten
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {daten.nachrichten_kanaele.slice(0, 12).map((n: any) => (
              <span
                key={n.kanal}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 cloudtix-workspace-card bg-[#131318] px-2 py-1 text-xs text-slate-300"
              >
                <Hash className="h-3 w-3 text-slate-600" />
                {n.kanal}
                <span className="text-amber-400/70">
                  {n.anzahl.toLocaleString(websiteLocale())}
                </span>
              </span>
            ))}
            {daten.nachrichten_kanaele.length > 12 && (
              <span className="inline-flex items-center rounded-lg px-2 py-1 text-xs text-slate-600">
                +{daten.nachrichten_kanaele.length - 12} weitere
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
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
  useWebsiteLocale();
  const [allesLoeschen, setAllesLoeschen] = useState(false);
  const [mitEinstellungen, setMitEinstellungen] = useState(true);
  const [mitNachrichten, setMitNachrichten] = useState(false);

  const hatNachrichten = sicherung.nachrichten > 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="wiederherstellen-titel"
      className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm"
    >
      <div className="my-auto w-full max-w-lg overflow-hidden rounded-3xl border border-slate-700 cloudtix-workspace-card bg-[#131318] shadow-2xl">
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
                : "border-slate-800 cloudtix-workspace-card bg-[#0f0f13] hover:bg-white/[0.02]"
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
                : "border-slate-800 cloudtix-workspace-card bg-[#0f0f13] hover:bg-white/[0.02]"
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
                  : "border-slate-800 cloudtix-workspace-card bg-[#0f0f13] hover:bg-white/[0.02]",
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
                  {sicherung.nachrichten.toLocaleString(websiteLocale())} Nachrichten.
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
            className="inline-flex flex-1 items-center justify-center rounded-xl border border-slate-800 cloudtix-workspace-card bg-[#0f0f13] px-4 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-white/[0.04]"
          >
            Abbrechen
          </button>
        </div>
      </div>
    </div>
  );
}

export function BackupPanel({ guildId }: { guildId: string }) {
  useWebsiteLocale();
  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);
  const [gewaehlt, setGewaehlt] = useState<Sicherung | null>(null);
  const [offen, setOffen] = useState<string | null>(null);
  const [mitNachrichten, setMitNachrichten] = useState(false);
  const [tab, setTab] = useState<"library" | "auto" | "scope">("library");
  const [query, setQuery] = useState("");
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
  const maxPremium = Number(daten?.limits?.premium ?? 10);

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
    if (!localizedConfirm(`${s.kennung} endgültig löschen?`)) return;
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

  if (!daten) return <section className="cloudtix-settings-card text-center"><Database className="mx-auto h-8 w-8 text-slate-500" /><h3 className="mt-4 text-lg">Sicherungen nicht erreichbar</h3><p className="mt-2 text-sm text-slate-400">Die Sicherungen konnten nicht geladen werden.</p><button onClick={() => void laden()} className="cloudtix-workspace-action mt-5">Erneut laden</button></section>;
  const bytes = sicherungen.reduce((sum, item) => sum + (item.groesse || 0), 0);
  const newest = Math.max(0, ...sicherungen.map(item => item.erstellt_at));
  const shown = sicherungen.filter(item => `${item.kennung} ${item.notiz || ""}`.toLowerCase().includes(query.trim().toLowerCase()));

  return <div className="cloudtix-settings-page">
    {gewaehlt && <WiederherstellenFenster sicherung={gewaehlt} premium={premium} onAbbruch={() => setGewaehlt(null)} onStart={wiederherstellen} />}
    <header className="cloudtix-settings-heading"><div><p className="cloudtix-workspace-eyebrow">DATEN & SICHERHEIT</p><h1>Server sichern.</h1><p>Bewahre deine Einrichtung auf und stelle einen früheren Stand wieder her.</p></div><span className="cloudtix-settings-badge"><Database size={13} />{premium ? "Premium-Backups" : "Gratis-Backup"}</span></header>
    <section className="cloudtix-settings-metrics" aria-label="Backup-Übersicht">
      <div><Database size={17} /><span>Gespeicherte Sicherungen</span><strong>{sicherungen.length}<small> / {grenze}</small></strong></div>
      <div><Settings size={17} /><span>Gesicherte Daten</span><strong>{groesse(bytes)}</strong></div>
      <div><Clock size={17} /><span>Letzte Sicherung</span><strong className="is-date">{newest ? zeitpunkt(newest) : "Noch keine"}</strong></div>
    </section>
    <nav className="cloudtix-settings-tabs" aria-label="Backup-Bereiche">{([["library", "Sicherungen", Database], ["auto", "Automatik", Timer], ["scope", "Sicherungsumfang", Shield]] as const).map(([key, label, Icon]) => <button key={key} type="button" aria-pressed={tab === key} onClick={() => setTab(key)}><Icon size={15} />{label}</button>)}</nav>
    {laeuft && <div role="status" className="cloudtix-settings-running"><Loader2 size={18} className="animate-spin" /><div><strong>{lauf.art === "wiederherstellen" ? "Wiederherstellung läuft" : "Sicherung wird erstellt"}</strong><p>{lauf.schritt || "Wird vorbereitet …"}</p></div></div>}

    {tab === "library" && <>
      <div className="cloudtix-settings-grid">
        <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Plus size={18} /></span><div><h2>Neue Sicherung</h2><p>Speichere den aktuellen Stand deines Servers.</p></div></div>
          <div className="cloudtix-settings-included">{[[Hash, "Kanäle"], [Users, "Rollen"], [Settings, "Einstellungen"]].map(([Icon, label]: any) => <span key={label}><Icon size={14} />{label}<Check size={12} /></span>)}</div>
          {premium && <label className="cloudtix-settings-check"><input type="checkbox" checked={mitNachrichten} disabled={beschaeftigt || laeuft} onChange={event => setMitNachrichten(event.target.checked)} /><span><strong>Nachrichten einschließen</strong><small>Bis zu {(daten?.limits?.nachrichten ?? 500).toLocaleString(websiteLocale())} Nachrichten je Kanal. Die Sicherung dauert dadurch länger.</small></span></label>}
          {voll && <p className="cloudtix-settings-warning">Alle {grenze} Plätze sind belegt. Lösche eine vorhandene Sicherung, um einen Platz freizugeben.</p>}
          <button onClick={erstellen} disabled={beschaeftigt || laeuft || voll} className="cloudtix-workspace-action mt-5 w-full disabled:cursor-not-allowed disabled:opacity-40">{beschaeftigt || laeuft ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}Backup erstellen</button>
        </section>
        <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Shield size={18} /></span><div><h2>Deine Einrichtung bleibt greifbar.</h2><p>Prüfe den Inhalt, bevor du einen Stand wiederherstellst.</p></div></div><ol className="cloudtix-settings-steps"><li><b>01</b><div><strong>Stand sichern</strong><p>Kanäle, Rollen, Berechtigungen und Dashboard-Einstellungen aufbewahren.</p></div></li><li><b>02</b><div><strong>Inhalt ansehen</strong><p>Die Vorschau zeigt dir, was in einer Sicherung enthalten ist.</p></div></li><li><b>03</b><div><strong>Gezielt wiederherstellen</strong><p>Wähle deine Optionen und bestätige die Wiederherstellung.</p></div></li></ol></section>
      </div>
      <section className="cloudtix-settings-card"><div className="cloudtix-settings-list-heading"><div><h2>Deine Sicherungen <span>{sicherungen.length}</span></h2><p>Gespeicherte Stände dieses Servers.</p></div><button type="button" onClick={() => void laden()} className="cloudtix-settings-icon-button" aria-label="Sicherungen neu laden"><RefreshCw size={16} /></button></div>
        {sicherungen.length > 0 && <label className="cloudtix-settings-search"><Search size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Kennung oder Notiz suchen …" aria-label="Sicherungen suchen" /></label>}
        <div className="cloudtix-backup-list">{shown.map(item => {
          const open = offen === item.kennung;
          return <article key={item.kennung} className="cloudtix-backup-entry"><div className="cloudtix-backup-entry-heading"><span className="cloudtix-backup-entry-icon"><Database size={20} /></span><div><h3>{item.notiz || item.kennung}</h3><p>{zeitpunkt(item.erstellt_at)}{item.notiz ? ` · ${item.kennung}` : ""}</p></div><span className="cloudtix-settings-badge">{item.quelle === "auto" ? "Automatisch" : "Manuell"}</span></div><div className="cloudtix-backup-entry-facts"><span><Hash size={13} />{item.kanaele} Kanäle</span><span><Users size={13} />{item.rollen} Rollen</span><span>{groesse(item.groesse)}</span>{item.mit_nachrichten && <span><MessageSquare size={13} />{item.nachrichten.toLocaleString(websiteLocale())} Nachrichten</span>}</div><div className="cloudtix-backup-entry-actions"><button type="button" onClick={() => setOffen(open ? null : item.kennung)} aria-expanded={open} className="cloudtix-workspace-action is-secondary"><Eye size={14} />Vorschau<ChevronDown size={12} className={open ? "rotate-180" : ""} /></button><button type="button" onClick={() => setGewaehlt(item)} disabled={beschaeftigt || laeuft} className="cloudtix-workspace-action is-secondary disabled:opacity-40"><RotateCcw size={14} />Wiederherstellen</button><button type="button" onClick={() => void loeschen(item)} disabled={beschaeftigt || laeuft} className="cloudtix-settings-icon-button is-danger" aria-label={`Sicherung ${item.kennung} löschen`}><Trash2 size={15} /></button></div>{open && <Vorschau guildId={guildId} kennung={item.kennung} />}</article>;
        })}{!shown.length && <div className="cloudtix-settings-empty"><Database size={28} /><h3>{sicherungen.length ? "Keine passende Sicherung" : "Dein erster Stand wartet."}</h3><p>{sicherungen.length ? "Versuche eine andere Kennung oder Notiz." : "Erstelle oben dein erstes Backup, um die Einrichtung aufzubewahren."}</p></div>}</div>
      </section>
    </>}

    {tab === "auto" && (premium ? <div className="cloudtix-settings-grid">
      <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Timer size={18} /></span><div><h2>Automatisch sichern</h2><p>Ein regelmäßiger Stand, ohne jedes Mal selbst daran zu denken.</p></div></div><label className="cloudtix-settings-check"><input type="checkbox" checked={Boolean(auto.aktiv)} disabled={beschaeftigt || laeuft} onChange={event => void autoSetzen({ aktiv: event.target.checked })} /><span><strong>Automatik aktivieren</strong><small>Änderungen werden direkt gespeichert.</small></span></label>{auto.aktiv && <div className="mt-5 space-y-5"><label className="cloudtix-settings-field-label">Zeitplan<WebsiteSelect value={String(auto.stunden ?? 24)} disabled={beschaeftigt || laeuft} onChange={event => void autoSetzen({ stunden: Number(event.target.value) })} className={cn(INPUT, "mt-2")}><option value="6">Alle 6 Stunden</option><option value="12">Alle 12 Stunden</option><option value="24">Täglich</option><option value="72">Alle 3 Tage</option><option value="168">Wöchentlich</option><option value="720">Monatlich</option></WebsiteSelect></label><label className="cloudtix-settings-check"><input type="checkbox" checked={Boolean(auto.alte_loeschen)} disabled={beschaeftigt || laeuft} onChange={event => void autoSetzen({ alte_loeschen: event.target.checked })} /><span><strong>Ältesten Stand ersetzen</strong><small>Wenn alle Plätze belegt sind, wird die älteste Sicherung gelöscht. Ohne diese Option pausiert die Automatik.</small></span></label><label className="cloudtix-settings-check"><input type="checkbox" checked={Boolean(auto.mit_nachrichten)} disabled={beschaeftigt || laeuft} onChange={event => void autoSetzen({ mit_nachrichten: event.target.checked })} /><span><strong>Nachrichten mitsichern</strong><small>Benötigt mehr Zeit und Speicherplatz.</small></span></label></div>}</section>
      <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Activity size={18} /></span><div><h2>Letzter Lauf</h2><p>Der aktuelle Stand deiner Automatik.</p></div></div><dl className="cloudtix-settings-details"><div><dt>Status</dt><dd>{auto.aktiv ? "Aktiviert" : "Ausgeschaltet"}</dd></div><div><dt>Zuletzt gesichert</dt><dd>{zeitpunkt(auto.letzter_lauf)}</dd></div><div><dt>Belegte Plätze</dt><dd>{sicherungen.length} von {grenze}</dd></div></dl>{auto.letzter_fehler && <p className="cloudtix-settings-warning">Letzter Versuch: {auto.letzter_fehler}</p>}</section>
    </div> : <section className="cloudtix-settings-card cloudtix-settings-upgrade"><Crown size={30} /><p className="cloudtix-workspace-eyebrow">CLOUDTIX PREMIUM</p><h2>Dein Server. Regelmäßig gesichert.</h2><p>Mit Premium erhältst du automatische Backups, bis zu {maxPremium} gespeicherte Stände und Sicherungen mit Nachrichten.</p><Link href={`/dashboard/guild/${guildId}/premium`} className="cloudtix-workspace-action">Server-Premium öffnen<ArrowRight size={15} /></Link></section>)}

    {tab === "scope" && <div className="cloudtix-settings-grid"><section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Settings size={18} /></span><div><h2>Was gesichert wird</h2><p>Die Einrichtung, die deine Community zusammenhält.</p></div></div><div className="cloudtix-settings-feature-list"><div><Hash size={18} /><span><strong>Serverstruktur</strong><small>Kategorien, Kanäle und ihre Berechtigungen.</small></span></div><div><Users size={18} /><span><strong>Rollen</strong><small>Rollen und deren Rechte.</small></span></div><div><Settings size={18} /><span><strong>Dashboard-Einstellungen</strong><small>Die gespeicherte Konfiguration deiner Module.</small></span></div><div><MessageSquare size={18} /><span><strong>Nachrichten mit Premium</strong><small>Optional bis zu {(daten?.limits?.nachrichten ?? 500).toLocaleString(websiteLocale())} Nachrichten je Kanal.</small></span></div></div><p className="cloudtix-settings-warning">Mitglieder und ihre Rollenzuordnung sind nicht enthalten. Nachrichten werden als neue Beiträge wiederhergestellt, nicht als Originale.</p></section><section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Crown size={18} /></span><div><h2>Gratis & Premium</h2><p>Der passende Umfang für deinen Server.</p></div></div><div className="cloudtix-backup-comparison"><div><strong>Funktion</strong><strong>Gratis</strong><strong>Premium</strong></div>{VERGLEICH.map(row => <div key={row.was}><span>{row.was}</span><JaNein wert={row.gratis} /><JaNein wert={row.premium} /></div>)}</div>{!premium && <Link href="/dashboard/premium" className="cloudtix-workspace-action mt-5 w-full">Premium ansehen<ArrowRight size={15} /></Link>}</section></div>}
  </div>;
}
