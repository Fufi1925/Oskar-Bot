"use client";

/**
 * Das Beta-Formular: fünf Fragen.
 *
 * Die erste ist besonders
 * -----------------------
 * Sie zeigt das angemeldete Discord-Konto und lässt sich nicht
 * ausfüllen — Bild und Name kommen aus der Anmeldung. Daneben steht
 * klein „Bin ich nicht“: ein Klick meldet ab, damit man sich mit dem
 * richtigen Konto neu anmelden kann.
 *
 * Die ID wird ohnehin serverseitig gesetzt (der Proxy überschreibt
 * sie aus der Sitzung). Das Feld hier ist die sichtbare Seite
 * derselben Regel — niemand soll glauben, er könne einen Antrag für
 * ein anderes Konto stellen.
 */

import React, { useCallback, useEffect, useState } from "react";
import { signOut } from "next-auth/react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  Send,
  Sparkles,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

interface Frage {
  key: string;
  frage: string;
  hinweis: string;
  readonly: boolean;
  min: number;
  max: number;
}

function datum(unix: number) {
  if (!unix) return "";
  return new Date(unix * 1000).toLocaleDateString("de-DE");
}

export function BetaForm() {
  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [sendet, setSendet] = useState(false);
  const [antworten, setAntworten] = useState<Record<string, string>>({});

  const laden = useCallback(async () => {
    try {
      setDaten(await api.betaForm());
    } catch (err: any) {
      toast.error(err?.message || "Konnte das Formular nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => {
    laden();
  }, [laden]);

  const absenden = async () => {
    setSendet(true);
    try {
      const antwort = await api.betaApply(antworten);
      setDaten((alt: any) => ({
        ...alt,
        application: antwort.application,
        can_apply: false,
      }));
      setAntworten({});
      toast.success("Antrag abgeschickt — wir melden uns in 1–7 Tagen.");
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setSendet(false);
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

  const fragen: Frage[] = daten?.questions || [];
  const nutzer = daten?.user || {};
  const antrag = daten?.application;
  const darf = Boolean(daten?.can_apply);

  // Fehlt noch etwas?
  const fehlend = fragen
    .filter((f) => !f.readonly && f.min > 0)
    .filter((f) => (antworten[f.key] || "").trim().length < f.min);

  return (
    <div className="space-y-4">
      {/* ── Der Stand eines vorhandenen Antrags ───────────────────── */}
      {antrag && antrag.status === "offen" && (
        <div className="flex gap-3 rounded-3xl border border-amber-400/30 bg-amber-400/5 p-4">
          <Clock className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          <div>
            <div className="font-semibold text-white">
              Dein Antrag liegt uns vor
            </div>
            <p className="mt-1 text-sm text-amber-200/80">
              Eingereicht am {datum(antrag.created_at)}. Wir melden uns
              innerhalb von 1–7 Tagen per Discord-Direktnachricht — egal wie
              die Entscheidung ausfällt.
            </p>
          </div>
        </div>
      )}

      {antrag && antrag.status === "angenommen" && (
        <div className="flex gap-3 rounded-3xl border border-emerald-500/30 bg-emerald-500/5 p-4">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
          <div>
            <div className="font-semibold text-white">Du bist in der Beta</div>
            <p className="mt-1 text-sm text-emerald-200/80">
              Premium ist aktiv. Du findest die neuen Möglichkeiten im
              Design-Reiter deines Servers.
            </p>
          </div>
        </div>
      )}

      {antrag && antrag.status === "abgelehnt" && (
        <div className="flex gap-3 rounded-3xl border border-slate-800 bg-[#0f0f13] p-4">
          <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" />
          <div>
            <div className="font-semibold text-white">
              Dein letzter Antrag wurde nicht angenommen
            </div>
            {antrag.grund && (
              <p className="mt-1 text-sm text-slate-400">{antrag.grund}</p>
            )}
            <p className="mt-1 text-xs text-slate-600">
              Das ist keine Sperre — du kannst es unten erneut versuchen.
            </p>
          </div>
        </div>
      )}

      {/* ── Worum es geht ─────────────────────────────────────────── */}
      <div className={cn(CARD, "border-amber-400/25")}>
        <div className="flex items-start gap-3">
          <div className="rounded-2xl bg-amber-400/15 p-2.5">
            <Sparkles className="h-5 w-5 text-amber-400" />
          </div>
          <div>
            <h3 className="font-bold text-white">
              Beta-Phase — mit 20 % Rabatt
            </h3>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-400">
              Premium für den Hauptbot ist noch in der Beta. Beantworte die
              fünf Fragen unten; unser Bot schickt dir innerhalb von{" "}
              <strong className="text-slate-200">1–7 Tagen</strong> eine
              Direktnachricht, ob du aufgenommen wirst. Bei einer Zusage
              bekommst du Premium automatisch — du musst nichts weiter tun.
            </p>
          </div>
        </div>
      </div>

      {/* ── Die Fragen ────────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-6")}>
        {fragen.map((f, i) => (
          <div key={f.key}>
            <label className="flex items-baseline gap-2 text-sm font-semibold text-white">
              <span className="text-xs text-slate-600">{i + 1}.</span>
              {f.frage}
            </label>

            {f.readonly ? (
              // Das Discord-Konto. Nicht ausfüllbar.
              <div className="mt-2 flex items-center gap-3 rounded-2xl border border-slate-800 bg-[#0f0f13] p-3">
                {nutzer.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={nutzer.avatar}
                    alt=""
                    className="h-9 w-9 rounded-full"
                  />
                ) : (
                  <div className="h-9 w-9 rounded-full bg-slate-800" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-white">
                    {nutzer.name || "Nicht angemeldet"}
                  </div>
                  <div className="truncate font-mono text-xs text-slate-600">
                    {nutzer.id}
                  </div>
                </div>
                {/* Klein daneben, wie gewünscht. */}
                <button
                  onClick={() => signOut({ callbackUrl: "/" })}
                  className="shrink-0 text-[11px] text-slate-600 underline underline-offset-2 transition hover:text-slate-400"
                >
                  Bin ich nicht
                </button>
              </div>
            ) : (
              <>
                <textarea
                  value={antworten[f.key] || ""}
                  onChange={(e) =>
                    setAntworten((a) => ({ ...a, [f.key]: e.target.value }))
                  }
                  disabled={!darf || sendet}
                  maxLength={f.max}
                  rows={3}
                  className="mt-2 w-full resize-y rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-amber-400/50 disabled:opacity-50"
                />
                <div className="mt-1 flex justify-between text-xs">
                  <span className="text-slate-600">{f.hinweis}</span>
                  <span
                    className={cn(
                      "shrink-0 tabular-nums",
                      (antworten[f.key] || "").length < f.min
                        ? "text-slate-600"
                        : "text-emerald-400/70"
                    )}
                  >
                    {(antworten[f.key] || "").length}
                    {f.min > 0 && ` / mind. ${f.min}`}
                  </span>
                </div>
              </>
            )}
          </div>
        ))}

        {!darf ? (
          <p className="flex items-start gap-2 text-sm text-slate-500">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            Du hast bereits einen offenen Antrag. Warte bitte auf unsere
            Antwort.
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={absenden}
              disabled={sendet || fehlend.length > 0 || !nutzer.id}
              className="inline-flex items-center gap-2 rounded-2xl bg-amber-400 px-5 py-3 text-sm font-bold text-black transition hover:brightness-110 disabled:opacity-40"
            >
              {sendet ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Antrag abschicken
            </button>
            {fehlend.length > 0 && (
              <span className="text-xs text-slate-600">
                Noch {fehlend.length}{" "}
                {fehlend.length === 1 ? "Frage" : "Fragen"} zu kurz.
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
