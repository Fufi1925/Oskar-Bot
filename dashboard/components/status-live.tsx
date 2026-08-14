"use client";

/**
 * Die Status-Seite, live.
 *
 * ── Was sie beantwortet, in dieser Reihenfolge ──────────────────────
 *
 *   1. Läuft es gerade? — eine Zeile, groß, ohne Beiwerk.
 *   2. Wie war es zuletzt? — Balken je Zeitabschnitt.
 *   3. Wie schnell? — die Antwortzeit als Linie.
 *   4. Woher kommen die Zahlen? — am Ende, für die, die es wissen wollen.
 *
 * Die alte Seite hörte nach Punkt 1 auf und listete darunter vier
 * Häkchen. Wer wissen wollte, ob die Störung von heute Morgen vorbei
 * ist, fand nichts.
 *
 * ── Warum es sich selbst aktualisiert ───────────────────────────────
 *
 * Eine Statusseite liest man genau dann, wenn etwas nicht geht — und
 * dann bleibt sie offen. Ohne Selbstaktualisierung zeigt sie fünf
 * Minuten später noch immer „Störung", obwohl längst alles läuft.
 *
 * ── Zwei Regeln, die den Aufbau erklären ────────────────────────────
 *
 * **Ein grauer Balken ist keine gute Nachricht.** „Nicht gemessen"
 * heißt: der Wächter war selbst aus. Das grün zu zeichnen wäre eine
 * Behauptung ohne Messung.
 *
 * **Der Wächter darf nicht der Bot sein.** Diese Seite fragt den
 * unabhängigen Status-Dienst, nicht den Bot selbst. Ein Kranker, den
 * man fragt, ob er krank ist, antwortet entweder „mir geht's gut" oder
 * gar nicht.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  Wrench,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { LineChart } from "@/components/ui/line-chart";
import { UptimeBars, type Abschnitt } from "@/components/ui/uptime-bars";

/** Wie oft der Zustand neu geholt wird. Wie der Wächter selbst prüft. */
const INTERVALL_MS = 30_000;

const ZEITRAEUME: Array<[number, string]> = [
  [24, "24 Stunden"],
  [24 * 7, "7 Tage"],
  [24 * 30, "30 Tage"],
];

interface Zustand {
  state: string;
  since: number;
  maintenance: boolean;
  maintenance_note: string;
  brand: string;
  main: {
    reachable: boolean;
    bot_ready: boolean;
    dashboard: string;
    latency_ms: number | null;
    status_code: number | null;
    error: string | null;
    checked_at: number;
  };
  uptime?: {
    known: boolean;
    percent?: number;
    days?: number;
    outage_count?: number;
    complete?: boolean;
    last_outage_end?: number | null;
  };
  history_persistent?: boolean;
}

interface Verlauf {
  hours: number;
  slots: Abschnitt[];
  uptime?: Zustand["uptime"];
  errors?: { known: boolean; total?: number; restarts?: number };
  persistent?: boolean;
  keep_days?: number;
}

const KARTE = "rounded-2xl border border-slate-800 bg-[#131318]";

async function hole(pfad: string) {
  const antwort = await fetch(pfad, { cache: "no-store" });
  const daten = await antwort.json();
  if (!daten?.ok) return null;
  return daten.data;
}

function seit(unix: number) {
  if (!unix) return "";
  const sekunden = Math.max(0, Math.floor(Date.now() / 1000) - unix);
  const tage = Math.floor(sekunden / 86400);
  if (tage >= 1) return `seit ${tage} ${tage === 1 ? "Tag" : "Tagen"}`;
  const stunden = Math.floor(sekunden / 3600);
  if (stunden >= 1) return `seit ${stunden} ${stunden === 1 ? "Stunde" : "Stunden"}`;
  const minuten = Math.floor(sekunden / 60);
  if (minuten >= 1) return `seit ${minuten} Minuten`;
  return "gerade eben";
}

/**
 * Eine Prozentzahl auf Deutsch.
 *
 * `toFixed(2)` liefert immer einen Punkt: „99.62". Auf einer sonst
 * deutschen Seite liest sich das als Tippfehler -- und bei Zahlen ab
 * tausend ist der Punkt bei uns das Tausendertrennzeichen, also
 * schlimmer als unschoen. Im gerenderten Bild nachgemessen.
 */
function prozent(wert: number) {
  return wert.toLocaleString("de-DE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Die Beschriftung eines Abschnitts auf der X-Achse. */
function achsenText(start: number, stunden: number) {
  const d = new Date(start * 1000);
  if (stunden <= 24) {
    return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("de-DE", { day: "numeric", month: "short" });
}

export function StatusLive({ marke }: { marke: string }) {
  const [zustand, setZustand] = useState<Zustand | null>(null);
  const [verlauf, setVerlauf] = useState<Verlauf | null>(null);
  const [stunden, setStunden] = useState(24);
  const [laedt, setLaedt] = useState(true);
  const [verlaufLaedt, setVerlaufLaedt] = useState(true);
  const [erreichbar, setErreichbar] = useState(true);
  const [zuletzt, setZuletzt] = useState<number | null>(null);
  const [aktualisiert, setAktualisiert] = useState(false);

  // Damit die Anzeige „vor X Sekunden" mitläuft, auch wenn gerade
  // keine Antwort kommt.
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 10_000);
    return () => clearInterval(t);
  }, []);

  const ladeZustand = useCallback(async (manuell = false) => {
    if (manuell) setAktualisiert(true);
    try {
      const daten = await hole("/api/status");
      if (daten) {
        setZustand(daten);
        setErreichbar(true);
        setZuletzt(Date.now());
      } else {
        setErreichbar(false);
      }
    } catch {
      setErreichbar(false);
    } finally {
      setLaedt(false);
      if (manuell) setAktualisiert(false);
    }
  }, []);

  useEffect(() => {
    ladeZustand();
    const t = setInterval(() => ladeZustand(), INTERVALL_MS);
    return () => clearInterval(t);
  }, [ladeZustand]);

  // Der Verlauf hängt am Zeitraum, nicht am Takt: er ändert sich
  // höchstens im Rhythmus der Messungen, und ein paar hundert
  // Messpunkte alle 30 Sekunden neu zu laden wäre Verschwendung.
  const abgebrochen = useRef(false);
  useEffect(() => {
    abgebrochen.current = false;
    setVerlaufLaedt(true);
    hole(`/api/status?was=history&stunden=${stunden}`)
      .then((daten) => {
        if (!abgebrochen.current) setVerlauf(daten);
      })
      .catch(() => {
        if (!abgebrochen.current) setVerlauf(null);
      })
      .finally(() => {
        if (!abgebrochen.current) setVerlaufLaedt(false);
      });
    return () => {
      abgebrochen.current = true;
    };
  }, [stunden]);

  // ── Der Kopf ──────────────────────────────────────────────────

  const zustandsText = (() => {
    if (!erreichbar || !zustand) {
      return {
        titel: "Status nicht abrufbar",
        text:
          "Die Überwachung antwortet gerade nicht. Das heißt nicht " +
          "zwingend, dass der Bot ausgefallen ist — es kann auch der " +
          "Wächter selbst sein.",
        farbe: "text-slate-400",
        rahmen: "border-slate-800",
        flaeche: "bg-[#131318]",
        Icon: Clock,
      };
    }
    if (zustand.maintenance) {
      return {
        titel: "Geplante Wartung",
        text:
          "An dem Bot wird gerade gearbeitet. Kurze Ausfälle sind in " +
          "dieser Zeit normal.",
        farbe: "text-amber-300",
        rahmen: "border-amber-500/30",
        flaeche: "bg-amber-500/[0.06]",
        Icon: Wrench,
      };
    }
    if (zustand.state === "online") {
      return {
        titel: "Alle Systeme laufen",
        text: "Der Bot ist erreichbar und bereit.",
        farbe: "text-emerald-300",
        rahmen: "border-emerald-500/30",
        flaeche: "bg-emerald-500/[0.06]",
        Icon: CheckCircle2,
      };
    }
    if (zustand.state === "starting") {
      return {
        titel: "Startet gerade",
        text:
          "Der Bot antwortet, ist aber noch nicht vollständig bereit. " +
          "Nach einem Update dauert das ein bis zwei Minuten.",
        farbe: "text-amber-300",
        rahmen: "border-amber-500/30",
        flaeche: "bg-amber-500/[0.06]",
        Icon: AlertTriangle,
      };
    }
    return {
      titel: "Störung",
      text:
        "Der Bot ist von außen nicht erreichbar. Das kann ein Neustart, " +
        "ein fehlgeschlagenes Update oder eine Störung bei Discord sein.",
      farbe: "text-rose-300",
      rahmen: "border-rose-500/30",
      flaeche: "bg-rose-500/[0.06]",
      Icon: XCircle,
    };
  })();

  if (laedt) {
    return (
      <div className="flex min-h-[300px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-400 opacity-50" />
      </div>
    );
  }

  const haupt = zustand?.main;
  const uptime = verlauf?.uptime ?? zustand?.uptime;

  const zeilen: Array<{
    label: string;
    wert: string;
    ton: "gut" | "schlecht" | "warnung" | "unbekannt";
  }> = haupt
    ? [
        {
          label: "Erreichbar",
          wert: haupt.reachable
            ? `HTTP ${haupt.status_code ?? "?"}`
            : haupt.error || "keine Antwort",
          ton: haupt.reachable ? "gut" : "schlecht",
        },
        {
          label: "Antwortzeit",
          wert:
            haupt.reachable && haupt.latency_ms !== null
              ? `${haupt.latency_ms} ms`
              : "nicht geprüft",
          ton: !haupt.reachable
            ? "unbekannt"
            : (haupt.latency_ms ?? 0) < 2000
              ? "gut"
              : "warnung",
        },
        {
          label: "Discord-Verbindung",
          // Nicht rot, wenn nicht erreichbar: so weit sind wir gar
          // nicht gekommen, und Rot würde behaupten, wir hätten.
          wert: !haupt.reachable
            ? "nicht geprüft"
            : haupt.bot_ready
              ? "verbunden"
              : "noch nicht bereit",
          ton: !haupt.reachable ? "unbekannt" : haupt.bot_ready ? "gut" : "warnung",
        },
        {
          label: "Dashboard",
          wert: !haupt.reachable
            ? "nicht geprüft"
            : haupt.dashboard === "online"
              ? "erreichbar"
              : haupt.dashboard,
          ton: !haupt.reachable
            ? "unbekannt"
            : haupt.dashboard === "online"
              ? "gut"
              : "warnung",
        },
      ]
    : [];

  const punkte = (verlauf?.slots || []).map((s) => ({
    label: achsenText(s.start, verlauf?.hours ?? 24),
    // `null` heißt „nicht gemessen" — das Diagramm zeichnet dann eine
    // Lücke statt einer Linie auf null.
    wert: s.known && s.latency !== null ? Math.round(s.latency) : null,
  }));

  const hatMesswerte = punkte.some((p) => p.wert !== null);

  return (
    <div className="space-y-5">
      {/* ── 1 · Läuft es? ─────────────────────────────────────── */}
      <section
        className={cn(
          "rounded-2xl border p-6 sm:p-7",
          zustandsText.rahmen,
          zustandsText.flaeche,
        )}
      >
        <div className="flex flex-wrap items-start gap-4">
          <zustandsText.Icon
            className={cn("mt-0.5 h-7 w-7 shrink-0", zustandsText.farbe)}
          />
          <div className="min-w-0 flex-1">
            <h2 className={cn("text-[24px] font-bold leading-tight", zustandsText.farbe)}>
              {zustandsText.titel}
            </h2>
            <p className="mt-2 text-[14px] leading-relaxed text-slate-400">
              {zustandsText.text}
            </p>
            {zustand?.maintenance && zustand.maintenance_note && (
              <p className="mt-2 text-[13px] text-amber-200/80">
                Grund: {zustand.maintenance_note}
              </p>
            )}
            {zustand && !zustand.maintenance && zustand.since > 0 && (
              <p className="mt-2 text-[13px] text-slate-500">
                Unverändert {seit(zustand.since)}.
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={() => ladeZustand(true)}
            disabled={aktualisiert}
            className="flex shrink-0 items-center gap-2 rounded-xl border border-slate-800 bg-[#0e0e12] px-4 py-2.5 text-[13px] font-semibold text-slate-300 transition-colors hover:border-slate-700 hover:text-white disabled:opacity-40"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", aktualisiert && "animate-spin")} />
            Aktualisieren
          </button>
        </div>

        {/* Wann zuletzt geschaut wurde. Auf einer Seite, die offen
            bleibt, ist das die Angabe, die den Rest glaubwürdig macht. */}
        <p className="mt-4 border-t border-white/[0.06] pt-4 text-[12px] text-slate-500">
          {zuletzt
            ? `Zuletzt geprüft ${seit(Math.floor(zuletzt / 1000))} · aktualisiert sich alle 30 Sekunden`
            : "Wird geprüft …"}
        </p>
      </section>

      {/* ── 2 · Die Einzelheiten ──────────────────────────────── */}
      {zeilen.length > 0 && (
        <section className={cn(KARTE, "overflow-hidden")}>
          <div className="border-b border-slate-800 px-5 py-4">
            <h3 className="text-[16px] font-bold text-white">
              {zustand?.brand || marke}
            </h3>
            <p className="mt-0.5 text-[13px] text-slate-500">
              Vier Prüfungen, jede einzeln gemessen.
            </p>
          </div>
          {zeilen.map((z, i) => (
            <div
              key={z.label}
              className={cn(
                "flex flex-wrap items-center justify-between gap-3 px-5 py-3.5",
                i > 0 && "border-t border-slate-800",
              )}
            >
              <span className="flex items-center gap-3 text-[14px] text-slate-300">
                <span
                  className={cn(
                    "h-2.5 w-2.5 shrink-0 rounded-full",
                    z.ton === "gut"
                      ? "bg-emerald-400"
                      : z.ton === "schlecht"
                        ? "bg-rose-400"
                        : z.ton === "warnung"
                          ? "bg-amber-400"
                          : "bg-slate-600",
                  )}
                />
                {z.label}
              </span>
              <span className="text-[13px] tabular-nums text-slate-500">
                {z.wert}
              </span>
            </div>
          ))}
        </section>
      )}

      {/* ── 3 · Der Verlauf ───────────────────────────────────── */}
      <section className={cn(KARTE, "p-5 sm:p-6")}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="flex items-center gap-2 text-[16px] font-bold text-white">
              <Activity className="h-4 w-4 text-indigo-400" />
              Verlauf
            </h3>
            <p className="mt-1 text-[13px] text-slate-500">
              Ein Balken je Zeitabschnitt. Grau heißt: da wurde nicht
              gemessen — nicht, dass alles lief.
            </p>
          </div>

          <div className="flex gap-1 rounded-lg border border-slate-800 bg-[#0f0f13] p-1">
            {ZEITRAEUME.map(([wert, text]) => (
              <button
                key={wert}
                type="button"
                onClick={() => setStunden(wert)}
                aria-pressed={stunden === wert}
                className={cn(
                  "rounded-md px-2.5 py-1 text-[12px] transition-colors",
                  stunden === wert
                    ? "bg-white/[0.07] font-semibold text-white"
                    : "text-slate-500 hover:text-slate-300",
                )}
              >
                {text}
              </button>
            ))}
          </div>
        </div>

        {verlaufLaedt ? (
          <div className="mt-5 flex h-[120px] items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-indigo-400 opacity-50" />
          </div>
        ) : !verlauf || verlauf.slots.length === 0 ? (
          <div className="mt-5 rounded-xl border border-slate-800 bg-[#0f0f13] p-5">
            <p className="text-[14px] text-slate-300">
              Noch keine Aufzeichnung für diesen Zeitraum.
            </p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
              Der Verlauf beginnt, sobald die Überwachung läuft.
              {verlauf?.persistent === false && (
                <>
                  {" "}
                  Aktuell wird sie <b>nicht dauerhaft</b> gespeichert — nach
                  jedem Neustart fängt die Aufzeichnung von vorn an.
                </>
              )}
            </p>
          </div>
        ) : (
          <div className="mt-5 space-y-5">
            <UptimeBars abschnitte={verlauf.slots} />

            {uptime?.known && (
              <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-xl border border-slate-800 bg-[#0f0f13] px-4 py-3.5">
                <span className="text-[13px] text-slate-400">
                  <b className="text-[17px] font-bold text-white tabular-nums">
                    {prozent(uptime.percent ?? 0)} %
                  </b>{" "}
                  erreichbar
                  {uptime.complete
                    ? ` in ${uptime.days} Tagen`
                    : " seit Beginn der Aufzeichnung"}
                </span>
                <span className="text-[13px] text-slate-400">
                  <b className="text-[17px] font-bold text-white tabular-nums">
                    {uptime.outage_count ?? 0}
                  </b>{" "}
                  {uptime.outage_count === 1 ? "Störung" : "Störungen"}
                </span>
                {verlauf.errors?.known && (
                  <span className="text-[13px] text-slate-400">
                    <b className="text-[17px] font-bold text-white tabular-nums">
                      {verlauf.errors.total ?? 0}
                    </b>{" "}
                    Befehlsfehler
                  </span>
                )}
              </div>
            )}

            {/* Die Antwortzeit. Nur wenn es überhaupt Messwerte gibt --
                ein leeres Gitter beantwortet keine Frage. */}
            {hatMesswerte && (
              <div>
                {/* Die Einheit gehoert in die Ueberschrift.
                    An der Achse steht sie nicht, und dort liest sich
                    „4.813" -- der deutsche Tausenderpunkt fuer 4813 --
                    leicht als vier Komma acht. Im gerenderten Bild
                    aufgefallen. */}
                <p className="mb-2 text-[13px] font-semibold text-slate-300">
                  Antwortzeit <span className="text-slate-500">in Millisekunden</span>
                </p>
                <LineChart
                  daten={punkte}
                  name="Antwortzeit"
                  einheit=" ms"
                  farbe="#5865f2"
                  hoehe={170}
                />
              </div>
            )}

            {verlauf.persistent === false && (
              <p className="flex gap-2 rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-3.5 text-[13px] leading-relaxed text-amber-200/90">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                Die Aufzeichnung liegt nicht auf einem dauerhaften Speicher.
                Nach einem Neustart der Überwachung beginnt sie von vorn — die
                Zahlen oben decken dann nur die Zeit seitdem ab.
              </p>
            )}
          </div>
        )}
      </section>

      {/* ── 4 · Woher die Zahlen kommen ───────────────────────── */}
      <section className={cn(KARTE, "p-5 sm:p-6")}>
        <h3 className="text-[16px] font-bold text-white">
          Woher kommen diese Angaben?
        </h3>
        <div className="mt-3 space-y-3 text-[14px] leading-relaxed text-slate-400">
          <p>
            Ein zweiter, unabhängiger Dienst prüft alle 30 Sekunden von außen,
            ob der Bot antwortet — aus einem eigenen Container. Ein Wächter,
            der mit dem Überwachten zusammen abstürzt, meldet gar nichts.
          </p>
          <p>
            Eine einzelne fehlgeschlagene Prüfung gilt noch nicht als Störung.
            Erst nach drei Fehlversuchen in Folge — also gut anderthalb
            Minuten — steht hier &bdquo;Störung&ldquo;. Sonst würde jedes
            Update wie ein Absturz aussehen.
          </p>
          <p>
            Diese Seite fragt den Wächter, nicht den Bot. Einen Dienst zu
            fragen, ob er selbst läuft, ergibt nur zwei mögliche Antworten:
            &bdquo;ja&ldquo; oder Schweigen.
          </p>
        </div>
      </section>
    </div>
  );
}
