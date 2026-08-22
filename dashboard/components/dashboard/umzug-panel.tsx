"use client";

/**
 * Kontowechsel: alles mitnehmen, anderswo wieder einspielen.
 *
 * Warum es das neben der vorhandenen Sicherung gibt
 * -------------------------------------------------
 * „Alles herunterladen" darunter schreibt Tabellenzeilen in eine
 * JSON-Datei. Das laesst sich nur zurueckspielen, wenn Datenbank und
 * Tabelle auf der Gegenseite schon existieren. Auf einem frischen
 * Konto ist das nicht der Fall -- nachgemessen in
 * repro/bug_umzug_leer.py:
 *
 *     exportiert:  4 Zeilen
 *     angekommen:  0 Zeilen
 *     Meldung:     kein Fehler
 *
 * Hier wandern die Dateien selbst ins Archiv. Damit sind auch die
 * Dinge dabei, die zeilenweise nie erfasst wurden: offene Tickets,
 * Panel-Nachrichten und der Schluessel db/template_secret.key.
 */

import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  FileArchive,
  HardDriveDownload,
  Loader2,
  PackageOpen,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

interface DateiEintrag {
  pfad: string;
  bytes: number;
  ist_datenbank?: boolean;
  tabellen?: number;
  zeilen?: number;
  ueberschreibt?: boolean;
}

interface Uebersicht {
  dateien: DateiEintrag[];
  datei_anzahl: number;
  bytes_gesamt: number;
  zeilen_gesamt: number;
  datenbanken: number;
}

interface Pruefbericht {
  archiv_version?: number;
  erstellt_am_text?: string;
  zeilen_gesamt?: number;
  dateien: DateiEintrag[];
  datei_anzahl: number;
  bytes_gesamt: number;
  ueberschreibt_anzahl: number;
  abgelehnt: string[];
}

/**
 * Groessen mit deutschem Trennzeichen.
 *
 * `toFixed()` liefert immer einen Punkt, egal welche Sprache der
 * Browser hat -- deshalb ausdruecklich de-DE.
 */
function groesse(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toLocaleString("de-DE", { maximumFractionDigits: 1 })} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toLocaleString("de-DE", { maximumFractionDigits: 2 })} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toLocaleString("de-DE", { maximumFractionDigits: 2 })} GB`;
}

function zahl(n: number): string {
  return n.toLocaleString("de-DE");
}

export function UmzugPanel() {
  const [uebersicht, setUebersicht] = useState<Uebersicht | null>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);
  const [fortschritt, setFortschritt] = useState("");
  const [bericht, setBericht] = useState<Pruefbericht | null>(null);
  const [rohdaten, setRohdaten] = useState<File | null>(null);
  const [ergebnis, setErgebnis] = useState<any>(null);
  const [alleZeigen, setAlleZeigen] = useState(false);
  const dateiRef = useRef<HTMLInputElement>(null);

  const laden = async () => {
    try {
      const antwort = await fetch("/api/bot/admin/umzug/uebersicht", {
        cache: "no-store",
      });
      if (!antwort.ok) throw new Error(`Fehler ${antwort.status}`);
      setUebersicht(await antwort.json());
    } catch (err: any) {
      toast.error(err?.message || "Die Übersicht ließ sich nicht laden.");
    } finally {
      setLaedt(false);
    }
  };

  useEffect(() => {
    laden();
  }, []);

  // ── Herunterladen ──────────────────────────────────────────────────
  const herunterladen = async () => {
    setBeschaeftigt(true);
    setFortschritt("Das Archiv wird gepackt …");
    try {
      const antwort = await fetch("/api/bot/admin/umzug/download", {
        cache: "no-store",
      });
      if (!antwort.ok) {
        let text = `Fehler ${antwort.status}`;
        try {
          const d = await antwort.json();
          if (d?.detail) text = String(d.detail);
        } catch {
          /* keine JSON-Antwort */
        }
        throw new Error(text);
      }

      setFortschritt("Die Datei wird übertragen …");
      const blob = await antwort.blob();

      let name = `umzug-komplett-${Date.now()}.zip`;
      const kopf = antwort.headers.get("content-disposition") || "";
      const treffer = kopf.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      if (treffer?.[1]) name = decodeURIComponent(treffer[1]);

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);

      toast.success(`${name} gespeichert (${groesse(blob.size)}).`);
    } catch (err: any) {
      toast.error(err?.message || "Der Download ist fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
      setFortschritt("");
    }
  };

  // ── Datei auswählen und prüfen ─────────────────────────────────────
  const dateiGewaehlt = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const datei = e.target.files?.[0];
    if (!datei) return;

    setRohdaten(datei);
    setBericht(null);
    setErgebnis(null);
    setBeschaeftigt(true);
    setFortschritt("Das Archiv wird geprüft …");

    try {
      const antwort = await fetch("/api/bot/admin/umzug/pruefen", {
        method: "POST",
        headers: { "Content-Type": "application/zip" },
        body: datei,
      });
      const daten = await antwort.json();
      if (!antwort.ok) throw new Error(daten?.detail || `Fehler ${antwort.status}`);
      setBericht(daten);
      toast.success(`${daten.datei_anzahl} Dateien im Archiv gefunden.`);
    } catch (err: any) {
      toast.error(err?.message || "Das Archiv ließ sich nicht lesen.");
      setRohdaten(null);
    } finally {
      setBeschaeftigt(false);
      setFortschritt("");
    }
  };

  // ── Einspielen ─────────────────────────────────────────────────────
  const einspielen = async () => {
    if (!rohdaten || !bericht) return;

    const frage =
      `Wirklich einspielen?\n\n` +
      `${bericht.datei_anzahl} Dateien werden zurückgeschrieben, ` +
      `${bericht.ueberschreibt_anzahl} davon überschreiben vorhandene.\n\n` +
      `Der bisherige Stand wird vorher gesichert.\n` +
      `Danach muss der Bot neu starten.`;
    if (!confirm(frage)) return;

    setBeschaeftigt(true);
    setFortschritt("Die Dateien werden zurückgeschrieben …");
    try {
      const antwort = await fetch("/api/bot/admin/umzug/einspielen", {
        method: "POST",
        headers: { "Content-Type": "application/zip" },
        body: rohdaten,
      });
      const daten = await antwort.json();
      if (!antwort.ok) throw new Error(daten?.detail || `Fehler ${antwort.status}`);

      setErgebnis(daten);
      toast.success(`${daten.geschrieben} Dateien eingespielt.`);
      if (dateiRef.current) dateiRef.current.value = "";
      setRohdaten(null);
      setBericht(null);
      await laden();
    } catch (err: any) {
      toast.error(err?.message || "Das Einspielen ist fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
      setFortschritt("");
    }
  };

  const dateien = uebersicht?.dateien ?? [];
  const sichtbar = alleZeigen ? dateien : dateien.slice(0, 8);

  return (
    <div className="space-y-4">
      {/* ── Kopf ──────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-[#5865f2]/40 bg-[#131318] p-5">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-[#5865f2]/15 p-2.5">
            <PackageOpen className="h-5 w-5 text-[#5865f2]" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-semibold text-white">
              Umzug auf ein anderes Konto
            </h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-400">
              Eine Datei mit <strong className="text-slate-200">allem</strong> —
              jede Einstellung, jeder eigene Text, offene Tickets, Panels,
              XP, Warnungen und der Schlüssel für die Vorlagen-Zugangscodes.
              Auf dem neuen Konto hochladen, und es läuft weiter wie vorher.
            </p>
          </div>
        </div>

        {/* Der Unterschied zur Sicherung darunter — das ist der Punkt,
            an dem sonst Daten verloren gehen. */}
        <div className="mt-4 flex gap-2.5 rounded-xl border border-amber-500/25 bg-amber-500/5 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <p className="text-xs leading-relaxed text-amber-200/80">
            Nicht verwechseln mit „Alles herunterladen“ weiter unten: das
            speichert nur ausgelesene Tabellenzeilen und kann auf einem
            <strong className="text-amber-200"> leeren</strong> Konto nichts
            zurückschreiben — es meldet trotzdem Erfolg. Für einen
            Kontowechsel ist dieser Bereich hier der richtige.
          </p>
        </div>
      </div>

      {/* ── Schritt 1: herunterladen ──────────────────────────────── */}
      <div className="rounded-2xl border border-[#1e1f22] bg-[#131318] p-5">
        <div className="mb-4 flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#5865f2] text-xs font-bold text-white">
            1
          </span>
          <h4 className="text-sm font-semibold text-white">
            Auf dem alten Konto herunterladen
          </h4>
        </div>

        {laedt ? (
          <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Übersicht wird geladen …
          </div>
        ) : uebersicht ? (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { wert: zahl(uebersicht.datei_anzahl), text: "Dateien" },
                { wert: zahl(uebersicht.datenbanken), text: "Datenbanken" },
                { wert: zahl(uebersicht.zeilen_gesamt), text: "Einträge" },
                { wert: groesse(uebersicht.bytes_gesamt), text: "Größe" },
              ].map((k) => (
                <div
                  key={k.text}
                  className="rounded-xl border border-[#1e1f22] bg-[#0f0f13] p-3"
                >
                  <div className="text-lg font-semibold text-white">{k.wert}</div>
                  <div className="text-xs text-slate-500">{k.text}</div>
                </div>
              ))}
            </div>

            <div className="mb-4 overflow-hidden rounded-xl border border-[#1e1f22]">
              {sichtbar.map((d, i) => (
                <div
                  key={d.pfad}
                  className={`flex items-center gap-3 px-3 py-2 text-xs ${
                    i % 2 ? "bg-[#0f0f13]" : "bg-[#0e0e12]"
                  }`}
                >
                  <FileArchive className="h-3.5 w-3.5 shrink-0 text-slate-600" />
                  <span className="min-w-0 flex-1 truncate font-mono text-slate-300">
                    {d.pfad}
                  </span>
                  {d.ist_datenbank && (d.zeilen ?? 0) > 0 && (
                    <span className="shrink-0 text-slate-500">
                      {zahl(d.zeilen ?? 0)} Einträge
                    </span>
                  )}
                  <span className="w-20 shrink-0 text-right text-slate-500">
                    {groesse(d.bytes)}
                  </span>
                </div>
              ))}
              {dateien.length > 8 && (
                <button
                  onClick={() => setAlleZeigen(!alleZeigen)}
                  className="w-full bg-[#0f0f13] px-3 py-2 text-xs text-[#5865f2] hover:bg-[#16161c]"
                >
                  {alleZeigen
                    ? "Weniger anzeigen"
                    : `Alle ${dateien.length} Dateien anzeigen`}
                </button>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={herunterladen}
                disabled={beschaeftigt}
                className="inline-flex items-center gap-2 rounded-xl bg-[#5865f2] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#4752c4] disabled:opacity-50"
              >
                {beschaeftigt ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Alles herunterladen
              </button>
              <button
                onClick={laden}
                disabled={beschaeftigt}
                className="inline-flex items-center gap-2 rounded-xl border border-[#1e1f22] bg-[#0f0f13] px-4 py-2.5 text-sm text-slate-300 transition hover:bg-[#16161c] disabled:opacity-50"
              >
                <RefreshCw className="h-4 w-4" />
                Neu einlesen
              </button>
            </div>
            {fortschritt && (
              <p className="mt-3 text-xs text-slate-500">{fortschritt}</p>
            )}
          </>
        ) : (
          <p className="py-6 text-sm text-slate-500">
            Die Übersicht ist nicht erreichbar. Läuft der Bot?
          </p>
        )}
      </div>

      {/* ── Schritt 2: einspielen ─────────────────────────────────── */}
      <div className="rounded-2xl border border-[#1e1f22] bg-[#131318] p-5">
        <div className="mb-4 flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#5865f2] text-xs font-bold text-white">
            2
          </span>
          <h4 className="text-sm font-semibold text-white">
            Auf dem neuen Konto einspielen
          </h4>
        </div>

        <input
          ref={dateiRef}
          type="file"
          accept=".zip,application/zip"
          onChange={dateiGewaehlt}
          className="hidden"
        />

        <button
          onClick={() => dateiRef.current?.click()}
          disabled={beschaeftigt}
          className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-[#1e1f22] bg-[#0f0f13] px-4 py-8 transition hover:border-[#5865f2]/50 hover:bg-[#16161c] disabled:opacity-50"
        >
          <Upload className="h-6 w-6 text-slate-500" />
          <span className="text-sm text-slate-300">
            {rohdaten ? rohdaten.name : "Umzugsdatei auswählen (.zip)"}
          </span>
          <span className="text-xs text-slate-600">
            {rohdaten
              ? groesse(rohdaten.size)
              : "Die Datei aus Schritt 1 vom alten Konto"}
          </span>
        </button>

        {/* Was drinsteckt — vor dem Einspielen, nicht danach. */}
        {bericht && (
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-[#1e1f22] bg-[#0f0f13] p-4">
              <div className="mb-3 flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                <span className="text-sm font-medium text-white">
                  Das Archiv wurde geprüft
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <div>
                  <div className="text-slate-500">Dateien</div>
                  <div className="font-semibold text-white">
                    {zahl(bericht.datei_anzahl)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Größe</div>
                  <div className="font-semibold text-white">
                    {groesse(bericht.bytes_gesamt)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Überschreibt</div>
                  <div className="font-semibold text-white">
                    {zahl(bericht.ueberschreibt_anzahl)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Erstellt</div>
                  <div className="font-semibold text-white">
                    {bericht.erstellt_am_text || "unbekannt"}
                  </div>
                </div>
              </div>

              {bericht.abgelehnt.length > 0 && (
                <div className="mt-3 flex gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-2.5">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-400" />
                  <div className="text-xs text-red-300">
                    {bericht.abgelehnt.length} Einträge wurden abgelehnt, weil
                    ihr Pfad aus dem Datenordner herausführt. Sie werden nicht
                    geschrieben.
                  </div>
                </div>
              )}
            </div>

            <div className="flex gap-2.5 rounded-xl border border-amber-500/25 bg-amber-500/5 p-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <p className="text-xs leading-relaxed text-amber-200/80">
                Der bisherige Stand wird vorher automatisch nach{" "}
                <code className="rounded bg-black/30 px-1">
                  db/backups/vor-umzug-…
                </code>{" "}
                gesichert. Nach dem Einspielen muss der Bot neu starten, damit
                er die neuen Dateien liest.
              </p>
            </div>

            <button
              onClick={einspielen}
              disabled={beschaeftigt}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
            >
              {beschaeftigt ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <HardDriveDownload className="h-4 w-4" />
              )}
              Jetzt einspielen
            </button>
            {fortschritt && (
              <p className="text-xs text-slate-500">{fortschritt}</p>
            )}
          </div>
        )}

        {/* Ergebnis */}
        {ergebnis && (
          <div className="mt-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
            <div className="mb-2 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span className="text-sm font-medium text-white">
                {zahl(ergebnis.geschrieben)} Dateien eingespielt
              </span>
            </div>
            {ergebnis.sicherung && (
              <p className="text-xs text-slate-400">
                Der alte Stand liegt in{" "}
                <code className="rounded bg-black/30 px-1">
                  {ergebnis.sicherung}
                </code>
              </p>
            )}
            {ergebnis.fehlgeschlagen?.length > 0 && (
              <div className="mt-2 text-xs text-red-300">
                {ergebnis.fehlgeschlagen.length} Dateien fehlgeschlagen:
                <ul className="mt-1 space-y-0.5">
                  {ergebnis.fehlgeschlagen.slice(0, 5).map((f: string) => (
                    <li key={f} className="font-mono">
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mt-3 flex items-center gap-1.5 text-xs font-medium text-amber-300">
              <ArrowRight className="h-3.5 w-3.5" />
              Jetzt den Bot in Railway neu starten.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
