"use client";

/**
 * Honeypot: ein Köder-Kanal ganz oben, in den niemand schreiben soll.
 *
 * Aufbau nach der Rückmeldung „besser, simpler, einfacher"
 * -------------------------------------------------------
 * Vorher standen fünf Karten untereinander, alle gleich wichtig
 * aussehend, und man musste an vier davon vorbeiscrollen, um zum
 * Speichern-Knopf zu kommen. Dabei ist für die meisten nur eines
 * relevant: der Schalter.
 *
 * Jetzt:
 *   * Oben der Schalter und der Zustand. Mehr braucht der Normalfall
 *     nicht.
 *   * Alles Weitere liegt in zugeklappten Bereichen. Wer nichts
 *     ändern will, sieht sie als eine Zeile.
 *   * Gespeichert wird beim Zuklappen bzw. über einen Knopf im
 *     Bereich selbst — kein Suchen nach einem Knopf ganz unten.
 *
 * Der Log-Kanal steht nicht mehr hier, sondern gesammelt unter
 * Bot-Logs. Zwei Felder für denselben Wert laufen auseinander.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ChevronDown,
  Loader2,
  MessageSquare,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LogUmgezogen } from "@/components/dashboard/log-umgezogen";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl";

interface Rolle {
  id: string;
  name: string;
}

/** Ein zugeklappter Bereich. */
function Bereich({
  titel,
  zusammenfassung,
  icon: Icon,
  offen,
  aufKlick,
  children,
}: {
  titel: string;
  zusammenfassung: string;
  icon: any;
  offen: boolean;
  aufKlick: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className={cn(CARD, "overflow-hidden")}>
      <button
        onClick={aufKlick}
        className="flex w-full items-center gap-3 p-4 text-left transition hover:bg-white/[0.02]"
      >
        <Icon className="h-4 w-4 shrink-0 text-slate-500" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-white">{titel}</div>
          <p className="mt-0.5 truncate text-xs text-slate-500">
            {zusammenfassung}
          </p>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-slate-500 transition-transform",
            offen && "rotate-180"
          )}
        />
      </button>
      {offen && (
        <div className="space-y-4 border-t border-slate-800 p-4">{children}</div>
      )}
    </div>
  );
}

export function HoneypotPanel({ guildId }: { guildId: string }) {
  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);
  const [offen, setOffen] = useState<string[]>([]);

  const [titel, setTitel] = useState("");
  const [text, setText] = useState("");
  const [eigenerKanal, setEigenerKanal] = useState("");
  const [tage, setTage] = useState(1);
  const [weisseRollen, setWeisseRollen] = useState<string[]>([]);

  const uebernehmen = useCallback((antwort: any) => {
    setDaten(antwort);
    setTitel(antwort.title || "");
    setText(antwort.text || "");
    setEigenerKanal(antwort.custom_channel_id || "");
    setTage(Number(antwort.delete_days ?? 1));
    setWeisseRollen(antwort.whitelist_roles || []);
  }, []);

  const laden = useCallback(async () => {
    try {
      uebernehmen(await api.honeypot(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Konnte die Einstellungen nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, [guildId, uebernehmen]);

  useEffect(() => {
    laden();
  }, [laden]);

  const umschalten = (name: string) =>
    setOffen((b) =>
      b.includes(name) ? b.filter((x) => x !== name) : [...b, name]
    );

  const anAus = async () => {
    setBeschaeftigt(true);
    try {
      const antwort = await api.honeypotToggle(guildId, !daten.enabled);
      uebernehmen(antwort);
      toast.success(
        !daten.enabled
          ? `Läuft — #${antwort.channel_name || "Kanal"} steht bereit.`
          : "Ausgeschaltet. Der Kanal bleibt bestehen."
      );
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const speichern = async () => {
    setBeschaeftigt(true);
    try {
      uebernehmen(
        await api.honeypotSave(guildId, {
          title: titel,
          text,
          custom_channel_id: eigenerKanal || null,
          delete_days: tage,
          whitelist_roles: weisseRollen,
        })
      );
      toast.success("Gespeichert.");
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const neuSenden = async () => {
    setBeschaeftigt(true);
    try {
      uebernehmen(await api.honeypotResend(guildId));
      toast.success("Nachricht neu gesendet.");
    } catch (err: any) {
      toast.error(err?.message || "Senden fehlgeschlagen.");
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

  const an = Boolean(daten?.enabled);
  const rollen: Rolle[] = daten?.roles || [];
  const kanaele = daten?.channels || [];
  const rechte = daten?.permissions || { ok: true, detail: "" };

  const tageText =
    tage === 0
      ? "keine Nachrichten löschen"
      : tage === 1
        ? "Nachrichten vom letzten Tag löschen"
        : `Nachrichten aus ${tage} Tagen löschen`;

  return (
    <div className="space-y-4">
      {/* ── Fehlende Rechte zuerst ────────────────────────────────── */}
      {!rechte.ok && (
        <div className="flex gap-3 rounded-3xl border border-red-500/30 bg-red-500/5 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
          <div>
            <div className="font-semibold text-white">
              So kann der Honeypot nichts tun
            </div>
            <p className="mt-1 text-sm text-red-200/80">{rechte.detail}</p>
          </div>
        </div>
      )}
      {rechte.ok && rechte.detail && (
        <div className="flex gap-3 rounded-3xl border border-amber-500/25 bg-amber-500/5 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          <p className="text-sm text-amber-200/80">{rechte.detail}</p>
        </div>
      )}

      {/* ── Der Schalter. Für die meisten das Einzige. ────────────── */}
      <div className={cn(CARD, "p-5")}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-amber-500/15 p-2.5 text-2xl leading-none">
              🍯
            </div>
            <div>
              <h3 className="font-bold text-white">Honeypot</h3>
              <p className="mt-1 max-w-lg text-sm leading-relaxed text-slate-400">
                Ein Kanal ganz oben, in den niemand schreiben soll. Spam-Bots
                tappen hinein und werden softgebannt. Einschalten genügt — den
                Kanal legt der Bot selbst an.
              </p>
            </div>
          </div>

          <button
            onClick={anAus}
            disabled={beschaeftigt}
            className={cn(
              "shrink-0 rounded-2xl px-5 py-3 text-sm font-semibold transition disabled:opacity-50",
              an
                ? "bg-red-500/15 text-red-300 hover:bg-red-500/25"
                : "bg-primary text-white hover:brightness-110"
            )}
          >
            {beschaeftigt ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : an ? (
              "Ausschalten"
            ) : (
              "Einschalten"
            )}
          </button>
        </div>

        {an && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-800 bg-[#0f0f13] p-3">
            <span className="flex items-center gap-1.5 text-sm text-emerald-300">
              <CheckCircle2 className="h-4 w-4" />
              Läuft
            </span>
            <span className="font-mono text-sm text-slate-300">
              #{daten?.channel_name || "—"}
            </span>
            <span className="text-sm text-slate-500">
              {Number(daten?.kicks || 0).toLocaleString("de-DE")} Softbans
            </span>
            <div className="ml-auto flex gap-1.5">
              <button
                onClick={laden}
                disabled={beschaeftigt}
                className="rounded-xl border border-slate-800 p-2 text-slate-400 transition hover:bg-white/[0.04] disabled:opacity-50"
                title="Neu laden"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={neuSenden}
                disabled={beschaeftigt}
                className="rounded-xl border border-slate-800 p-2 text-slate-400 transition hover:bg-white/[0.04] disabled:opacity-50"
                title="Nachricht neu senden, falls sie gelöscht wurde"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}

        {an && daten?.channel_missing && (
          <div className="mt-3 flex gap-2 rounded-2xl border border-amber-500/25 bg-amber-500/5 p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <p className="text-xs text-amber-200/80">
              Der Kanal existiert nicht mehr. Einmal aus- und wieder
              einschalten legt ihn neu an.
            </p>
          </div>
        )}
      </div>

      {/* ── Alles Weitere: zugeklappt ─────────────────────────────── */}
      <Bereich
        titel="Text der Warnung"
        zusammenfassung={titel || daten?.defaults?.title || "Standardtext"}
        icon={MessageSquare}
        offen={offen.includes("text")}
        aufKlick={() => umschalten("text")}
      >
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
            Überschrift
          </label>
          <input
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            maxLength={daten?.limits?.title || 200}
            placeholder={daten?.defaults?.title}
            className="mt-2 w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
            Text
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={daten?.limits?.text || 1500}
            rows={3}
            placeholder={daten?.defaults?.text}
            className="mt-2 w-full resize-y rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50"
          />
          <p className="mt-1.5 text-xs text-slate-600">
            **Sternchen** machen den Text fett.
          </p>
        </div>
      </Bereich>

      <Bereich
        titel="Strafe"
        zusammenfassung={`Softban, ${tageText}`}
        icon={Ban}
        offen={offen.includes("strafe")}
        aufKlick={() => umschalten("strafe")}
      >
        <p className="text-sm leading-relaxed text-slate-400">
          Softban heißt: bannen und sofort wieder entbannen. Das entfernt die
          Person und löscht ihren Spam — zurückkommen kann sie mit einem neuen
          Einladungslink.
        </p>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
            Nachrichten löschen
          </label>
          <select
            value={tage}
            onChange={(e) => setTage(Number(e.target.value))}
            className="mt-2 w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50 sm:max-w-xs"
          >
            <option value={0}>Keine löschen</option>
            <option value={1}>Vom letzten Tag</option>
            <option value={3}>Aus 3 Tagen</option>
            <option value={7}>Aus 7 Tagen</option>
          </select>
        </div>
        <div className="flex gap-2.5 rounded-2xl border border-slate-800 bg-[#0f0f13] p-3">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <p className="text-xs leading-relaxed text-slate-500">
            Kann der Bot jemanden nicht bannen — höhere Rolle, fehlendes Recht,
            Server-Inhaber —, passiert <strong>gar nichts</strong>. Keine
            Fehlermeldung, keine Nachricht. So verrät die Falle nicht, wo ihre
            Grenzen liegen.
          </p>
        </div>
      </Bereich>

      <Bereich
        titel="Ausnahmen"
        zusammenfassung={
          weisseRollen.length === 0
            ? "Nur Bots und der Server-Inhaber"
            : `${weisseRollen.length} Rolle${weisseRollen.length === 1 ? "" : "n"} ausgenommen`
        }
        icon={Users}
        offen={offen.includes("rollen")}
        aufKlick={() => umschalten("rollen")}
      >
        <p className="text-sm text-slate-400">
          Wer eine dieser Rollen hat, darf dort schreiben, ohne bestraft zu
          werden. Bots und der Server-Inhaber sind immer ausgenommen.
        </p>
        {rollen.length === 0 ? (
          <p className="text-sm text-slate-600">Keine Rollen gefunden.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {rollen.map((r) => {
              const gewaehlt = weisseRollen.includes(r.id);
              return (
                <button
                  key={r.id}
                  onClick={() =>
                    setWeisseRollen((b) =>
                      b.includes(r.id)
                        ? b.filter((x) => x !== r.id)
                        : [...b, r.id]
                    )
                  }
                  className={cn(
                    "rounded-xl border px-3 py-1.5 text-xs transition",
                    gewaehlt
                      ? "border-primary/50 bg-primary/15 text-white"
                      : "border-slate-800 bg-[#0f0f13] text-slate-400 hover:bg-white/[0.04]"
                  )}
                >
                  {gewaehlt && (
                    <CheckCircle2 className="mr-1 inline h-3 w-3 text-primary" />
                  )}
                  @{r.name}
                </button>
              );
            })}
          </div>
        )}
      </Bereich>

      <Bereich
        titel="Eigener Kanal"
        zusammenfassung={
          eigenerKanal
            ? kanaele.find((k: any) => k.id === eigenerKanal)?.name
              ? `#${kanaele.find((k: any) => k.id === eigenerKanal).name}`
              : "Eigener Kanal gewählt"
            : "Der Bot legt den Kanal selbst an"
        }
        icon={MessageSquare}
        offen={offen.includes("kanal")}
        aufKlick={() => umschalten("kanal")}
      >
        <select
          value={eigenerKanal}
          onChange={(e) => setEigenerKanal(e.target.value)}
          className="w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50"
        >
          <option value="">
            Der Bot legt #{daten?.defaults?.channel_name} selbst an
          </option>
          {kanaele.map((k: any) => (
            <option key={k.id} value={k.id}>
              #{k.name}
              {k.category ? ` — ${k.category}` : ""}
            </option>
          ))}
        </select>
        <p className="text-xs text-slate-600">
          Ein selbst gewählter Kanal wird <strong>nicht</strong> nach oben
          verschoben. Achte darauf, dass er weit oben steht — Spam-Bots
          schreiben in den erstbesten Kanal von oben.
        </p>
      </Bereich>

      {/* Der Log-Kanal ist umgezogen. */}
      <LogUmgezogen
        guildId={guildId}
        logKey="honeypot"
        was="Wer softgebannt wurde"
      />

      <button
        onClick={speichern}
        disabled={beschaeftigt}
        className="inline-flex items-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white transition hover:brightness-110 disabled:opacity-50"
      >
        {beschaeftigt ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" />
        )}
        Speichern
      </button>
    </div>
  );
}
