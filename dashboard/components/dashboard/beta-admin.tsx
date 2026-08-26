"use client";

/**
 * Beta-Anträge prüfen.
 *
 * Annehmen vergibt Premium sofort und schickt eine DM. Ablehnen
 * verlangt eine Begründung — eine Absage ohne Grund ist für den
 * Empfänger wertlos, er weiß nicht, ob ein zweiter Versuch Sinn hat.
 *
 * Der Zustand der DM steht dabei: wer seine Direktnachrichten zu hat,
 * erfährt sonst nie von der Entscheidung, und hier sähe es aus, als
 * wäre alles erledigt.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Clock,
  Loader2,
  MailWarning,
  RefreshCw,
  ShieldOff,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

interface Antrag {
  id: number;
  user_id: string;
  user_name: string;
  avatar: string;
  warum: string;
  gut: string;
  besser: string;
  schluss: string;
  status: string;
  grund: string;
  created_at: number;
  decided_at: number | null;
  decided_by: string;
  dm_state: string;
}

const DM_TEXT: Record<string, string> = {
  sent: "DM zugestellt",
  dms_closed: "DMs geschlossen — er weiß es nicht",
  unknown_user: "Konto nicht erreichbar",
  failed: "DM fehlgeschlagen",
};

function datum(unix: number) {
  if (!unix) return "—";
  return new Date(unix * 1000).toLocaleString("de-DE");
}

export function BetaAdmin() {
  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(0);
  const [filter, setFilter] = useState("offen");
  const [gruende, setGruende] = useState<Record<number, string>>({});

  const laden = useCallback(async () => {
    try {
      setDaten(await api.betaList());
    } catch (err: any) {
      toast.error(err?.message || "Konnte die Anträge nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => {
    laden();
  }, [laden]);

  const entscheiden = async (a: Antrag, annehmen: boolean) => {
    const grund = (gruende[a.id] || "").trim();
    if (!annehmen && !grund) {
      toast.error("Eine Ablehnung braucht eine Begründung.");
      return;
    }
    setBeschaeftigt(a.id);
    try {
      const antwort = await api.betaDecide(a.id, annehmen, grund);
      setDaten({
        applications: antwort.applications,
        counts: antwort.counts,
      });
      const dm = DM_TEXT[antwort.dm] || antwort.dm;
      toast.success(
        `${annehmen ? "Angenommen" : "Abgelehnt"} — ${dm}.`
      );
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBeschaeftigt(0);
    }
  };

  const entziehen = async (a: Antrag) => {
    if (
      !confirm(
        `${a.user_name || a.user_id} das Premium entziehen?\n\n` +
          "Der Zugang ist danach sofort weg. Bei einer späteren " +
          "Neuvergabe erscheint der Willkommens-Hinweis erneut."
      )
    ) {
      return;
    }
    setBeschaeftigt(a.id);
    try {
      const antwort = await api.betaRevoke(a.user_id);
      setDaten({
        applications: antwort.applications,
        counts: antwort.counts,
      });
      toast.success(`Premium entzogen (${antwort.revoked} Lizenzen).`);
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBeschaeftigt(0);
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

  const alle: Antrag[] = daten?.applications || [];
  const zahlen = daten?.counts || {};
  const sichtbar = filter ? alle.filter((a) => a.status === filter) : alle;

  return (
    <div className="space-y-4">
      {/* ── Zahlen und Filter ─────────────────────────────────────── */}
      <div className={CARD}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-bold text-white">Beta-Anträge</h3>
            <p className="mt-1 text-sm text-slate-400">
              Annehmen vergibt Premium sofort und schickt eine DM.
            </p>
          </div>
          <button
            onClick={laden}
            className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-3 text-slate-300 transition hover:bg-white/[0.04]"
            title="Neu laden"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {[
            { id: "offen", label: `Offen (${zahlen.offen ?? 0})` },
            { id: "angenommen", label: `Angenommen (${zahlen.angenommen ?? 0})` },
            { id: "abgelehnt", label: `Abgelehnt (${zahlen.abgelehnt ?? 0})` },
            { id: "", label: `Alle (${zahlen.gesamt ?? 0})` },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={cn(
                "rounded-xl border px-3 py-1.5 text-xs transition",
                filter === f.id
                  ? "border-amber-400/50 bg-amber-400/15 text-amber-200"
                  : "border-slate-800 bg-[#0f0f13] text-slate-400 hover:bg-white/[0.04]"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Die Anträge ───────────────────────────────────────────── */}
      {sichtbar.length === 0 ? (
        <div className={CARD}>
          <p className="text-sm text-slate-600">
            Hier ist gerade nichts.
          </p>
        </div>
      ) : (
        sichtbar.map((a) => (
          <div key={a.id} className={CARD}>
            {/* Wer */}
            <div className="flex flex-wrap items-center gap-3">
              {a.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={a.avatar} alt="" className="h-10 w-10 rounded-full" />
              ) : (
                <div className="h-10 w-10 rounded-full bg-slate-800" />
              )}
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold text-white">
                  {a.user_name || "Unbekannt"}
                </div>
                <div className="truncate font-mono text-xs text-slate-600">
                  {a.user_id}
                </div>
              </div>

              <span
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-xl px-2.5 py-1 text-xs",
                  a.status === "offen"
                    ? "bg-amber-400/15 text-amber-300"
                    : a.status === "angenommen"
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "bg-slate-800 text-slate-400"
                )}
              >
                {a.status === "offen" ? (
                  <Clock className="h-3 w-3" />
                ) : a.status === "angenommen" ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <XCircle className="h-3 w-3" />
                )}
                {a.status}
              </span>
            </div>

            {/* Die Antworten */}
            <div className="mt-4 space-y-3">
              {[
                ["Warum in die Beta?", a.warum],
                ["Was findet er gut?", a.gut],
                ["Was kann besser werden?", a.besser],
                ["Schlusswort", a.schluss],
              ]
                .filter(([, text]) => text)
                .map(([titel, text]) => (
                  <div
                    key={titel}
                    className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-3"
                  >
                    <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      {titel}
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-slate-300">
                      {text}
                    </p>
                  </div>
                ))}
            </div>

            <div className="mt-3 text-xs text-slate-600">
              Eingereicht {datum(a.created_at)}
              {a.decided_at ? ` · entschieden ${datum(a.decided_at)}` : ""}
              {a.decided_by ? ` von ${a.decided_by}` : ""}
            </div>

            {/* Ehrlich: kam die DM an? */}
            {a.dm_state && a.dm_state !== "sent" && (
              <div className="mt-2 flex gap-2 rounded-2xl border border-amber-500/25 bg-amber-500/5 p-2.5">
                <MailWarning className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                <span className="text-xs text-amber-200/80">
                  {DM_TEXT[a.dm_state] || a.dm_state} — er weiß nichts von der
                  Entscheidung.
                </span>
              </div>
            )}

            {a.grund && a.status === "abgelehnt" && (
              <div className="mt-2 rounded-2xl border border-slate-800 bg-[#0f0f13] p-2.5 text-xs text-slate-400">
                <span className="text-slate-600">Begründung:</span> {a.grund}
              </div>
            )}

            {/* Entscheiden */}
            {a.status === "offen" && (
              <div className="mt-4 space-y-2">
                <input
                  value={gruende[a.id] || ""}
                  onChange={(e) =>
                    setGruende((g) => ({ ...g, [a.id]: e.target.value }))
                  }
                  placeholder="Begründung (Pflicht bei Ablehnung)"
                  className="w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/50"
                />
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => entscheiden(a, true)}
                    disabled={beschaeftigt === a.id}
                    className="inline-flex items-center gap-2 rounded-2xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-50"
                  >
                    {beschaeftigt === a.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4" />
                    )}
                    Annehmen
                  </button>
                  <button
                    onClick={() => entscheiden(a, false)}
                    disabled={beschaeftigt === a.id}
                    className="inline-flex items-center gap-2 rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-2.5 text-sm text-slate-300 transition hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
                  >
                    <XCircle className="h-4 w-4" />
                    Ablehnen
                  </button>
                </div>
              </div>
            )}

            {a.status === "angenommen" && (
              <button
                onClick={() => entziehen(a)}
                disabled={beschaeftigt === a.id}
                className="mt-4 inline-flex items-center gap-2 rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-2.5 text-sm text-slate-400 transition hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
              >
                {beschaeftigt === a.id ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ShieldOff className="h-4 w-4" />
                )}
                Premium entziehen
              </button>
            )}
          </div>
        ))
      )}
    </div>
  );
}
