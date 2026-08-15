"use client";

/**
 * Die Cookie-Bestätigungen im Admin-Bereich.
 *
 * ── Wozu diese Liste da ist ─────────────────────────────────────────
 *
 * Art. 7 Abs. 1 DSGVO verlangt, dass sich eine Einwilligung nachweisen
 * lässt. Ein Häkchen, das nur im Browser des Besuchers steht, ist kein
 * Nachweis — es ist mit einem Rechtsklick gelöscht und mit einem
 * zweiten erfunden. Hier steht, was tatsächlich ankam.
 *
 * Genau genommen ist es kein Einwilligungs-, sondern ein
 * Kenntnisnahme-Nachweis: die Seite setzt ausschließlich technisch
 * notwendige Cookies, für die nach § 25 Abs. 2 TDDDG keine Einwilligung
 * nötig ist. Der Unterschied steht auch auf der Seite und nicht nur in
 * diesem Kommentar — sonst behauptet die Oberfläche mehr, als da ist.
 *
 * ── Warum zwei Wege zu löschen ──────────────────────────────────────
 *
 *   **Zeile löschen**   ein einzelner Eintrag, etwa nach Rückfrage.
 *   **Konto löschen**   alles zu einer Discord-ID.
 *
 * Der zweite ist der wichtigere: ein Löschverlangen nach Art. 17 DSGVO
 * nennt ein Konto, keine Browser-Kennung — die kennt niemand von sich
 * selbst. Ohne diesen Knopf müsste man die Zeile erst suchen, und bei
 * jemandem mit drei Browsern fände man zwei.
 *
 * ── Was hier bewusst NICHT steht ────────────────────────────────────
 *
 * Keine IP-Adresse und kein Browser-Kennzeichen. Beides wird gar nicht
 * erst gespeichert (`utils/cookie_consent.py`): die
 * Datenschutzerklärung sagt zu, dass keine IP-Adressen zu
 * Analysezwecken verarbeitet werden, und eine Spalte, die dieser Zusage
 * widerspricht, gehört auch dann nicht in die Datenbank, wenn sie
 * praktisch wäre.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Cookie,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  UserX,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LineChart } from "@/components/ui/line-chart";

interface ConsentRow {
  besucher_id: string;
  user_id: string;
  user_name: string;
  version: string;
  pfad: string;
  zuerst_at: number;
  zuletzt_at: number;
  anzahl: number;
  angemeldet: boolean;
}

interface Zahlen {
  gesamt: number;
  mit_konto: number;
  ohne_konto: number;
  heute: number;
  woche: number;
}

const KARTE = "rounded-3xl border border-slate-800 bg-[#131318]";

/** Datum und Uhrzeit — bei einem Nachweis zählt die Minute. */
function zeitpunkt(unix: number) {
  if (!unix) return "—";
  return new Date(unix * 1000).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Ein Tagesstempel als „12. Aug“ für die Achse. */
function tagKurz(unix: number) {
  return new Date(unix * 1000).toLocaleDateString("de-DE", {
    day: "numeric",
    month: "short",
  });
}

export function CookieConsentsPanel() {
  const [rows, setRows] = useState<ConsentRow[]>([]);
  const [zahlen, setZahlen] = useState<Zahlen | null>(null);
  const [verlauf, setVerlauf] = useState<Array<{ tag: number; anzahl: number }>>([]);
  const [tage, setTage] = useState(30);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [nurKonto, setNurKonto] = useState(false);

  const load = useCallback(async () => {
    try {
      // Beide Anfragen nebeneinander: nacheinander wäre die Seite
      // doppelt so lange leer, ohne dass eine auf die andere wartet.
      const [liste, kurve] = await Promise.all([
        api.cookieConsents(500),
        api.cookieConsentStats(tage),
      ]);
      setRows(liste?.consents || []);
      setZahlen(liste?.stats || null);
      setVerlauf(kurve?.verlauf || []);
    } catch (err: any) {
      toast.error(err?.message || "Die Bestätigungen ließen sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, [tage]);

  useEffect(() => {
    load();
  }, [load]);

  const sichtbar = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (nurKonto && !row.angemeldet) return false;
      if (!needle) return true;
      return [row.user_id, row.user_name, row.besucher_id, row.pfad]
        .filter(Boolean)
        .some((feld) => String(feld).toLowerCase().includes(needle));
    });
  }, [rows, query, nurKonto]);

  const zeileLoeschen = async (row: ConsentRow) => {
    if (
      !confirm(
        `Diesen Eintrag löschen?\n\n` +
          `${row.user_name || row.user_id || "Ohne Konto"} — ` +
          `bestätigt am ${zeitpunkt(row.zuerst_at)}.\n\n` +
          "Der Nachweis für diesen Browser ist danach weg. Das Fenster " +
          "erscheint dort trotzdem nicht wieder: das Cookie liegt im " +
          "Browser des Besuchers, nicht hier.",
      )
    ) {
      return;
    }
    setBusy(row.besucher_id);
    try {
      await api.cookieConsentDelete(row.besucher_id);
      toast.success("Der Eintrag wurde gelöscht.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBusy("");
    }
  };

  const kontoLoeschen = async (row: ConsentRow) => {
    const wieViele = rows.filter((r) => r.user_id === row.user_id).length;
    if (
      !confirm(
        `Alles zu ${row.user_name || row.user_id} löschen?\n\n` +
          `Betrifft ${wieViele} ${wieViele === 1 ? "Eintrag" : "Einträge"} — ` +
          "jeden Browser, mit dem dieses Konto angemeldet war.\n\n" +
          "Das ist der Weg für ein Löschverlangen nach Art. 17 DSGVO.",
      )
    ) {
      return;
    }
    setBusy(row.besucher_id);
    try {
      const antwort = await api.cookieConsentDeleteUser(row.user_id);
      toast.success(
        `${antwort?.deleted ?? 0} ${
          (antwort?.deleted ?? 0) === 1 ? "Eintrag" : "Einträge"
        } gelöscht.`,
      );
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return (
      <div className={cn(KARTE, "flex items-center justify-center p-16")}>
        <Loader2 className="h-5 w-5 animate-spin text-indigo-400 opacity-50" />
      </div>
    );
  }

  return (
    <section className="space-y-4">
      <div className={cn(KARTE, "flex flex-wrap items-center gap-4 px-5 py-4")}>
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-indigo-500/25 bg-indigo-500/10">
          <Cookie className="h-[18px] w-[18px] text-indigo-400" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[18px] font-bold tracking-tight text-white">
            Cookie-Hinweis
          </h2>
          <p className="mt-0.5 text-[13px] text-slate-500">
            Wer den Hinweis bestätigt hat — ein Eintrag pro Browser, nicht
            pro Klick.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="flex shrink-0 items-center gap-2 rounded-xl border border-slate-800 bg-[#0e0e12] px-4 py-2.5 text-sm font-semibold text-slate-300 transition-colors hover:border-slate-700 hover:text-white"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Aktualisieren
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Insgesamt", wert: zahlen?.gesamt ?? 0, farbe: "text-slate-300" },
          { label: "Mit Discord-Konto", wert: zahlen?.mit_konto ?? 0, farbe: "text-indigo-400" },
          { label: "Letzte 24 Stunden", wert: zahlen?.heute ?? 0, farbe: "text-emerald-400" },
          { label: "Letzte 7 Tage", wert: zahlen?.woche ?? 0, farbe: "text-slate-400" },
        ].map((k) => (
          <div key={k.label} className={cn(KARTE, "px-4 py-3.5")}>
            <p className={cn("text-[19px] font-bold leading-none tabular-nums", k.farbe)}>
              {k.wert.toLocaleString("de-DE")}
            </p>
            <p className="mt-1.5 text-[12px] text-slate-500">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Der Verlauf. Gezählt werden NEUE Bestätigungen, nicht Besuche
          -- sonst wanderte jeder Wiederkehrer täglich in die Kurve und
          das Bild zeigte Zulauf, wo dieselben Leute wiederkommen. */}
      <div className={cn(KARTE, "p-5")}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-[15px] font-bold text-white">
              Neue Bestätigungen pro Tag
            </h3>
            <p className="mt-1 text-[13px] text-slate-500">
              Jeder Browser zählt einmal, am Tag seiner ersten Bestätigung.
            </p>
          </div>
          <div className="flex gap-1 rounded-lg border border-slate-800 bg-[#0f0f13] p-1">
            {([
              [7, "7 Tage"],
              [30, "30 Tage"],
              [90, "90 Tage"],
            ] as Array<[number, string]>).map(([wert, label]) => (
              <button
                key={wert}
                type="button"
                onClick={() => setTage(wert)}
                aria-pressed={tage === wert}
                className={cn(
                  "rounded-md px-2.5 py-1 text-[12px] transition-colors",
                  tage === wert
                    ? "bg-white/[0.07] font-semibold text-white"
                    : "text-slate-500 hover:text-slate-300",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4">
          <LineChart
            daten={verlauf.map((punkt) => ({
              label: tagKurz(punkt.tag),
              wert: punkt.anzahl,
            }))}
            name="Bestätigungen"
            farbe="#5865f2"
            hoehe={180}
          />
        </div>
      </div>

      <div className={cn(KARTE, "flex flex-wrap items-center gap-3 p-4")}>
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Nach Name, Discord-ID oder Kennung suchen"
            className="w-full rounded-xl border border-slate-800 bg-[#0e0e12] py-2.5 pl-10 pr-4 text-sm text-white placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
          />
        </div>
        <button
          type="button"
          onClick={() => setNurKonto((v) => !v)}
          aria-pressed={nurKonto}
          className={cn(
            "rounded-xl border px-4 py-2.5 text-sm font-semibold transition-colors",
            nurKonto
              ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-300"
              : "border-slate-800 bg-[#0e0e12] text-slate-400 hover:border-slate-700 hover:text-white",
          )}
        >
          Nur mit Discord-Konto
        </button>
      </div>

      {sichtbar.length === 0 ? (
        <div className={cn(KARTE, "px-6 py-10 text-center")}>
          <Cookie className="mx-auto mb-3 h-7 w-7 text-slate-700" />
          <p className="text-[15px] text-slate-300">
            {rows.length === 0
              ? "Noch hat niemand den Hinweis bestätigt."
              : "Kein Eintrag passt zu dieser Suche."}
          </p>
          {rows.length === 0 && (
            <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">
              Einträge erscheinen hier, sobald jemand die Seite besucht und
              auf „Verstanden“ klickt.
            </p>
          )}
        </div>
      ) : (
        <div className={cn(KARTE, "overflow-hidden")}>
          <div className="divide-y divide-slate-800/70">
            {sichtbar.map((row) => (
              <div
                key={row.besucher_id}
                className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5"
              >
                <div className="min-w-[200px] flex-1">
                  <p className="truncate text-[14px] font-semibold text-white">
                    {row.user_name || (row.user_id ? row.user_id : "Ohne Konto")}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[11px] text-slate-600">
                    {row.user_id ? `${row.user_id} · ` : ""}
                    {row.besucher_id}
                  </p>
                </div>

                {/* Feste Breiten statt `min-w`. Mit `min-w` richtete
                    sich jede Zeile nach ihrem eigenen Inhalt: eine
                    Zeile mit „zuletzt …“ ist breiter und schob ihre
                    Nachbarspalte weiter nach rechts als die Zeile
                    darüber. Im Bild sah das aus wie eine schief
                    gesetzte Tabelle. `tabular-nums`, damit die Ziffern
                    untereinander stehen. */}
                <div className="w-[190px] shrink-0 text-[12px] tabular-nums text-slate-500">
                  <p>{zeitpunkt(row.zuerst_at)}</p>
                  {row.anzahl > 1 && (
                    <p className="mt-0.5 text-slate-600">
                      zuletzt {zeitpunkt(row.zuletzt_at)} · {row.anzahl}×
                    </p>
                  )}
                </div>

                <div className="w-[120px] shrink-0">
                  <p className="truncate text-[12px] text-slate-500">
                    {row.pfad || "/"}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-600">
                    Fassung {row.version || "—"}
                  </p>
                </div>

                {/* Auch die Knopfspalte hat eine feste Breite: den
                    „Konto“-Knopf gibt es nur bei Angemeldeten, und ohne
                    Platzhalter sprang „Zeile“ von Reihe zu Reihe. */}
                <div className="flex w-[190px] shrink-0 items-center justify-end gap-2">
                  {row.angemeldet ? (
                    <button
                      type="button"
                      onClick={() => kontoLoeschen(row)}
                      disabled={busy === row.besucher_id}
                      title="Alles zu diesem Discord-Konto löschen (Art. 17 DSGVO)"
                      className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-[#0e0e12] px-3 py-2 text-[12px] font-semibold text-slate-400 transition-colors hover:border-rose-500/30 hover:text-rose-300 disabled:opacity-40"
                    >
                      <UserX className="h-3.5 w-3.5" />
                      Konto
                    </button>
                  ) : (
                    <span aria-hidden="true" className="w-[92px]" />
                  )}
                  <button
                    type="button"
                    onClick={() => zeileLoeschen(row)}
                    disabled={busy === row.besucher_id}
                    title="Nur diesen Eintrag löschen"
                    className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-[#0e0e12] px-3 py-2 text-[12px] font-semibold text-slate-400 transition-colors hover:border-rose-500/30 hover:text-rose-300 disabled:opacity-40"
                  >
                    {busy === row.besucher_id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )}
                    Zeile
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className={cn(KARTE, "px-5 py-4")}>
        <p className="text-[13px] leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-400">
            Was hier nicht steht:
          </span>{" "}
          keine IP-Adresse und kein Browser-Kennzeichen — beides wird gar
          nicht erst gespeichert. Die Kennung ist eine Zufallszahl, die der
          Browser selbst erzeugt. Einträge werden nach 400 Tagen automatisch
          gelöscht.
        </p>
      </div>
    </section>
  );
}
