"use client";

/**
 * Backup — Sicherungen dieses Servers.
 *
 * ── Was am Vorgänger falsch war ─────────────────────────────────────
 *
 * Die Premium-Sperre lag als `absolute inset-0` über der Automatik-
 * Karte. Ohne Premium ist diese Karte aber kurz (Überschrift, ein
 * Satz, ein Schalter) und die Sperr-Box darin höher — sie stand oben
 * und unten über den Kartenrand hinaus und überlappte die Karte
 * darunter. Im Screenshot gut zu sehen.
 *
 * Zwei Fehler auf einmal: erstens ein Overlay über etwas, das ohnehin
 * niemand bedienen darf, zweitens eine feste Höhe, die von der
 * Textmenge abhängt.
 *
 * ── Wie es jetzt gelöst ist ─────────────────────────────────────────
 *
 * Kein Overlay mehr. Ohne Premium wird die Automatik-Karte gar nicht
 * erst als bedienbare Karte gerendert, sondern als **Angebot**: eine
 * eigene Karte, die sagt, was es gäbe. Nichts liegt über etwas
 * anderem, also kann auch nichts überstehen.
 *
 * ── Trennung Gratis / Premium ───────────────────────────────────────
 *
 * Ausdrückliche Vorgabe: niemand ohne Premium soll denken, er könne
 * die Premium-Sachen benutzen. Deshalb:
 *
 *   * Ganz oben steht in einer Zeile, welchen Stand man hat.
 *   * Was mit Premium ginge, steht in einem eigenen Block mit einer
 *     Gegenüberstellung — nicht als gesperrter Schalter dazwischen.
 *   * Gesperrte Bedienelemente werden gar nicht erst gezeigt. Ein
 *     ausgegrauter Schalter lädt zum Klicken ein und tut dann nichts.
 *
 * ── Die Vorschau ────────────────────────────────────────────────────
 *
 * Wiederherstellen lässt sich nicht rückgängig machen. Wer nur eine
 * Kennung und ein Datum sieht, weiß nicht, ob er die richtige
 * erwischt. Deshalb lässt sich jede Sicherung aufklappen: Kategorien
 * mit ihren Kanälen, Rollen, Einstellungen, Nachrichten je Kanal.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, ArrowRight, Check, ChevronDown, Clock, Crown,
  Database, Eye, Hash, Loader2, Lock, MessageSquare, Mic, Plus,
  RefreshCw, RotateCcw, Settings, Shield, Timer, Trash2, Users, X,
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
  if (wert === true) return <Check className="h-4 w-4 text-emerald-400" />;
  if (wert === false)
    return <X className="h-4 w-4 text-slate-700" aria-label="nicht enthalten" />;
  return <span className="text-sm text-slate-300">{wert}</span>;
}

/** Ein Kanalsymbol nach Art. */
function KanalIcon({ kind }: { kind: string }) {
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
      <div className="border-t border-slate-800 bg-[#0f0f13] px-5 py-4">
        <p className="text-xs text-red-300">{fehler}</p>
      </div>
    );
  }

  if (!daten) {
    return (
      <div className="flex items-center gap-2 border-t border-slate-800 bg-[#0f0f13] px-5 py-4 text-xs text-slate-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Wird geladen …
      </div>
    );
  }

  return (
    <div className="space-y-4 border-t border-slate-800 bg-[#0f0f13] px-5 py-4">
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
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-[#131318] px-2 py-1 text-xs"
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
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-[#131318] px-2 py-1 text-xs text-slate-300"
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
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-[#131318] px-2 py-1 text-xs text-slate-300"
              >
                <Hash className="h-3 w-3 text-slate-600" />
                {n.kanal}
                <span className="text-amber-400/70">
                  {n.anzahl.toLocaleString("de-DE")}
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
      <div className="my-auto w-full max-w-lg overflow-hidden rounded-3xl border border-slate-700 bg-[#131318] shadow-2xl">
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
  const [offen, setOffen] = useState<string | null>(null);
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

      {/* ── Welchen Stand habe ich? ─────────────────────────────── */}
      {/*
          Ganz oben und in einer Zeile. Ohne diese Zeile rät man aus
          gesperrten Schaltern zusammen, was man hat — und das ist
          genau die Verwirrung, die weg soll.
      */}
      <div
        className={cn(
          "flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border px-4 py-3",
          premium
            ? "border-amber-400/30 bg-amber-400/[0.05]"
            : "border-slate-800 bg-[#0f0f13]"
        )}
      >
        {premium ? (
          <>
            <Crown className="h-4 w-4 shrink-0 text-amber-400" />
            <span className="text-sm font-bold text-amber-300">
              Premium aktiv
            </span>
            <span className="text-sm text-slate-400">
              Bis zu {maxPremium} Sicherungen, Automatik und Nachrichten.
            </span>
          </>
        ) : (
          <>
            <Database className="h-4 w-4 shrink-0 text-slate-500" />
            <span className="text-sm font-bold text-white">Gratis-Version</span>
            <span className="text-sm text-slate-400">
              Eine Sicherung, von Hand erstellt. Alles Weitere gibt es mit
              Premium.
            </span>
          </>
        )}
      </div>

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

            <div className="mt-2">
              <span
                className={cn(
                  "rounded-lg px-2 py-1 text-xs font-bold",
                  voll
                    ? "bg-amber-400/10 text-amber-300"
                    : "bg-[#0f0f13] text-slate-400"
                )}
              >
                {sicherungen.length} von {grenze} belegt
              </span>
            </div>

            {/* Nachrichten: nur mit Premium, und dann als echte Wahl.
                Ohne Premium steht der Schalter gar nicht erst da —
                ein ausgegrautes Kästchen lädt zum Klicken ein und tut
                dann nichts. */}
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
              : `Der eine Platz ist belegt. Lösche die vorhandene Sicherung — oder hol dir Premium für bis zu ${maxPremium}.`}
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
          sicherungen.map((s, i) => {
            const auf = offen === s.kennung;
            return (
              <div
                key={s.kennung}
                className={cn(i > 0 && "border-t border-slate-800")}
              >
                <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
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

                  <div className="flex shrink-0 flex-wrap gap-2">
                    <button
                      onClick={() => setOffen(auf ? null : s.kennung)}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 bg-[#0f0f13] px-3 py-2 text-xs font-bold text-slate-300 transition hover:bg-white/[0.04]"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Vorschau
                      <ChevronDown
                        className={cn(
                          "h-3 w-3 transition-transform",
                          auf && "rotate-180"
                        )}
                      />
                    </button>
                    <button
                      onClick={() => setGewaehlt(s)}
                      disabled={beschaeftigt || laeuft}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 bg-[#0f0f13] px-3 py-2 text-xs font-bold text-slate-200 transition hover:bg-white/[0.04] disabled:opacity-40"
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

                {auf && <Vorschau guildId={guildId} kennung={s.kennung} />}
              </div>
            );
          })
        )}
      </div>

      {/* ── Automatik ───────────────────────────────────────────────
          MIT Premium: eine ganz normale Karte mit Schaltern.
          OHNE Premium: gar keine Karte, sondern das Angebot weiter
          unten. Kein Overlay über einer kurzen Karte — genau das ist
          im Screenshot übergelaufen.
      */}
      {premium && (
        <div className={cn(CARD, "p-5 sm:p-6")}>
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
              disabled={beschaeftigt}
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
                  disabled={beschaeftigt}
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
                  disabled={beschaeftigt}
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
                  disabled={beschaeftigt}
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
      )}

      {/* ── Ohne Premium: was es gäbe ───────────────────────────────
          Eine eigene Karte, kein Overlay. Sie steht am Ende, weil sie
          ein Angebot ist und keine Bedienung — und weil dort niemand
          versehentlich hineinklickt.
      */}
      {!premium && (
        <div className="overflow-hidden rounded-3xl border border-amber-400/30 bg-gradient-to-br from-amber-400/[0.08] to-transparent">
          <div className="flex items-start gap-3 border-b border-amber-400/15 px-5 py-4">
            <div className="shrink-0 rounded-2xl bg-amber-400/15 p-2.5">
              <Crown className="h-5 w-5 text-amber-400" />
            </div>
            <div className="min-w-0">
              <h3 className="font-bold text-amber-300">Mit Premium</h3>
              <p className="mt-0.5 text-sm leading-relaxed text-slate-400">
                Alles hier oben funktioniert auch ohne. Das hier kommt
                dazu.
              </p>
            </div>
          </div>

          {/* Die Gegenüberstellung. Zwei Spalten nebeneinander statt
              zweier Absätze — so sieht man den Unterschied, statt ihn
              sich zusammenzureimen. */}
          <div className="px-5 py-4">
            <div className="overflow-hidden rounded-2xl border border-slate-800">
              <div className="grid grid-cols-[1.4fr_1fr_1fr] border-b border-slate-800 bg-[#0f0f13]">
                <div className="px-3 py-2 text-[10px] font-black uppercase tracking-widest text-slate-600">
                  Funktion
                </div>
                <div className="px-3 py-2 text-[10px] font-black uppercase tracking-widest text-slate-600">
                  Gratis
                </div>
                <div className="px-3 py-2 text-[10px] font-black uppercase tracking-widest text-amber-400">
                  Premium
                </div>
              </div>

              {VERGLEICH.map((z, i) => (
                <div
                  key={z.was}
                  className={cn(
                    "grid grid-cols-[1.4fr_1fr_1fr] items-center bg-[#131318]",
                    i > 0 && "border-t border-slate-800"
                  )}
                >
                  <div className="px-3 py-2.5 text-xs text-slate-300">
                    {z.was}
                  </div>
                  <div className="px-3 py-2.5">
                    <JaNein wert={z.gratis} />
                  </div>
                  <div className="px-3 py-2.5">
                    <JaNein wert={z.premium} />
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <Link
                href="/dashboard/premium/beta"
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl bg-amber-400 px-4 py-2.5 text-sm font-bold text-black transition hover:brightness-110"
              >
                Premium holen
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/premium"
                className="inline-flex flex-1 items-center justify-center rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-white/[0.04]"
              >
                Was Premium sonst kann
              </Link>
            </div>
          </div>
        </div>
      )}

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
