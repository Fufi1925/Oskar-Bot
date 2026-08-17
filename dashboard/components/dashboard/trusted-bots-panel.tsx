"use client";

/**
 * Die Bots, die der Anti-Nuke nie angreift.
 *
 * ── Wozu die Liste da ist ───────────────────────────────────────────
 *
 * Bekannte Bots wie MEE6 oder Dyno legen Kanäle an, vergeben Rollen
 * und löschen Nachrichten — also genau das, was der Anti-Nuke als
 * Angriff liest. Ohne Eintrag bannt er sie beim ersten Mal, und der
 * Server-Inhaber sucht den Fehler bei sich.
 *
 * ── Warum sie global gilt ───────────────────────────────────────────
 *
 * Weil sie sonst eine Hintertür wäre: wer sie auf dem eigenen Server
 * pflegen dürfte, trägt seinen Zweitbot ein und hat den Schutz
 * ausgehebelt, den der Anti-Nuke verspricht. Server-Inhaber **sehen**
 * die Liste in ihrem Reiter — ändern kann sie nur das Team.
 *
 * ── Die drei, die nicht wegzubekommen sind ──────────────────────────
 *
 * Hauptbot, Template-Bot und Statusbot stehen fest drin. Der
 * Template-Bot baut nach einem Angriff Server wieder auf — dutzende
 * Kanäle und Rollen in Sekunden, die exakte Form eines Nukes. Wer ihn
 * versehentlich austrägt, lässt ihn mitten in der Rettung bannen und
 * steht mit einem halb wiederhergestellten Server da.
 *
 * Deshalb tragen sie kein Entfernen-Kreuz, sondern ein Schloss.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, Bot, Loader2, Lock, Plus, RefreshCw, Server, Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TrustedBot {
  id: string;
  name: string;
  avatar: string | null;
  known: boolean;
  /** builtin = fest eingebaut, env = Railway-Variable, manual = hier */
  source: "builtin" | "env" | "manual";
  label: string;
  note: string;
  added_by: string;
  added_at: number;
}

const KARTE = "rounded-3xl border border-slate-800 bg-[#131318]";

/** Woher der Eintrag stammt — und ob er sich entfernen lässt. */
const QUELLE: Record<string, { text: string; ton: string }> = {
  builtin: {
    text: "Fest eingebaut",
    ton: "border-amber-500/25 bg-amber-500/10 text-amber-400",
  },
  env: {
    text: "Aus der Variablen",
    ton: "border-slate-800 bg-[#0e0e12] text-slate-400",
  },
  manual: {
    text: "Hier eingetragen",
    ton: "border-indigo-500/25 bg-indigo-500/10 text-indigo-300",
  },
};

export function TrustedBotsPanel() {
  const [bots, setBots] = useState<TrustedBot[]>([]);
  const [envName, setEnvName] = useState("TRUSTED_BOTS");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [neueId, setNeueId] = useState("");
  const [notiz, setNotiz] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await api.trustedBots();
      setBots(res?.bots || []);
      if (res?.env_name) setEnvName(res.env_name);
    } catch (err: any) {
      toast.error(err?.message || "Die Liste ließ sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const hinzufuegen = async () => {
    const id = neueId.trim();
    if (!id) return;

    // Vorab prüfen, statt den Server antworten zu lassen: eine
    // Discord-ID ist 17 bis 20 Ziffern, und wer einen Namen einträgt,
    // soll das sofort erfahren.
    if (!/^\d{17,20}$/.test(id)) {
      toast.error(
        "Das sieht nicht nach einer Discord-ID aus — die besteht aus 17 bis 20 Ziffern.",
      );
      return;
    }

    setBusy("add");
    try {
      const res = await api.addTrustedBot(id, notiz.trim());
      setBots(res?.bots || []);
      setNeueId("");
      setNotiz("");
      toast.success("Der Bot wird vom Anti-Nuke nicht mehr angegriffen.");
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBusy("");
    }
  };

  const entfernen = async (eintrag: TrustedBot) => {
    if (
      !confirm(
        `${eintrag.name || eintrag.id} von der Liste nehmen?\n\n` +
          "Der Anti-Nuke behandelt diesen Bot danach wie jeden anderen: " +
          "legt er Kanäle an oder vergibt Rollen, wird er gebannt.",
      )
    ) {
      return;
    }
    setBusy(eintrag.id);
    try {
      const res = await api.removeTrustedBot(eintrag.id);
      setBots(res?.bots || []);
      toast.success("Der Bot ist nicht mehr geschützt.");
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

  const eingebaut = bots.filter((b) => b.source === "builtin").length;
  const unbekannt = bots.filter((b) => !b.known).length;

  return (
    <section className="space-y-4">
      <div className={cn(KARTE, "flex flex-wrap items-center gap-4 px-5 py-4")}>
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-indigo-500/25 bg-indigo-500/10">
          <Bot className="h-[18px] w-[18px] text-indigo-400" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[18px] font-bold tracking-tight text-white">
            Vertraute Bots
          </h2>
          <p className="mt-0.5 text-[13px] text-slate-500">
            Diese Bots greift der Anti-Nuke nie an — auf allen Servern.
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

      {/* Warum das hier steht und nicht bei den Servern. */}
      <div className={cn(KARTE, "flex items-start gap-3 px-5 py-4")}>
        <Server className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
        <p className="text-[13px] leading-relaxed text-slate-500">
          Die Liste gilt für <strong className="text-slate-400">alle Server</strong>,
          auf denen der Bot ist. Server-Inhaber sehen sie in ihrem
          Anti-Nuke-Reiter, ändern können sie nur hier — sonst trüge jeder
          seinen Zweitbot ein und der Schutz wäre wirkungslos.
        </p>
      </div>

      {/* ── Eintragen ─────────────────────────────────────────────── */}
      <div className={cn(KARTE, "p-5")}>
        <h3 className="text-[15px] font-bold text-white">Bot hinzufügen</h3>
        <p className="mt-1 text-[13px] text-slate-500">
          Die Discord-ID des Bots — in Discord mit Rechtsklick auf den Bot,
          dann „ID kopieren“ (Entwicklermodus muss an sein).
        </p>

        <div className="mt-4 flex flex-wrap gap-3">
          <input
            value={neueId}
            onChange={(e) => setNeueId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") hinzufuegen();
            }}
            placeholder="z. B. 159985870458322944"
            inputMode="numeric"
            aria-label="Discord-ID des Bots"
            className="min-w-[220px] flex-1 rounded-xl border border-slate-800 bg-[#0e0e12] px-4 py-2.5 font-mono text-sm text-white placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
          />
          <input
            value={notiz}
            onChange={(e) => setNotiz(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") hinzufuegen();
            }}
            placeholder="Notiz (optional) — z. B. „MEE6“"
            aria-label="Notiz"
            className="min-w-[180px] flex-1 rounded-xl border border-slate-800 bg-[#0e0e12] px-4 py-2.5 text-sm text-white placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
          />
          <button
            type="button"
            onClick={hinzufuegen}
            disabled={!neueId.trim() || busy === "add"}
            className="flex shrink-0 items-center gap-2 rounded-xl bg-[#5865f2] px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-[#4752c4] disabled:opacity-40"
          >
            {busy === "add" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            Hinzufügen
          </button>
        </div>
      </div>

      {/* ── Die Liste ─────────────────────────────────────────────── */}
      <div className={cn(KARTE, "overflow-hidden")}>
        <div className="divide-y divide-slate-800/70">
          {bots.map((eintrag) => {
            const quelle = QUELLE[eintrag.source] || QUELLE.manual;
            const fest = eintrag.source !== "manual";
            return (
              <div
                key={eintrag.id}
                className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5"
              >
                {/* Profilbild — oder ein Platzhalter, wenn der Bot
                    dem Bot nie begegnet ist. Ein leerer Kreis ist
                    ehrlicher als ein erfundenes Bild. */}
                {eintrag.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={eintrag.avatar}
                    alt=""
                    width={36}
                    height={36}
                    className="h-9 w-9 shrink-0 rounded-full border border-slate-800 object-cover"
                  />
                ) : (
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-slate-800 bg-[#0e0e12]">
                    <Bot className="h-4 w-4 text-slate-600" />
                  </span>
                )}

                <div className="min-w-[180px] flex-1">
                  <p className="truncate text-[14px] font-semibold text-white">
                    {eintrag.name || eintrag.label || "Unbekannter Bot"}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[11px] text-slate-600">
                    {eintrag.id}
                    {eintrag.note ? ` · ${eintrag.note}` : ""}
                  </p>
                </div>

                <span
                  className={cn(
                    "shrink-0 rounded-lg border px-2.5 py-1 text-[12px] font-semibold",
                    quelle.ton,
                  )}
                >
                  {quelle.text}
                </span>

                <div className="flex w-[120px] shrink-0 justify-end">
                  {fest ? (
                    <span
                      className="flex items-center gap-1.5 text-[12px] text-slate-600"
                      title={
                        eintrag.source === "builtin"
                          ? "Ohne diesen Bot würde der Anti-Nuke den eigenen Rettungsbot bannen."
                          : `Steht in der Variablen ${envName} und lässt sich nur dort entfernen.`
                      }
                    >
                      <Lock className="h-3.5 w-3.5" />
                      Fest
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => entfernen(eintrag)}
                      disabled={busy === eintrag.id}
                      className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-[#0e0e12] px-3 py-2 text-[12px] font-semibold text-slate-400 transition-colors hover:border-rose-500/30 hover:text-rose-300 disabled:opacity-40"
                    >
                      {busy === eintrag.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                      Entfernen
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Ein Bot, den der University Bot nie gesehen hat, ist
          vermutlich auf keinem gemeinsamen Server — dann steht dort
          nur die ID. Das ist kein Fehler, sieht aber danach aus. */}
      {unbekannt > 0 && (
        <div className={cn(KARTE, "flex items-start gap-3 px-5 py-4")}>
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <p className="text-[13px] leading-relaxed text-slate-500">
            Bei {unbekannt}{" "}
            {unbekannt === 1 ? "Eintrag" : "Einträgen"} steht nur die ID:
            diese Bots sind auf keinem Server, den der University Bot sieht.
            Der Schutz gilt trotzdem — sobald sie irgendwo gemeinsam sind,
            erscheinen Name und Bild.
          </p>
        </div>
      )}

      <div className={cn(KARTE, "px-5 py-4")}>
        <p className="text-[13px] leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-400">
            {eingebaut} Einträge sind fest eingebaut:
          </span>{" "}
          Hauptbot, Vorlagen-Bot und Statusbot. Der Vorlagen-Bot baut nach
          einem Angriff Server wieder auf — dutzende Kanäle und Rollen in
          Sekunden, also genau die Form eines Nukes. Ohne ihn auf der Liste
          würde er mitten in der Rettung gebannt.
        </p>
      </div>
    </section>
  );
}
