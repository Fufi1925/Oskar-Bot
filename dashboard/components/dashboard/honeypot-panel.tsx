"use client";

/**
 * Honeypot: ein Köder-Kanal ganz oben, in den niemand schreiben soll.
 *
 * Einschalten genügt — den Rest macht der Bot: Kanal anlegen, ganz
 * nach oben schieben, Warnung hineinschreiben. Alles Weitere ist
 * freiwillig.
 *
 * Warum der Zähler hier nur beim Laden aktualisiert wird
 * ------------------------------------------------------
 * Live mitzuzählen hieße, im Sekundentakt zu fragen. Der Zähler, der
 * wirklich live sein muss, steht im Discord-Kanal selbst — der Bot
 * schreibt ihn nach jedem Treffer sofort neu. Hier reicht ein Blick
 * beim Öffnen, plus ein Knopf zum Neuladen.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowUpToLine,
  Ban,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

interface Kanal {
  id: string;
  name: string;
  category: string | null;
  can_send: boolean;
}

interface Rolle {
  id: string;
  name: string;
}

export function HoneypotPanel({ guildId }: { guildId: string }) {
  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);

  const [an, setAn] = useState(false);
  const [titel, setTitel] = useState("");
  const [text, setText] = useState("");
  const [eigenerKanal, setEigenerKanal] = useState("");
  const [logKanal, setLogKanal] = useState("");
  const [tage, setTage] = useState(1);
  const [weisseRollen, setWeisseRollen] = useState<string[]>([]);

  const uebernehmen = useCallback((antwort: any) => {
    setDaten(antwort);
    setAn(Boolean(antwort.enabled));
    setTitel(antwort.title || "");
    setText(antwort.text || "");
    setEigenerKanal(antwort.custom_channel_id || "");
    setLogKanal(antwort.log_channel_id || "");
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

  const umschalten = async () => {
    setBeschaeftigt(true);
    try {
      const antwort = await api.honeypotToggle(guildId, !an);
      uebernehmen(antwort);
      toast.success(
        !an
          ? `Honeypot an — #${antwort.channel_name || "Kanal"} steht bereit.`
          : "Honeypot aus. Der Kanal bleibt bestehen."
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
      const antwort = await api.honeypotSave(guildId, {
        title: titel,
        text,
        custom_channel_id: eigenerKanal || null,
        log_channel_id: logKanal || null,
        delete_days: tage,
        whitelist_roles: weisseRollen,
      });
      uebernehmen(antwort);
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

  const rolleUmschalten = (id: string) => {
    setWeisseRollen((bisher) =>
      bisher.includes(id) ? bisher.filter((r) => r !== id) : [...bisher, id]
    );
  };

  if (laedt) {
    return (
      <div className={cn(CARD, "flex items-center gap-3 text-slate-400")}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Wird geladen …
      </div>
    );
  }

  const kanaele: Kanal[] = daten?.channels || [];
  const rollen: Rolle[] = daten?.roles || [];
  const rechte = daten?.permissions || { ok: true, detail: "" };

  return (
    <div className="space-y-5">
      {/* ── Fehlende Rechte ganz oben ─────────────────────────────── */}
      {!rechte.ok && (
        <div className="flex gap-3 rounded-3xl border border-red-500/30 bg-red-500/5 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
          <div>
            <div className="font-semibold text-white">
              Der Honeypot kann so nichts tun
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

      {/* ── Hauptschalter ─────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-amber-500/15 p-2.5 text-2xl leading-none">
              🍯
            </div>
            <div>
              <h3 className="font-bold text-white">Honeypot</h3>
              <p className="mt-1 max-w-xl text-sm leading-relaxed text-slate-400">
                Ein Kanal <strong className="text-slate-200">ganz oben</strong>,
                den jeder sehen und beschreiben kann — mit einer deutlichen
                Warnung darin. Spam-Bots gehen die Kanalliste von oben durch
                und tappen hinein. Wer dort schreibt, wird{" "}
                <strong className="text-slate-200">softgebannt</strong>.
              </p>
            </div>
          </div>

          <button
            onClick={umschalten}
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

        {/* Zustand */}
        {an && (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-3">
              <div className="text-xs text-slate-500">Köder-Kanal</div>
              <div className="mt-0.5 truncate font-mono text-sm text-white">
                {daten?.channel_name ? `#${daten.channel_name}` : "—"}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-3">
              <div className="text-xs text-slate-500">Softbans insgesamt</div>
              <div className="mt-0.5 text-lg font-bold text-white">
                {Number(daten?.kicks || 0).toLocaleString("de-DE")}
              </div>
            </div>
            <div className="flex items-end gap-2">
              <button
                onClick={laden}
                disabled={beschaeftigt}
                className="flex-1 rounded-2xl border border-slate-800 bg-[#0f0f13] px-3 py-2.5 text-sm text-slate-300 transition hover:bg-white/[0.04] disabled:opacity-50"
              >
                <RefreshCw className="mr-1.5 inline h-3.5 w-3.5" />
                Neu laden
              </button>
              <button
                onClick={neuSenden}
                disabled={beschaeftigt}
                className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-2.5 text-slate-300 transition hover:bg-white/[0.04] disabled:opacity-50"
                title="Nachricht neu senden, falls sie gelöscht wurde"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {an && daten?.channel_missing && (
          <div className="mt-3 flex gap-2 rounded-2xl border border-amber-500/25 bg-amber-500/5 p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <p className="text-xs text-amber-200/80">
              Der eingetragene Kanal existiert nicht mehr. Schalte einmal aus
              und wieder ein — der Bot legt ihn dann neu an.
            </p>
          </div>
        )}
      </div>

      {/* ── Wie der Zähler live bleibt ────────────────────────────── */}
      {an && (
        <div className="flex gap-3 rounded-3xl border border-slate-800 bg-[#0f0f13] p-4">
          <ArrowUpToLine className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <p className="text-xs leading-relaxed text-slate-400">
            Der Knopf unter der Warnung im Kanal zeigt die Zahl der Softbans
            und wird nach jedem Treffer sofort aktualisiert. Der Kanal wird
            beim Einschalten automatisch ganz nach oben geschoben — außer du
            wählst unten einen eigenen.
          </p>
        </div>
      )}

      {/* ── Text der Warnung ──────────────────────────────────────── */}
      <div className={CARD}>
        <h4 className="mb-4 font-bold text-white">Die Warnung im Kanal</h4>

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

        <label className="mt-4 block text-xs font-semibold uppercase tracking-wider text-slate-500">
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
          **Sternchen** machen den Text fett — Discord-Formatierung
          funktioniert.
        </p>
      </div>

      {/* ── Kanäle ────────────────────────────────────────────────── */}
      <div className={CARD}>
        <h4 className="mb-4 font-bold text-white">Kanäle</h4>

        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
          Eigener Köder-Kanal <span className="text-slate-600">(freiwillig)</span>
        </label>
        <select
          value={eigenerKanal}
          onChange={(e) => setEigenerKanal(e.target.value)}
          className="mt-2 w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50"
        >
          <option value="">
            Der Bot legt {daten?.defaults?.channel_name
              ? `#${daten.defaults.channel_name}`
              : "einen Kanal"}{" "}
            selbst an
          </option>
          {kanaele.map((k) => (
            <option key={k.id} value={k.id}>
              #{k.name}
              {k.category ? ` — ${k.category}` : ""}
            </option>
          ))}
        </select>
        <p className="mt-1.5 text-xs text-slate-600">
          Wählst du einen eigenen, wird er <strong>nicht</strong> verschoben —
          du hast ihn ja bewusst dort abgelegt. Achte selbst darauf, dass er
          weit oben steht.
        </p>

        <label className="mt-5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
          Log-Kanal <span className="text-slate-600">(freiwillig)</span>
        </label>
        <select
          value={logKanal}
          onChange={(e) => setLogKanal(e.target.value)}
          className="mt-2 w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50"
        >
          <option value="">Kein Log</option>
          {kanaele.map((k) => (
            <option key={k.id} value={k.id}>
              #{k.name}
              {k.can_send ? "" : "  (Bot darf hier nicht schreiben)"}
            </option>
          ))}
        </select>
        <p className="mt-1.5 text-xs text-slate-600">
          Hier landet jeder Treffer mit Namen und dem neuen Zählerstand. Ohne
          Log-Kanal passiert alles lautlos.
        </p>
      </div>

      {/* ── Strafe ────────────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="mb-4 flex items-center gap-2">
          <Ban className="h-4 w-4 text-red-400" />
          <h4 className="font-bold text-white">Softban</h4>
        </div>

        <p className="mb-4 text-sm leading-relaxed text-slate-400">
          Bannen und sofort wieder entbannen. Das entfernt die Person und
          löscht ihren Spam — zurückkommen kann sie mit einem neuen
          Einladungslink.
        </p>

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

        <div className="mt-4 flex gap-2.5 rounded-2xl border border-slate-800 bg-[#0f0f13] p-3">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <p className="text-xs leading-relaxed text-slate-500">
            Kann der Bot jemanden nicht bannen — höhere Rolle, fehlendes
            Recht, Server-Inhaber —, passiert <strong>gar nichts</strong>:
            keine Fehlermeldung im Kanal, keine Nachricht an dich. Nur die
            Zeile im Log-Kanal, falls eingestellt. So verrät die Falle nicht,
            wo ihre Grenzen liegen.
          </p>
        </div>
      </div>

      {/* ── Whitelist ─────────────────────────────────────────────── */}
      <div className={CARD}>
        <h4 className="font-bold text-white">Rollen ausnehmen</h4>
        <p className="mt-1 mb-4 text-sm text-slate-400">
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
                  onClick={() => rolleUmschalten(r.id)}
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

        {weisseRollen.length > 0 && (
          <button
            onClick={() => setWeisseRollen([])}
            className="mt-3 inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300"
          >
            <Trash2 className="h-3 w-3" />
            Alle entfernen ({weisseRollen.length})
          </button>
        )}
      </div>

      {/* ── Speichern ─────────────────────────────────────────────── */}
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
