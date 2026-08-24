"use client";

/**
 * Support-Warteraum: vier Einstellungen, mehr nicht.
 *
 *     an/aus · Warteraum-Kanal · Meldekanal · Team-Rolle
 *
 * Warum so wenig
 * --------------
 * Vorher standen hier acht Felder: eigene Ansage, Musik-URL, Dauer,
 * Cooldown, Erinnerungsabstand, Zahl der Erinnerungen,
 * Ping-trotz-Team, Meldekanal. Jedes davon war ein Weg, das System
 * kaputt einzustellen — eine Musik-URL, die Lavalink nicht findet;
 * ein Cooldown von einer Stunde, nach dem sich niemand mehr meldet.
 *
 * Jetzt steht alles Übrige fest. Was genau, ist unten nachlesbar —
 * aber nicht änderbar.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  Clock,
  Headphones,
  Info,
  Loader2,
  Music,
  Save,
  Users,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

interface VoiceChannel {
  id: string;
  name: string;
  category: string | null;
  can_join: boolean;
  can_speak: boolean;
}

interface TextChannel {
  id: string;
  name: string;
  can_send: boolean;
}

interface Rolle {
  id: string;
  name: string;
}

interface Wartend {
  user_id: string;
  name: string;
  avatar: string | null;
  since: number;
}

/** Wie lange jemand schon wartet. */
function wartetSeit(since: number) {
  const sekunden = Math.max(0, Math.floor(Date.now() / 1000 - since));
  if (sekunden < 60) return `${sekunden}s`;
  const minuten = Math.floor(sekunden / 60);
  if (minuten < 60) return `${minuten} min`;
  return `${Math.floor(minuten / 60)} h ${minuten % 60} min`;
}

export function SupportQueuePanel({ guildId }: { guildId: string }) {
  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);

  const [an, setAn] = useState(false);
  const [kanal, setKanal] = useState("");
  const [meldeKanal, setMeldeKanal] = useState("");
  const [rolle, setRolle] = useState("");

  const uebernehmen = useCallback((antwort: any) => {
    setDaten(antwort);
    setAn(Boolean(antwort.enabled));
    setKanal(antwort.channel_id || "");
    setMeldeKanal(antwort.notify_channel_id || "");
    setRolle(antwort.staff_role_id || "");
  }, []);

  const laden = useCallback(async () => {
    try {
      uebernehmen(await api.supportQueue(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Konnte die Einstellungen nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, [guildId, uebernehmen]);

  useEffect(() => {
    laden();
  }, [laden]);

  // Wer wartet, ändert sich laufend. Alle 15 Sekunden nachsehen —
  // häufiger wäre für eine Liste mit selten mehr als drei Einträgen
  // verschwendet.
  useEffect(() => {
    if (!an) return;
    const timer = setInterval(async () => {
      try {
        const frisch = await api.supportQueue(guildId);
        setDaten((alt: any) => ({ ...alt, waiting: frisch.waiting }));
      } catch {
        /* still — ein Aussetzer darf die Seite nicht stören */
      }
    }, 15000);
    return () => clearInterval(timer);
  }, [an, guildId]);

  const speichern = async (zusatz: Record<string, unknown> = {}) => {
    setBeschaeftigt(true);
    try {
      uebernehmen(
        await api.supportQueueSave(guildId, {
          enabled: an,
          channel_id: kanal || null,
          notify_channel_id: meldeKanal || null,
          staff_role_id: rolle || null,
          ...zusatz,
        })
      );
      toast.success("Gespeichert.");
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const umschalten = async () => {
    const neu = !an;
    setAn(neu);
    await speichern({ enabled: neu });
  };

  if (laedt) {
    return (
      <div className={cn(CARD, "flex items-center gap-3 text-slate-400")}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Wird geladen …
      </div>
    );
  }

  const sprachKanaele: VoiceChannel[] = daten?.voice_channels || [];
  const textKanaele: TextChannel[] = daten?.text_channels || [];
  const rollen: Rolle[] = daten?.roles || [];
  const wartende: Wartend[] = daten?.waiting || [];
  const fest = daten?.fixed || {};
  const lavalink = daten?.lavalink || { ready: true, detail: "" };

  const gewaehlterKanal = sprachKanaele.find((k) => k.id === kanal);

  return (
    <div className="space-y-4">
      {/* ── Kein Lavalink: das muss ganz oben stehen ──────────────── */}
      {!lavalink.ready && (
        <div className="flex gap-3 rounded-3xl border border-amber-500/25 bg-amber-500/5 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          <div>
            <div className="font-semibold text-white">Keine Wartemusik</div>
            <p className="mt-1 text-sm text-amber-200/80">{lavalink.detail}</p>
          </div>
        </div>
      )}

      {/* ── 1. An oder aus ────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-primary/15 p-2.5">
              <Headphones className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h3 className="font-bold text-white">Support-Warteraum</h3>
              <p className="mt-1 max-w-lg text-sm leading-relaxed text-slate-400">
                Betritt jemand den Warteraum, kommt der Bot dazu und spielt
                Wartemusik. Das Team bekommt gleichzeitig eine Meldung.
              </p>
            </div>
          </div>

          <button
            onClick={umschalten}
            disabled={beschaeftigt || (!an && !kanal)}
            title={!an && !kanal ? "Wähle zuerst einen Warteraum-Kanal" : ""}
            className={cn(
              "shrink-0 rounded-2xl px-5 py-3 text-sm font-semibold transition disabled:opacity-40",
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
              {daten?.channel_name ? `#${daten.channel_name}` : "—"}
            </span>
            <span className="text-sm text-slate-500">
              {wartende.length === 0
                ? "niemand wartet"
                : `${wartende.length} ${wartende.length === 1 ? "Person wartet" : "Personen warten"}`}
            </span>
          </div>
        )}

        {daten?.channel_missing && (
          <div className="mt-3 flex gap-2 rounded-2xl border border-amber-500/25 bg-amber-500/5 p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <p className="text-xs text-amber-200/80">
              Der eingestellte Kanal existiert nicht mehr. Wähle unten einen
              neuen.
            </p>
          </div>
        )}
      </div>

      {/* ── 2. Warteraum-Kanal ────────────────────────────────────── */}
      <div className={CARD}>
        <div className="mb-3 flex items-center gap-2">
          <Volume2 className="h-4 w-4 text-slate-500" />
          <h4 className="text-sm font-semibold text-white">Warteraum-Kanal</h4>
        </div>
        <select
          value={kanal}
          onChange={(e) => setKanal(e.target.value)}
          className="w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50"
        >
          <option value="">Keiner ausgewählt</option>
          {sprachKanaele.map((k) => (
            <option key={k.id} value={k.id}>
              {k.name}
              {k.category ? ` — ${k.category}` : ""}
              {k.can_join ? "" : "  (Bot darf nicht hinein)"}
            </option>
          ))}
        </select>
        {gewaehlterKanal && !gewaehlterKanal.can_join && (
          <p className="mt-2 flex items-start gap-1.5 text-xs text-red-300">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            Dem Bot fehlt das Recht, diesen Kanal zu betreten — er wird nie
            erscheinen.
          </p>
        )}
        {gewaehlterKanal?.can_join && !gewaehlterKanal.can_speak && (
          <p className="mt-2 flex items-start gap-1.5 text-xs text-amber-300">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            Der Bot darf hinein, aber nicht sprechen — es bleibt still.
          </p>
        )}
      </div>

      {/* ── 3. Meldekanal ─────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="mb-3 flex items-center gap-2">
          <Bell className="h-4 w-4 text-slate-500" />
          <h4 className="text-sm font-semibold text-white">Meldekanal</h4>
        </div>
        <select
          value={meldeKanal}
          onChange={(e) => setMeldeKanal(e.target.value)}
          className="w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50"
        >
          <option value="">Keine Meldung</option>
          {textKanaele.map((k) => (
            <option key={k.id} value={k.id}>
              #{k.name}
              {k.can_send ? "" : "  (Bot darf hier nicht schreiben)"}
            </option>
          ))}
        </select>
        <p className="mt-2 text-xs text-slate-600">
          Hier meldet der Bot, wenn jemand wartet. Ohne Meldekanal merkt das
          Team nichts davon.
        </p>
      </div>

      {/* ── 4. Team-Rolle ─────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="mb-3 flex items-center gap-2">
          <Users className="h-4 w-4 text-slate-500" />
          <h4 className="text-sm font-semibold text-white">Team-Rolle</h4>
        </div>
        <select
          value={rolle}
          onChange={(e) => setRolle(e.target.value)}
          className="w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50"
        >
          <option value="">Keine Erwähnung</option>
          {rollen.map((r) => (
            <option key={r.id} value={r.id}>
              @{r.name}
            </option>
          ))}
        </select>
        <p className="mt-2 text-xs text-slate-600">
          Diese Rolle wird in der Meldung erwähnt. Sitzt bereits jemand mit
          ihr im Warteraum, bleibt die Meldung aus — es ist ja schon jemand
          da.
        </p>
      </div>

      <button
        onClick={() => speichern()}
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

      {/* ── Wer wartet gerade ─────────────────────────────────────── */}
      {an && wartende.length > 0 && (
        <div className={CARD}>
          <div className="mb-3 flex items-center gap-2">
            <Clock className="h-4 w-4 text-slate-500" />
            <h4 className="text-sm font-semibold text-white">
              Wartet gerade ({wartende.length})
            </h4>
          </div>
          <div className="space-y-2">
            {wartende.map((w) => (
              <div
                key={w.user_id}
                className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-[#0f0f13] p-3"
              >
                {w.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={w.avatar}
                    alt=""
                    className="h-7 w-7 rounded-full"
                  />
                ) : (
                  <div className="h-7 w-7 rounded-full bg-slate-800" />
                )}
                <span className="flex-1 truncate text-sm text-white">
                  {w.name}
                </span>
                <span className="text-xs text-slate-500">
                  {wartetSeit(w.since)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Was fest eingestellt ist ──────────────────────────────── */}
      <div className={cn(CARD, "border-slate-800/60")}>
        <div className="flex gap-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Fest eingestellt
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
              Diese Werte lassen sich nicht ändern — sie sind erprobt, und
              jede Einstellung mehr war bisher ein Weg, den Warteraum kaputt
              zu konfigurieren.
            </p>
            <ul className="mt-3 space-y-1.5 text-xs text-slate-500">
              <li className="flex items-start gap-2">
                <Music className="mt-0.5 h-3 w-3 shrink-0 text-slate-600" />
                <span>
                  Wartemusik:{" "}
                  <code className="rounded bg-black/30 px-1 text-slate-400">
                    {fest.music_file || "warteraum.mp3"}
                  </code>{" "}
                  — zum Austauschen die Datei in{" "}
                  <code className="rounded bg-black/30 px-1 text-slate-400">
                    dashboard/public/
                  </code>{" "}
                  ersetzen.
                </span>
              </li>
              <li>
                Ein Durchgang dauert {fest.music_seconds ?? 30} Sekunden, dann
                beginnt sie von vorn.
              </li>
              <li>
                Nach einer Meldung ist{" "}
                {Math.round((fest.ping_cooldown ?? 120) / 60)} Minuten Ruhe —
                sonst löst jedes Verbindungswackeln eine neue aus.
              </li>
              <li>
                Reagiert niemand, wird nach{" "}
                {Math.round((fest.reminder_seconds ?? 300) / 60)} Minuten
                erinnert, höchstens {fest.max_reminders ?? 3} Mal.
              </li>
              <li>Der Text der Meldung ist nicht bearbeitbar.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
