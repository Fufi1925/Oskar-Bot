"use client";

/**
 * Der Musik-Reiter.
 *
 * Drei Bereiche, von oben nach unten:
 *
 *   1. **Einstellungen** -- Stammkanal, Dauerbetrieb, Lautstärke.
 *   2. **Playlists** -- anlegen, Titel ansehen, starten, löschen.
 *   3. **Live** -- was gerade läuft: Cover, Titel, Fortschritt,
 *      Warteschlange, und die Knöpfe dazu.
 *
 * ── Warum die Zeit im Browser weiterläuft ───────────────────────────
 *
 * Der Fortschritt kommt vom Bot, aber nur alle fünf Sekunden. Würde
 * die Anzeige nur darauf warten, spränge sie in Fünf-Sekunden-Stufen.
 * Zwischen zwei Abfragen zählt der Browser deshalb selbst weiter --
 * und korrigiert sich, sobald eine neue Zahl kommt.
 *
 * Der Bot schickt dazu `measured_at` mit. Ohne diesen Zeitstempel
 * liefe der Balken nach einem langsamen Aufruf vor: die Position wäre
 * dann schon eine Sekunde alt, und der Browser rechnete trotzdem ab
 * dem Moment des Empfangs weiter.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ListMusic, Loader2, LogOut, Music, Pause, Play, Plus, RefreshCw,
  SkipForward, Trash2, Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InlineToggle } from "@/components/dashboard/form-elements";

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";
const INPUT =
  "w-full bg-[#0a1628] border border-slate-800 rounded-xl px-4 py-3 text-sm " +
  "text-white placeholder:text-slate-600 focus:outline-none " +
  "focus:border-primary/50 transition-colors";

/** Millisekunden als `m:ss`. */
function clock(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) ms = 0;
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** Millisekunden als `1 h 23 min` -- für eine ganze Playlist. */
function duration(ms: number): string {
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && (
        <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>
      )}
    </div>
  );
}

export function MusicPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [live, setLive] = useState<any>(null);

  // Der Stand, den der Browser zwischen zwei Abfragen selbst hochzählt.
  const [tick, setTick] = useState(0);

  // Playlist anlegen
  const [newName, setNewName] = useState("");
  const [newQuery, setNewQuery] = useState("");
  // Welche Playlist ist aufgeklappt, und was soll dort hinein?
  const [open, setOpen] = useState<number | null>(null);
  const [addQuery, setAddQuery] = useState("");

  // Der Regler beim Ziehen. Ohne diesen Zwischenstand springt er
  // zurück, sobald die nächste Abfrage die alte Zahl bringt -- die
  // Änderung ist ja noch nicht abgeschickt.
  const [volumeDraft, setVolumeDraft] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const answer = await api.music(guildId);
      setData(answer);
      setLive(answer.live);
    } catch (error: any) {
      toast.error(error?.message || "Die Musik-Einstellungen ließen sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    load();
  }, [load]);

  // Den Live-Zustand regelmäßig nachfragen.
  //
  // Fünf Sekunden sind ein Kompromiss: häufiger belastet den Bot ohne
  // sichtbaren Gewinn, seltener und der Titelwechsel fällt auf.
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        setLive(await api.musicLive(guildId));
      } catch {
        // Ein fehlgeschlagener Abruf ist kein Grund für eine Meldung --
        // er wiederholt sich in fünf Sekunden von selbst.
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [guildId]);

  // Und dazwischen selbst weiterzählen, damit die Zeit flüssig läuft.
  useEffect(() => {
    if (!live?.playing || live?.paused) return;
    const timer = setInterval(() => setTick((old) => old + 1), 500);
    return () => clearInterval(timer);
  }, [live?.playing, live?.paused]);

  const save = async (patch: any) => {
    setBusy("settings");
    try {
      const answer = await api.musicSave(guildId, patch);
      setData((old: any) => ({ ...old, settings: answer.settings }));
      toast.success("Gespeichert.");
    } catch (error: any) {
      toast.error(error?.message || "Das ließ sich nicht speichern.");
    } finally {
      setBusy("");
    }
  };

  const control = async (action: string, value?: number) => {
    setBusy(action);
    try {
      const answer = await api.musicControl(guildId, action, value);
      if (answer?.live) setLive(answer.live);

      // Der Bot hat die Zahl jetzt -- der Entwurf hat ausgedient.
      // Ohne dieses Zurücksetzen bliebe er für immer stehen und die
      // Anzeige folgte dem Bot nie wieder, etwa wenn jemand im Chat
      // `>volume` benutzt.
      if (action === "volume") setVolumeDraft(null);

      // Die gespeicherte Lautstärke wandert mit, damit die Anzeige
      // auch stimmt, wenn der Bot später in keinem Kanal mehr ist.
      if (action === "volume" && typeof value === "number") {
        setData((old: any) =>
          old ? { ...old, settings: { ...old.settings, volume: value } } : old
        );
      }
    } catch (error: any) {
      toast.error(error?.message || "Das hat nicht geklappt.");
      // Auch im Fehlerfall zurück: sonst zeigt der Regler dauerhaft
      // etwas an, das nie angekommen ist.
      if (action === "volume") setVolumeDraft(null);
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return (
      <div className={cn(CARD, "flex items-center justify-center py-16")}>
        <Loader2 className="h-6 w-6 text-primary animate-spin opacity-50" />
      </div>
    );
  }

  if (!data) return null;

  const settings = data.settings || {};
  // Der gewählte Kanal als ganzer Eintrag, nicht nur seine Nummer --
  // für die Zeile darunter, die Kategorie und Rechte mit anzeigt.
  // Beide Seiten als Text vergleichen.
  //
  // Discord-IDs sind 18- bis 19-stellig und damit größer als
  // `Number.MAX_SAFE_INTEGER` (9007199254740991). Kämen sie als Zahl
  // an, hätte JSON.parse sie schon gerundet -- aus ...370 würde
  // ...300, und dieser Vergleich fände nie etwas. Der Bot schickt sie
  // deshalb als Zeichenkette; `String()` hier ist der Gürtel zum
  // Hosenträger, falls doch einmal eine Zahl durchkommt.
  const chosen = (data.channels || []).find(
    (entry: any) =>
      String(entry.id) === String(settings.channel_id ?? "")
  );

  // Beim Ziehen der Entwurf, sonst der Stand vom Bot -- und solange
  // er in keinem Kanal ist, die gespeicherte Voreinstellung.
  const volumeShown =
    volumeDraft ?? (live?.connected ? live.volume : settings.volume) ?? 60;
  const playlists = data.playlists || [];
  const limits = data.limits || {};
  const lavalink = data.lavalink || {};

  // Der gerechnete Stand: gemeldete Position plus die Zeit, die seit
  // der Messung vergangen ist.
  const track = live?.track || {};
  const measuredAgo = live?.measured_at
    ? Math.max(0, Date.now() / 1000 - live.measured_at) * 1000
    : 0;
  const position =
    live?.playing && !live?.paused
      ? Math.min((live?.position || 0) + measuredAgo, track.length || 0)
      : live?.position || 0;
  const percent = track.length ? Math.min(100, (position / track.length) * 100) : 0;
  void tick; // nur, damit das Neuzeichnen ausgelöst wird

  return (
    <div className="space-y-5">
      {/* ── Ohne Lavalink geht nichts ───────────────────────── */}
      {!lavalink.ready && (
        <div className="rounded-2xl bg-amber-500/[0.07] border border-amber-500/25 p-4 flex gap-3">
          <Volume2 className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-[13px] font-bold text-amber-200">
              Kein Audio-Dienst verbunden
            </p>
            <p className="text-[12px] text-amber-200/70 mt-1 leading-relaxed">
              {lavalink.detail}
            </p>
          </div>
        </div>
      )}

      {/* ── Status auf einen Blick ──────────────────────────── */}
      {/*
        Drei Zahlen, die man sonst aus drei Karten zusammensuchen
        müsste: läuft gerade etwas, wie viele Playlists gibt es, und
        bleibt der Bot dauerhaft im Kanal.
      */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-2xl bg-[#10233f] border border-slate-800 px-4 py-3.5">
          <p className="text-[9px] font-black uppercase tracking-widest text-slate-600">
            Zustand
          </p>
          <div className="flex items-center gap-2 mt-1.5">
            <span
              className={cn(
                "h-2 w-2 rounded-full shrink-0",
                live?.playing && !live?.paused
                  ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,.6)]"
                  : live?.connected
                  ? "bg-amber-400"
                  : "bg-slate-600"
              )}
            />
            <span className="text-[13px] font-bold text-white truncate">
              {live?.playing && !live?.paused
                ? "Spielt"
                : live?.paused
                ? "Pausiert"
                : live?.connected
                ? "Wartet"
                : "Offline"}
            </span>
          </div>
        </div>

        <div className="rounded-2xl bg-[#10233f] border border-slate-800 px-4 py-3.5">
          <p className="text-[9px] font-black uppercase tracking-widest text-slate-600">
            Playlists
          </p>
          <p className="text-[13px] font-bold text-white mt-1.5">
            {(data.playlists || []).length}
          </p>
        </div>

        <div className="rounded-2xl bg-[#10233f] border border-slate-800 px-4 py-3.5">
          <p className="text-[9px] font-black uppercase tracking-widest text-slate-600">
            Dauerbetrieb
          </p>
          <p
            className={cn(
              "text-[13px] font-bold mt-1.5",
              settings.stay_forever ? "text-emerald-300" : "text-slate-500"
            )}
          >
            {settings.stay_forever ? "24/7 an" : "Aus"}
          </p>
        </div>
      </div>

      {/* ── 1. Einstellungen ────────────────────────────────── */}
      <div className={cn(CARD, "space-y-5")}>
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
            <Music className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h3 className="font-bold text-white">Sprachkanal</h3>
            <p className="text-[12px] text-slate-500 mt-0.5">
              Wo der Bot Musik spielt.
            </p>
          </div>
        </div>

        <Field
          label="Stammkanal"
          hint="Der Bot spielt hier, statt dem Aufrufer hinterherzulaufen. Kanäle, die er nicht betreten darf, sind ausgegraut."
        >
          <select
            value={settings.channel_id || ""}
            onChange={(event) =>
              save({ channel_id: event.target.value || null })
            }
            disabled={busy === "settings"}
            className={INPUT}
          >
            <option value="">— keiner —</option>
            {(data.channels || []).map((channel: any) => (
              <option
                key={channel.id}
                value={channel.id}
                disabled={!channel.can_join}
              >
                {channel.name}
                {channel.category ? ` · ${channel.category}` : ""}
                {!channel.can_join ? "  (kein Zutritt)" : ""}
                {channel.can_join && !channel.can_speak ? "  (stumm)" : ""}
              </option>
            ))}
          </select>

          {/* Was gerade gewählt ist -- als Zeile, nicht nur im
              zugeklappten Menü.
              
              Ein <select> zeigt seine Auswahl zwar an, aber ohne
              Kategorie und ohne den Hinweis, ob der Bot dort
              überhaupt sprechen darf. Genau das ist der häufigste
              Grund für "es passiert nichts". */}
          {chosen ? (
            <div className="flex items-center gap-3 rounded-xl bg-primary/[0.07] border border-primary/25 px-3.5 py-3">
              <div className="h-8 w-8 rounded-lg bg-primary/15 grid place-items-center shrink-0">
                <Volume2 className="h-4 w-4 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-bold text-white truncate">
                  {chosen.name}
                </p>
                <p className="text-[11px] text-slate-500 truncate">
                  {chosen.category || "Ohne Kategorie"}
                  {live?.connected && live?.channel_id === chosen.id
                    ? " · der Bot ist gerade drin"
                    : ""}
                </p>
              </div>
              {!chosen.can_speak && (
                <span className="text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/25 shrink-0">
                  stumm
                </span>
              )}
            </div>
          ) : (
            <div className="rounded-xl bg-white/[0.02] border border-dashed border-slate-700 px-3.5 py-3">
              <p className="text-[12px] text-slate-500">
                Noch kein Kanal gewählt — ohne ihn weiß der Bot nicht, wo er
                spielen soll.
              </p>
            </div>
          )}
        </Field>

        <InlineToggle
          checked={Boolean(settings.stay_forever)}
          onCheckedChange={(value: boolean) => save({ stay_forever: value })}
          label="Dauerbetrieb (24/7)"
          hint="An: der Bot bleibt im Kanal, auch wenn niemand zuhört. Aus: er geht nach der eingestellten Leerlaufzeit."
        />

        {!settings.stay_forever && (
          <Field
            label="Leerlaufzeit"
            hint={`Wie lange der Bot ohne Zuhörer bleibt. Zwischen ${
              (limits.min_idle ?? 30) / 60 < 1
                ? `${limits.min_idle ?? 30} Sekunden`
                : `${(limits.min_idle ?? 30) / 60} Minuten`
            } und ${(limits.max_idle ?? 3600) / 60} Minuten.`}
          >
            <div className="flex items-center gap-3">
              <input
                type="number"
                min={limits.min_idle ?? 30}
                max={limits.max_idle ?? 3600}
                value={settings.idle_seconds ?? 120}
                onChange={(event) =>
                  setData((old: any) => ({
                    ...old,
                    settings: {
                      ...old.settings,
                      idle_seconds: Number(event.target.value),
                    },
                  }))
                }
                onBlur={(event) =>
                  save({ idle_seconds: Number(event.target.value) })
                }
                className={cn(INPUT, "w-32")}
              />
              <span className="text-[12px] text-slate-500">Sekunden</span>
            </div>
          </Field>
        )}

        <div className="border-t border-slate-800 pt-5 space-y-4">
          <InlineToggle
            checked={Boolean(settings.autostart)}
            onCheckedChange={(value: boolean) => save({ autostart: value })}
            label="Automatisch starten"
            hint="Sobald jemand den Stammkanal betritt, läuft die gewählte Playlist los."
          />

          {Boolean(settings.autostart) && (
            <Field
              label="Startliste"
              hint={
                playlists.length === 0
                  ? "Es gibt noch keine Playlist — lege unten eine an."
                  : undefined
              }
            >
              <select
                value={settings.autostart_playlist || ""}
                onChange={(event) =>
                  save({ autostart_playlist: event.target.value || null })
                }
                className={INPUT}
              >
                <option value="">— keine —</option>
                {playlists.map((list: any) => (
                  <option key={list.id} value={list.id}>
                    {list.name} ({list.count} Titel)
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
      </div>

      {/* ── 2. Playlists ────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-5")}>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
              <ListMusic className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="font-bold text-white">Playlists</h3>
              <p className="text-[12px] text-slate-500 mt-0.5">
                {playlists.length} von {limits.max_playlists ?? 25}
              </p>
            </div>
          </div>
        </div>

        {/* Anlegen */}
        <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-3">
          <p className="text-[11px] font-black uppercase tracking-widest text-slate-500">
            Neue Playlist
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="Name, z. B. Chill"
              maxLength={limits.max_name ?? 80}
              className={INPUT}
            />
            <input
              value={newQuery}
              onChange={(event) => setNewQuery(event.target.value)}
              placeholder="Link oder Suchbegriff (optional)"
              className={INPUT}
            />
          </div>
          <button
            disabled={!newName.trim() || busy === "create"}
            onClick={async () => {
              setBusy("create");
              try {
                await api.musicPlaylistCreate(
                  guildId,
                  newName.trim(),
                  newQuery.trim() || undefined
                );
                setNewName("");
                setNewQuery("");
                await load();
                toast.success("Playlist angelegt.");
              } catch (error: any) {
                toast.error(error?.message || "Das ließ sich nicht anlegen.");
              } finally {
                setBusy("");
              }
            }}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/20 disabled:opacity-40 transition-all"
          >
            {busy === "create" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            Anlegen
          </button>
        </div>

        {playlists.length === 0 ? (
          <p className="text-[13px] text-slate-600 text-center py-6">
            Noch keine Playlist.
          </p>
        ) : (
          <div className="space-y-3">
            {playlists.map((list: any) => (
              <div
                key={list.id}
                className="rounded-2xl bg-[#0a1628] border border-slate-800 overflow-hidden"
              >
                <div className="flex items-center gap-3 p-4 flex-wrap">
                  <button
                    onClick={() => setOpen(open === list.id ? null : list.id)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <p className="text-sm font-bold text-white truncate">
                      {list.name}
                    </p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {list.count} Titel
                      {list.length ? ` · ${duration(list.length)}` : ""}
                    </p>
                  </button>

                  <button
                    disabled={!list.count || busy === `play${list.id}`}
                    onClick={async () => {
                      setBusy(`play${list.id}`);
                      try {
                        const answer = await api.musicPlay(guildId, list.id);
                        if (answer?.live) setLive(answer.live);
                        toast.success(answer?.detail || "Läuft.");
                      } catch (error: any) {
                        toast.error(error?.message || "Das hat nicht geklappt.");
                      } finally {
                        setBusy("");
                      }
                    }}
                    title="Im Stammkanal abspielen"
                    className="p-2.5 rounded-xl bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 disabled:opacity-30 transition-all"
                  >
                    {busy === `play${list.id}` ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                  </button>

                  <button
                    onClick={async () => {
                      setBusy(`del${list.id}`);
                      try {
                        await api.musicPlaylistDelete(guildId, list.id);
                        await load();
                        toast.success("Gelöscht.");
                      } catch (error: any) {
                        toast.error(error?.message || "Das ließ sich nicht löschen.");
                      } finally {
                        setBusy("");
                      }
                    }}
                    title="Playlist löschen"
                    className="p-2.5 rounded-xl text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-all"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>

                {/* Aufgeklappt: die Titel mit Cover */}
                {open === list.id && (
                  <div className="border-t border-slate-800 p-4 space-y-3">
                    <div className="flex gap-2">
                      <input
                        value={addQuery}
                        onChange={(event) => setAddQuery(event.target.value)}
                        placeholder="Titel hinzufügen — Link oder Suchbegriff"
                        className={cn(INPUT, "flex-1")}
                      />
                      <button
                        disabled={!addQuery.trim() || busy === `add${list.id}`}
                        onClick={async () => {
                          setBusy(`add${list.id}`);
                          try {
                            const answer = await api.musicPlaylistAddTracks(
                              guildId,
                              list.id,
                              addQuery.trim()
                            );
                            setAddQuery("");
                            await load();
                            toast.success(
                              `${answer?.added ?? 0} Titel hinzugefügt.`
                            );
                          } catch (error: any) {
                            toast.error(
                              error?.message || "Das ließ sich nicht hinzufügen."
                            );
                          } finally {
                            setBusy("");
                          }
                        }}
                        className="px-4 rounded-xl bg-white/[0.04] border border-white/10 text-slate-300 text-xs font-bold hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
                      >
                        {busy === `add${list.id}` ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Plus className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>

                    {list.tracks.length === 0 ? (
                      <p className="text-[12px] text-slate-600 py-3 text-center">
                        Noch keine Titel.
                      </p>
                    ) : (
                      <div className="space-y-1.5 max-h-80 overflow-y-auto">
                        {list.tracks.map((entry: any, index: number) => (
                          <div
                            key={`${entry.uri}-${index}`}
                            className="flex items-center gap-3 p-2 rounded-xl hover:bg-white/[0.03] transition-colors"
                          >
                            <span className="text-[10px] text-slate-600 w-5 shrink-0 text-right">
                              {index + 1}
                            </span>
                            {entry.artwork ? (
                              /* eslint-disable-next-line @next/next/no-img-element */
                              <img
                                src={entry.artwork}
                                alt=""
                                loading="lazy"
                                className="h-9 w-9 rounded-lg object-cover shrink-0"
                              />
                            ) : (
                              <div className="h-9 w-9 rounded-lg bg-white/[0.04] grid place-items-center shrink-0">
                                <Music className="h-3.5 w-3.5 text-slate-600" />
                              </div>
                            )}
                            <div className="min-w-0 flex-1">
                              <p className="text-[12.5px] text-slate-200 truncate">
                                {entry.title}
                              </p>
                              {entry.author && (
                                <p className="text-[11px] text-slate-600 truncate">
                                  {entry.author}
                                </p>
                              )}
                            </div>
                            <span className="text-[11px] text-slate-600 shrink-0">
                              {clock(entry.length)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── 3. Live ─────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-5")}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
              <Volume2 className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="font-bold text-white">Läuft gerade</h3>
              <p className="text-[12px] text-slate-500 mt-0.5">
                {live?.connected
                  ? `Im Kanal ${live.channel_name}`
                  : "Der Bot ist in keinem Sprachkanal."}
              </p>
            </div>
          </div>
          <button
            onClick={async () => {
              try {
                setLive(await api.musicLive(guildId));
              } catch {
                /* still */
              }
            }}
            title="Neu laden"
            className="p-2 rounded-xl text-slate-600 hover:text-slate-300 transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {!live?.connected || !track.title ? (
          <p className="text-[13px] text-slate-600 text-center py-8">
            Gerade läuft nichts.
          </p>
        ) : (
          <>
            <div className="flex gap-4">
              {track.artwork ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={track.artwork}
                  alt=""
                  className="h-24 w-24 rounded-2xl object-cover shrink-0 shadow-lg shadow-black/40"
                />
              ) : (
                <div className="h-24 w-24 rounded-2xl bg-white/[0.04] grid place-items-center shrink-0">
                  <Music className="h-7 w-7 text-slate-700" />
                </div>
              )}

              <div className="min-w-0 flex-1 flex flex-col justify-center">
                <p className="text-base font-bold text-white truncate">
                  {track.title}
                </p>
                {track.author && (
                  <p className="text-[13px] text-slate-500 truncate mt-0.5">
                    {track.author}
                  </p>
                )}

                {/* Fortschritt */}
                <div className="mt-3">
                  <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-[width] duration-500 ease-linear"
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                  <div className="flex justify-between mt-1.5">
                    <span className="text-[11px] text-slate-500 tabular-nums">
                      {clock(position)}
                    </span>
                    <span className="text-[11px] text-slate-600 tabular-nums">
                      {clock(track.length)}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Warum es still ist.
                
                Ohne diesen Hinweis wirkt der pausierte Bot kaputt:
                man sieht einen Titel, hört aber nichts. */}
            {live.paused && (
              <div className="rounded-xl bg-amber-500/[0.07] border border-amber-500/25 px-3.5 py-2.5">
                <p className="text-[12px] text-amber-200/80 leading-relaxed">
                  Pausiert. Ist niemand mehr im Kanal, hält der Bot von
                  selbst an und macht an derselben Stelle weiter, sobald
                  wieder jemand da ist.
                </p>
              </div>
            )}

            {/* Steuerung */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                disabled={busy === "pause" || busy === "resume"}
                onClick={() => control(live.paused ? "resume" : "pause")}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/20 disabled:opacity-40 transition-all"
              >
                {live.paused ? (
                  <Play className="h-3.5 w-3.5" />
                ) : (
                  <Pause className="h-3.5 w-3.5" />
                )}
                {live.paused ? "Weiter" : "Pause"}
              </button>

              <button
                disabled={busy === "skip"}
                onClick={() => control("skip")}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-slate-300 text-xs font-black uppercase tracking-widest hover:text-white disabled:opacity-40 transition-all"
              >
                <SkipForward className="h-3.5 w-3.5" />
                Weiter
              </button>

              {/* "Verlassen" statt "Stopp".
                  
                  Die Aktion war schon immer beides: Warteschlange
                  leeren UND den Kanal verlassen. "Stopp" ließ das
                  Zweite erwarten -- man drückte es, um die Musik
                  anzuhalten, und der Bot war weg. Dafür gibt es
                  Pause. */}
              <button
                disabled={busy === "stop"}
                onClick={() => control("stop")}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-slate-400 text-xs font-black uppercase tracking-widest hover:text-red-400 hover:border-red-500/30 disabled:opacity-40 transition-all"
                title="Warteschlange leeren und den Sprachkanal verlassen"
              >
                <LogOut className="h-3.5 w-3.5" />
                Verlassen
              </button>
            </div>

            {/* Lautstärke -- der einzige Regler.
                
                Oben in den Einstellungen stand ein zweiter, und das
                war verwirrend: zwei Regler für dieselbe Zahl, wobei
                der obere erst beim nächsten Titel wirkte. Dieser hier
                wirkt sofort und wird zugleich gespeichert. */}
            <div className="rounded-2xl bg-[#0a1628] border border-slate-800 px-4 py-3.5">
              <div className="flex items-center justify-between mb-2.5">
                <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">
                  Lautstärke
                </span>
                <span className="text-[12px] font-bold text-slate-300 tabular-nums">
                  {volumeShown} %
                </span>
              </div>
              <div className="flex items-center gap-3">
                <Volume2 className="h-3.5 w-3.5 text-slate-600 shrink-0" />
                <input
                  type="range"
                  min={limits.min_volume ?? 0}
                  max={limits.max_volume ?? 200}
                  value={volumeShown}
                  onChange={(event) => setVolumeDraft(Number(event.target.value))}
                  onMouseUp={(event: any) =>
                    control("volume", Number(event.target.value))
                  }
                  onTouchEnd={(event: any) =>
                    control("volume", Number(event.target.value))
                  }
                  className="flex-1 accent-primary"
                />
              </div>
              <p className="text-[11px] text-slate-600 mt-2 leading-relaxed">
                Wirkt sofort und bleibt für das nächste Mal gespeichert.
                Über 100 % übersteuert hörbar.
              </p>
            </div>

            {/* Warteschlange */}
            {live.queue?.length > 0 && (
              <div className="border-t border-slate-800 pt-4">
                <p className="text-[11px] font-black uppercase tracking-widest text-slate-500 mb-3">
                  Als Nächstes · {live.queue_total}
                </p>
                <div className="space-y-1.5">
                  {live.queue.map((entry: any, index: number) => (
                    <div
                      key={`${entry.uri}-${index}`}
                      className="flex items-center gap-3 p-1.5"
                    >
                      <span className="text-[10px] text-slate-600 w-4 shrink-0 text-right">
                        {index + 1}
                      </span>
                      {entry.artwork ? (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                          src={entry.artwork}
                          alt=""
                          loading="lazy"
                          className="h-7 w-7 rounded-md object-cover shrink-0"
                        />
                      ) : (
                        <div className="h-7 w-7 rounded-md bg-white/[0.04] shrink-0" />
                      )}
                      <p className="text-[12px] text-slate-400 truncate flex-1">
                        {entry.title}
                      </p>
                      <span className="text-[11px] text-slate-600 shrink-0">
                        {clock(entry.length)}
                      </span>
                    </div>
                  ))}
                </div>
                {live.queue_total > live.queue.length && (
                  <p className="text-[11px] text-slate-600 mt-2 pl-7">
                    … und {live.queue_total - live.queue.length} weitere
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
