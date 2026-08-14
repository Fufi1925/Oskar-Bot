"use client";

/**
 * Die 7-Tage-Probewochen im Admin-Bereich.
 *
 * ── Woher die Einträge kommen ───────────────────────────────────────
 *
 * Nicht von hier. Der Template-Bot vergibt persönliche Keys, die genau
 * sieben Tage gelten, und meldet das an den University Bot
 * (`POST /api/v1/premium/grant`). Diese Liste zeigt, was angekommen
 * ist.
 *
 * ── Warum abgelaufene Einträge stehen bleiben ───────────────────────
 *
 * Sie sind der Beleg dafür, dass ein Konto seine Probewoche schon
 * hatte — **eine pro Konto, für immer**. Würden sie verschwinden,
 * könnte sich jeder nach sieben Tagen eine neue holen, und die Regel
 * wäre wirkungslos.
 *
 * Deshalb sind es hier auch zwei verschiedene Knöpfe, die leicht zu
 * verwechseln wären:
 *
 *   **Beenden**       Die laufende Woche endet sofort. Der Eintrag
 *                     bleibt, das Konto hat sie verbraucht.
 *   **Zurücksetzen**  Der Eintrag verschwindet, das Konto darf noch
 *                     einmal. Für Support-Fälle.
 *
 * Weil der Unterschied nicht selbsterklärend ist, steht er als Satz
 * an den Knöpfen — nicht nur in diesem Kommentar.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Clock,
  Gift,
  Loader2,
  RefreshCw,
  RotateCcw,
  Search,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TrialRow {
  user_id: string;
  user_name: string;
  guild_id: string | null;
  guild_name: string;
  granted_at: number;
  expires_at: number;
  duration_days: number;
  times_granted: number;
  reset_by: string;
  active: boolean;
  seconds_left: number;
}

const KARTE = "rounded-3xl border border-slate-800 bg-[#131318]";

function datum(unix: number) {
  if (!unix) return "—";
  return new Date(unix * 1000).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/**
 * Wie lange noch — in Worten, die jemand laut sagen würde.
 *
 * „noch 0 Tage“ am letzten Tag wäre falsch: die Woche läuft ja noch.
 * Unter einem Tag wird deshalb in Stunden gerechnet.
 */
function restzeit(sekunden: number) {
  if (sekunden <= 0) return "abgelaufen";
  const tage = Math.floor(sekunden / 86400);
  if (tage >= 1) return `noch ${tage} ${tage === 1 ? "Tag" : "Tage"}`;
  const stunden = Math.max(1, Math.floor(sekunden / 3600));
  return `noch ${stunden} ${stunden === 1 ? "Stunde" : "Stunden"}`;
}

export function PremiumTrials() {
  const [rows, setRows] = useState<TrialRow[]>([]);
  const [stats, setStats] = useState<{
    total: number;
    active: number;
    expired: number;
  } | null>(null);
  const [tage, setTage] = useState(7);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [nurAktive, setNurAktive] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.listPremiumTrials(300);
      setRows(res?.trials || []);
      setStats(res?.stats || null);
      if (res?.trial_days) setTage(res.trial_days);
    } catch (err: any) {
      toast.error(err?.message || "Die Probewochen ließen sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const sichtbar = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (nurAktive && !row.active) return false;
      if (!needle) return true;
      return [row.user_id, row.user_name, row.guild_name]
        .filter(Boolean)
        .some((f) => String(f).toLowerCase().includes(needle));
    });
  }, [rows, query, nurAktive]);

  const beenden = async (row: TrialRow) => {
    if (
      !confirm(
        `Die Probewoche von ${row.user_name || row.user_id} sofort beenden?\n\n` +
          "Der Eintrag bleibt bestehen — das Konto hat seine Probewoche " +
          "damit verbraucht und bekommt keine neue.",
      )
    ) {
      return;
    }
    setBusy(row.user_id);
    try {
      await api.revokePremiumTrial(row.user_id);
      toast.success("Die Probewoche wurde beendet.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBusy("");
    }
  };

  const zuruecksetzen = async (row: TrialRow) => {
    if (
      !confirm(
        `Die Probewoche von ${row.user_name || row.user_id} zurücksetzen?\n\n` +
          `Das Konto darf danach noch einmal ${tage} Tage kostenlos — ` +
          "normalerweise geht das nur einmal.",
      )
    ) {
      return;
    }
    setBusy(row.user_id);
    try {
      await api.resetPremiumTrial(row.user_id);
      toast.success("Die Probewoche ist wieder frei.");
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
          <Gift className="h-[18px] w-[18px] text-indigo-400" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[18px] font-bold tracking-tight text-white">
            {tage} Tage kostenlos
          </h2>
          <p className="mt-0.5 text-[13px] text-slate-500">
            Der Template-Bot vergibt sie beim Einlösen eines persönlichen
            Keys. Eine pro Konto.
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

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Insgesamt", wert: stats?.total ?? 0, farbe: "text-slate-400" },
          { label: "Laufen gerade", wert: stats?.active ?? 0, farbe: "text-emerald-400" },
          { label: "Abgelaufen", wert: stats?.expired ?? 0, farbe: "text-slate-500" },
        ].map((k) => (
          <div key={k.label} className={cn(KARTE, "px-4 py-3.5")}>
            <p className={cn("text-[19px] font-bold leading-none tabular-nums", k.farbe)}>
              {k.wert}
            </p>
            <p className="mt-1.5 text-[12px] text-slate-500">{k.label}</p>
          </div>
        ))}
      </div>

      <div className={cn(KARTE, "flex flex-wrap items-center gap-3 p-4")}>
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Nach Name, ID oder Server suchen"
            className="w-full rounded-xl border border-slate-800 bg-[#0e0e12] py-2.5 pl-10 pr-4 text-sm text-white placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
          />
        </div>
        <button
          type="button"
          onClick={() => setNurAktive((v) => !v)}
          aria-pressed={nurAktive}
          className={cn(
            "rounded-xl border px-4 py-2.5 text-sm font-semibold transition-colors",
            nurAktive
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              : "border-slate-800 bg-[#0e0e12] text-slate-400 hover:border-slate-700 hover:text-white",
          )}
        >
          Nur laufende
        </button>
      </div>

      {sichtbar.length === 0 ? (
        <div className={cn(KARTE, "px-6 py-10 text-center")}>
          <Gift className="mx-auto mb-3 h-7 w-7 text-slate-700" />
          <p className="text-[15px] text-slate-300">
            {rows.length === 0
              ? "Noch keine Probewoche vergeben."
              : "Kein Eintrag passt zu dieser Suche."}
          </p>
          {rows.length === 0 && (
            <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">
              Sie erscheinen hier, sobald jemand im Template-Bot einen
              persönlichen Key einlöst. Kommt nichts an, prüf{" "}
              <code className="text-slate-400">PREMIUM_PARTNER_TOKEN</code> auf
              beiden Seiten.
            </p>
          )}
        </div>
      ) : (
        <div className={cn(KARTE, "overflow-hidden")}>
          {sichtbar.map((row, i) => (
            <div
              key={row.user_id}
              className={cn(
                "flex flex-wrap items-center gap-3 px-5 py-4",
                i > 0 && "border-t border-slate-800",
              )}
            >
              <span
                className={cn(
                  "grid h-9 w-9 shrink-0 place-items-center rounded-xl",
                  row.active ? "bg-emerald-500/10" : "bg-white/[0.04]",
                )}
              >
                {row.active ? (
                  <Check className="h-4 w-4 text-emerald-400" />
                ) : (
                  <Clock className="h-4 w-4 text-slate-600" />
                )}
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-semibold text-white">
                    {row.user_name || row.user_id}
                  </span>
                  {row.times_granted > 1 && (
                    <span className="rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-300">
                      {row.times_granted}. Probewoche
                    </span>
                  )}
                </div>
                <p className="mt-0.5 truncate font-mono text-[11px] text-slate-600">
                  {row.user_id}
                  {row.guild_name && (
                    <span className="font-sans"> · {row.guild_name}</span>
                  )}
                </p>
              </div>

              <div className="shrink-0 text-right">
                <p
                  className={cn(
                    "text-[13px] font-semibold",
                    row.active ? "text-emerald-400" : "text-slate-500",
                  )}
                >
                  {restzeit(row.seconds_left)}
                </p>
                <p className="mt-0.5 text-[11px] text-slate-600">
                  bis {datum(row.expires_at)}
                </p>
              </div>

              <div className="flex shrink-0 gap-2">
                {row.active && (
                  <button
                    type="button"
                    onClick={() => beenden(row)}
                    disabled={busy === row.user_id}
                    title="Beendet die laufende Woche. Der Eintrag bleibt — das Konto bekommt keine neue."
                    className="flex items-center gap-1.5 rounded-xl border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-[13px] font-semibold text-rose-300 transition-colors hover:bg-rose-500/20 disabled:opacity-40"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    Beenden
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => zuruecksetzen(row)}
                  disabled={busy === row.user_id}
                  title="Gibt den Weg frei: das Konto darf noch einmal kostenlos."
                  className="flex items-center gap-1.5 rounded-xl border border-slate-800 bg-[#0e0e12] px-3 py-2 text-[13px] font-semibold text-slate-300 transition-colors hover:border-slate-700 hover:text-white disabled:opacity-40"
                >
                  {busy === row.user_id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="h-3.5 w-3.5" />
                  )}
                  Zurücksetzen
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Der Unterschied zwischen den beiden Knöpfen gehört auf den
          Bildschirm, nicht nur in einen Kommentar: er ist der einzige
          Grund, warum es zwei sind. */}
      <div className={cn(KARTE, "flex gap-3 p-4")}>
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
        <p className="text-[13px] leading-relaxed text-slate-400">
          <b className="text-slate-300">Beenden</b> stoppt die laufende Woche
          sofort — das Konto hat sie damit verbraucht.{" "}
          <b className="text-slate-300">Zurücksetzen</b> gibt sie wieder frei,
          das Konto darf noch einmal {tage} Tage. Ohne Zurücksetzen bekommt
          jedes Konto genau eine.
        </p>
      </div>
    </section>
  );
}
