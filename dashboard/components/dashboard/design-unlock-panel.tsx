"use client";

/**
 * Freischaltliste für den Design-Reiter.
 *
 * Normalerweise darf nur der Server-Inhaber das Aussehen des Bots
 * ändern. Hier lässt sich ein Server zusätzlich freischalten — etwa
 * für einen Partner, dessen Server einem anderen Konto gehört.
 *
 * Diese Liste taucht im Nutzer-Dashboard nirgends auf. Weder als Text
 * noch als Feld in der Antwort: dort steht nur ein Ja/Nein, ohne
 * Begründung. Wer freigeschaltet ist, sieht dasselbe wie ein
 * Inhaber — und wer es nicht ist, erfährt nicht, dass es diese
 * Möglichkeit gibt.
 */

import React, { useCallback, useEffect, useState } from "react";
import { KeyRound, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

interface Eintrag {
  guild_id: string;
  granted_at: number;
  granted_by: string;
  note: string;
}

function datum(unix: number) {
  if (!unix) return "—";
  return new Date(unix * 1000).toLocaleString("de-DE");
}

export function DesignUnlockPanel({
  guilds = [],
}: {
  guilds?: Array<{ id: string; name: string }>;
}) {
  const [liste, setListe] = useState<Eintrag[]>([]);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);
  const [wahl, setWahl] = useState("");
  const [notiz, setNotiz] = useState("");

  const laden = useCallback(async () => {
    try {
      const antwort = await api.designUnlocked();
      setListe(antwort.servers || []);
    } catch (err: any) {
      toast.error(err?.message || "Konnte die Liste nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => {
    laden();
  }, [laden]);

  const freischalten = async () => {
    if (!wahl.trim()) {
      toast.error("Wähle einen Server oder gib eine ID ein.");
      return;
    }
    setBeschaeftigt(true);
    try {
      const antwort = await api.designUnlock(wahl.trim(), notiz);
      setListe(antwort.servers || []);
      setWahl("");
      setNotiz("");
      toast.success("Freigeschaltet.");
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const entfernen = async (guildId: string) => {
    setBeschaeftigt(true);
    try {
      const antwort = await api.designLock(guildId);
      setListe(antwort.servers || []);
      toast.success("Freischaltung zurückgenommen.");
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const name = (id: string) =>
    guilds.find((g) => g.id === id)?.name || null;

  return (
    <div className="space-y-4">
      <div className={CARD}>
        <div className="flex items-start gap-3">
          <div className="rounded-2xl bg-amber-400/15 p-2.5">
            <KeyRound className="h-5 w-5 text-amber-400" />
          </div>
          <div>
            <h3 className="font-bold text-white">Design freischalten</h3>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-400">
              Sonst darf nur der Server-Inhaber das Aussehen des Bots ändern.
              Hier lässt sich ein Server zusätzlich freigeben — Premium am
              Konto braucht die Person trotzdem.
            </p>
            <p className="mt-2 text-xs text-slate-600">
              Im Nutzer-Dashboard wird diese Liste nirgends erwähnt.
            </p>
          </div>
        </div>

        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <select
            value={guilds.some((g) => g.id === wahl) ? wahl : ""}
            onChange={(e) => setWahl(e.target.value)}
            className="flex-1 rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-amber-400/50"
          >
            <option value="">Server wählen …</option>
            {guilds.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
          <input
            value={notiz}
            onChange={(e) => setNotiz(e.target.value)}
            placeholder="Notiz (freiwillig)"
            className="flex-1 rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-amber-400/50"
          />
          <button
            onClick={freischalten}
            disabled={beschaeftigt}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-2xl bg-amber-400 px-4 py-3 text-sm font-bold text-black transition hover:brightness-110 disabled:opacity-50"
          >
            {beschaeftigt ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Freischalten
          </button>
        </div>
      </div>

      <div className={CARD}>
        <h4 className="mb-3 text-sm font-semibold text-white">
          Freigeschaltet ({liste.length})
        </h4>

        {laedt ? (
          <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Wird geladen …
          </div>
        ) : liste.length === 0 ? (
          <p className="py-4 text-sm text-slate-600">
            Kein Server freigeschaltet. Es gilt überall: nur der Inhaber.
          </p>
        ) : (
          <div className="space-y-2">
            {liste.map((e) => (
              <div
                key={e.guild_id}
                className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-800 bg-[#0f0f13] p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-white">
                    {name(e.guild_id) || (
                      <span className="text-slate-500">
                        Bot ist nicht auf diesem Server
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 font-mono text-xs text-slate-600">
                    {e.guild_id}
                  </div>
                  {e.note && (
                    <div className="mt-1 text-xs text-slate-500">{e.note}</div>
                  )}
                </div>
                <div className="text-xs text-slate-600">
                  {datum(e.granted_at)}
                </div>
                <button
                  onClick={() => entfernen(e.guild_id)}
                  disabled={beschaeftigt}
                  className="rounded-xl border border-slate-800 p-2 text-slate-400 transition hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
                  title="Freischaltung zurücknehmen"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
