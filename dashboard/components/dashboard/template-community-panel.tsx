"use client";

/**
 * Community-Vorlagen: stöbern, ansehen, anwenden.
 *
 * ── Der Ablauf ──────────────────────────────────────────────────────
 *
 *   1. Liste mit Suche und Sortierung.
 *   2. Eine Vorlage auswählen → Vorschau. Bei einer Vorlage mit
 *      Zugangscode bleibt sie verschlossen, bis der Code stimmt.
 *   3. Auswählen, was übernommen wird — Rollen, Kanäle, Rechte,
 *      Einstellungen. Unter „Dashboard erweitert" jede Funktion
 *      einzeln.
 *   4. Prüfen: der Bot sagt, was er anlegen würde und was ihm fehlt.
 *   5. Anwenden.
 *
 * ── Warum „alles löschen“ so umständlich ist ────────────────────────
 *
 * Discord kennt keinen Papierkorb. Ein gelöschter Kanal ist samt
 * Verlauf weg — endgültig. Deshalb bleiben zwei Hürden:
 *
 *   * der Schalter ist rot und getrennt vom Rest,
 *   * der Knopf ist zehn Sekunden lang gesperrt.
 *
 * Das Abtippen des Servernamens ist bewusst wieder verschwunden. Es
 * sah nach Sicherheit aus, war aber keine: der Name stand als
 * Platzhalter direkt im Feld darüber, abtippen dauert drei Sekunden
 * und man liest dabei nichts. Die Wartezeit dagegen vergeht, ob man
 * will oder nicht — und in ihr liest man tatsächlich, was da steht.
 *
 * Die Sperre steht doppelt: hier im `disabled` des Knopfes und noch
 * einmal im Bot. Nur im Browser wäre sie eine Bitte, kein Riegel — ein
 * direkter Aufruf der Route umginge sie mit einer Zeile.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowLeft, Check, Clock, Flame, Hash, Loader2, Lock,
  RefreshCcw, Search, Shield, SortAsc, Sparkles, ThumbsDown, ThumbsUp,
  TrendingUp, Users, Volume2, X,
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

/**
 * Wie lange der Löschen-Knopf gesperrt bleibt.
 *
 * Dieselbe Zahl steht im Bot (`WIPE_DELAY_SECONDS` in
 * `api/routes/templates.py`) und wird von dort über die Prüfung
 * mitgeliefert. Der Wert hier ist nur der Startwert, bis die Prüfung
 * geantwortet hat — maßgeblich ist immer der Server.
 */
const WIPE_DELAY_SECONDS = 10;

/**
 * Wonach sich ordnen lässt.
 *
 * „Beliebt" und „Genutzt" sind bewusst zwei Einträge. Früher war
 * „beliebt" gleichbedeutend mit „oft angewendet" — das ist aber etwas
 * anderes: eine Vorlage kann oft angewendet werden, weil sie ganz oben
 * steht, und trotzdem niemandem gefallen.
 *
 * Die Schlüssel müssen zu `SORTS` im Bot passen; ein unbekannter Wert
 * fällt dort still auf „neu" zurück.
 */
const SORTS = [
  {
    id: "beliebt",
    label: "Beste",
    icon: Flame,
    hint: "Nach Bewertung. Wenige Stimmen zählen weniger als viele.",
  },
  {
    id: "genutzt",
    label: "Meist genutzt",
    icon: TrendingUp,
    hint: "Wie oft die Vorlage auf einen Server geholt wurde.",
  },
  { id: "neu", label: "Neueste", icon: Clock, hint: "Zuletzt hochgeladen." },
  { id: "name", label: "Name", icon: SortAsc, hint: "Alphabetisch." },
];

/** Was aus der Liste ausgeblendet werden kann. */
const FILTERS = [
  { id: "alle", label: "Alle" },
  { id: "offen", label: "Ohne Code" },
  { id: "bewertet", label: "Bewertet" },
];

/**
 * Die zwei Daumen.
 *
 * Eigenes Bauteil, weil es zweimal gebraucht wird — in der Liste und
 * in der Detailansicht. Zwei Kopien liefen garantiert auseinander.
 *
 * Der eigene Daumen ist farbig hinterlegt: ohne diese Rückmeldung
 * weiß niemand, ob der Klick angekommen ist, und man klickt noch
 * einmal — was die Stimme wieder zurücknimmt.
 */
function VoteButtons({
  votes,
  disabled,
  busy,
  hint,
  mine,
  onVote,
  size = "sm",
}: {
  votes: { up: number; down: number; own: number };
  disabled?: boolean;
  busy?: boolean;
  hint?: string;
  mine?: boolean;
  onVote: (value: number) => void;
  size?: "sm" | "lg";
}) {
  const big = size === "lg";
  const shape = big ? "px-3.5 py-2 text-[13px]" : "px-2.5 py-1.5 text-[12px]";
  const icon = big ? "h-4 w-4" : "h-3.5 w-3.5";

  return (
    <div className="flex items-center gap-1.5" title={hint || undefined}>
      <button
        type="button"
        disabled={disabled || mine}
        aria-pressed={votes.own === 1}
        aria-label="Gefällt mir"
        onClick={() => onVote(1)}
        className={cn(
          "flex items-center gap-1.5 rounded-xl border font-bold transition-all tabular-nums",
          shape,
          votes.own === 1
            ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300"
            : "bg-white/[0.03] border-white/10 text-slate-500 hover:text-emerald-300 hover:border-emerald-500/30",
          (disabled || mine) && "opacity-40 cursor-not-allowed"
        )}
      >
        {busy ? (
          <Loader2 className={cn(icon, "animate-spin")} />
        ) : (
          <ThumbsUp className={icon} />
        )}
        {votes.up}
      </button>

      <button
        type="button"
        disabled={disabled || mine}
        aria-pressed={votes.own === -1}
        aria-label="Gefällt mir nicht"
        onClick={() => onVote(-1)}
        className={cn(
          "flex items-center gap-1.5 rounded-xl border font-bold transition-all tabular-nums",
          shape,
          votes.own === -1
            ? "bg-red-500/15 border-red-500/40 text-red-300"
            : "bg-white/[0.03] border-white/10 text-slate-500 hover:text-red-300 hover:border-red-500/30",
          (disabled || mine) && "opacity-40 cursor-not-allowed"
        )}
      >
        <ThumbsDown className={icon} />
        {votes.down}
      </button>
    </div>
  );
}

export function TemplateCommunityPanel({ guildId }: { guildId: string }) {
  const [list, setList] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  // Beste zuerst: das ist die Frage, mit der man herkommt.
  // Vorher stand „neu" oben — dort landet, was gerade erst hochgeladen
  // wurde und noch niemand angesehen hat.
  const [sort, setSort] = useState("beliebt");
  const [filter, setFilter] = useState("alle");
  // Ob der angemeldete Nutzer überhaupt abstimmen darf. Sagt der Bot,
  // nicht der Browser.
  const [canVote, setCanVote] = useState(false);

  // Ausgewählte Vorlage
  const [chosen, setChosen] = useState<any>(null);
  const [keyInput, setKeyInput] = useState("");
  const [features, setFeatures] = useState<any[]>([]);
  const [busy, setBusy] = useState("");

  // Was übernommen wird
  const [options, setOptions] = useState({
    roles: true,
    channels: true,
    permissions: true,
    features: false,
  });
  const [featureKeys, setFeatureKeys] = useState<Record<string, boolean>>({});

  // Die gefährliche Option
  const [wipe, setWipe] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [preview, setPreview] = useState<any>(null);
  const [report, setReport] = useState<any>(null);

  const timer = useRef<any>(null);

  const load = useCallback(
    async (manual = false) => {
      if (manual) setBusy("reload");
      try {
        const answer = await api.templateList(guildId, search, sort);
        const own: any[] = answer?.own || [];
        // Welche Vorlagen von diesem Server stammen. Sie lassen sich
        // nicht bewerten — die Daumen sind dann ausgegraut statt still
        // eine Fehlermeldung zu erzeugen.
        const mine = new Set(own.map((entry: any) => entry.id));
        setList(
          (answer?.templates || []).map((entry: any) => ({
            ...entry,
            mine: mine.has(entry.id),
          }))
        );
        setCanVote(Boolean(answer?.can_vote));
      } catch (error: any) {
        toast.error(error?.message || "Die Vorlagen ließen sich nicht laden.");
      } finally {
        setLoading(false);
        if (manual) setBusy("");
      }
    },
    [guildId, search, sort]
  );

  useEffect(() => {
    // Kurz warten, damit nicht bei jedem Tastendruck gesucht wird.
    const handle = setTimeout(load, 250);
    return () => clearTimeout(handle);
  }, [load]);

  /**
   * Abstimmen.
   *
   * Die neuen Zahlen kommen aus der Antwort des Bots und werden nicht
   * im Browser hochgezählt: bei zwei offenen Fenstern liefen die
   * Stände sonst auseinander, und ein abgelehnter Klick — etwa bei der
   * eigenen Vorlage — sähe trotzdem nach Erfolg aus.
   *
   * Die Liste wird bewusst NICHT neu geladen. Bei der Sortierung
   * „Beste" spränge die eben bewertete Karte sonst mitten unter dem
   * Zeiger weg.
   */
  const runVote = async (entry: any, value: number) => {
    if (!canVote || entry.mine) return;
    setBusy(`vote${entry.id}`);
    try {
      const answer = await api.templateVote(guildId, entry.id, value);
      const votes = answer?.votes;
      if (!votes) return;

      setList((old) =>
        old.map((item) =>
          item.id === entry.id ? { ...item, votes } : item
        )
      );
      // Auch die geöffnete Vorlage mitziehen, falls es dieselbe ist.
      setChosen((old: any) =>
        old && old.id === entry.id ? { ...old, votes } : old
      );
    } catch (error: any) {
      toast.error(error?.message || "Die Bewertung ging nicht durch.");
    } finally {
      setBusy("");
    }
  };

  /** Die gefilterte Liste. Sortiert hat schon der Bot. */
  const visible = useMemo(() => {
    if (filter === "offen") return list.filter((entry) => !entry.locked);
    if (filter === "bewertet") {
      return list.filter(
        (entry) => (entry.votes?.up || 0) + (entry.votes?.down || 0) > 0
      );
    }
    return list;
  }, [list, filter]);

  /** Wie viele Stimmen insgesamt — für die Zeile unter der Überschrift. */
  const stats = useMemo(() => {
    let up = 0;
    let down = 0;
    for (const entry of list) {
      up += entry.votes?.up || 0;
      down += entry.votes?.down || 0;
    }
    return { up, down };
  }, [list]);

  // Der Countdown für „alles löschen“.
  //
  // Er hängt an der Prüfung, nicht am Schalter. Das ist der
  // Unterschied, auf den es ankommt: der Bot rechnet ab dem Zeitpunkt
  // der Prüfung (`armed_at`) und weist ein zu frühes Anwenden ab. Liefe
  // die Uhr hier schon ab dem Umlegen des Schalters, wäre sie fertig,
  // bevor die Prüfung überhaupt zurück ist — der Knopf sähe frei aus
  // und der Bot antwortete trotzdem mit „bitte noch warten“.
  //
  // `preview?.armed_at` in den Abhängigkeiten sorgt dafür, dass jede
  // neue Prüfung die Uhr neu startet.
  useEffect(() => {
    if (timer.current) clearInterval(timer.current);

    if (!wipe || !preview?.armed_at) {
      setCountdown(0);
      return;
    }

    // Der Server bestimmt die Wartezeit. Ohne Angabe der hiesige
    // Startwert — dann stimmen im schlimmsten Fall die Sekunden nicht
    // ganz, aber der Bot weist trotzdem korrekt ab.
    const total = Number(preview.wipe_delay) || WIPE_DELAY_SECONDS;
    setCountdown(total);
    timer.current = setInterval(() => {
      setCountdown((old) => {
        if (old <= 1) {
          clearInterval(timer.current);
          return 0;
        }
        return old - 1;
      });
    }, 1000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [wipe, preview?.armed_at, preview?.wipe_delay]);

  const open = async (entry: any, key = "") => {
    setBusy(`open${entry.id}`);
    try {
      const answer = await api.templateDetail(guildId, entry.id, key);
      setChosen(answer?.template || null);
      setFeatures(answer?.features || []);
      const keys: Record<string, boolean> = {};
      for (const item of answer?.features || []) keys[item.key] = true;
      setFeatureKeys(keys);
      setPreview(null);
      setReport(null);
      setWipe(false);
    } catch (error: any) {
      toast.error(error?.message || "Die Vorlage ließ sich nicht öffnen.");
    } finally {
      setBusy("");
    }
  };

  const runPreview = async () => {
    if (!chosen) return;
    setBusy("preview");
    try {
      const answer = await api.templatePreview(guildId, {
        template_id: chosen.id,
        key: keyInput || undefined,
        wipe,
      });
      setPreview(answer);
    } catch (error: any) {
      toast.error(error?.message || "Die Prüfung schlug fehl.");
    } finally {
      setBusy("");
    }
  };

  const runApply = async () => {
    if (!chosen) return;
    setBusy("apply");
    try {
      const answer = await api.templateApply(guildId, {
        template_id: chosen.id,
        key: keyInput || undefined,
        ...options,
        feature_keys: featureKeys,
        wipe,
        // Der Zeitstempel aus der Prüfung. Der Bot rechnet damit nach,
        // ob die zehn Sekunden wirklich um sind — die Sperre im Browser
        // allein wäre keine.
        armed_at: preview?.armed_at,
      });
      setReport(answer?.report || null);
      if (answer?.report?.ok) {
        toast.success("Vorlage angewendet.");
      } else {
        toast.warning("Fertig — mit Hinweisen. Siehe Bericht unten.");
      }
    } catch (error: any) {
      toast.error(error?.message || "Das Anwenden schlug fehl.");
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

  // ── Eine Vorlage ist ausgewählt ──────────────────────────
  if (chosen) {
    const payload = chosen.payload || {};
    // Eine gesperrte Vorlage lässt sich nicht anwenden. Der Bot weist
    // es ohnehin ab; hier steht es, damit der Knopf nicht klickbar
    // aussieht und der Grund lesbar ist.
    const blocked = Boolean(chosen.blocked || preview?.blocked);

    return (
      <div className="space-y-5">
        <button
          onClick={() => setChosen(null)}
          className="flex items-center gap-2 text-[12px] font-bold text-slate-500 hover:text-slate-300 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Zurück zur Liste
        </button>

        <div className={cn(CARD, "space-y-4")}>
          <div className="flex items-start gap-3 flex-wrap">
            <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
              <Sparkles className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="font-bold text-white">{chosen.name}</h3>
              {chosen.description && (
                <p className="text-[12.5px] text-slate-400 mt-1 leading-relaxed">
                  {chosen.description}
                </p>
              )}
              <p className="text-[11px] text-slate-600 mt-1.5">
                {chosen.author_name ? `von ${chosen.author_name} · ` : ""}
                {chosen.uses}× verwendet
              </p>
            </div>

            {/* Bewerten geht auch hier — man entscheidet sich meist
                erst, nachdem man die Vorlage angesehen hat, nicht
                schon in der Liste. */}
            <div className="shrink-0">
              <VoteButtons
                size="lg"
                votes={
                  chosen.votes || { up: 0, down: 0, own: 0 }
                }
                disabled={!canVote || busy === `vote${chosen.id}`}
                busy={busy === `vote${chosen.id}`}
                mine={Boolean(
                  list.find((entry) => entry.id === chosen.id)?.mine
                )}
                hint={
                  !canVote ? "Zum Bewerten anmelden" : ""
                }
                onVote={(value) => runVote(chosen, value)}
              />
            </div>
          </div>

          {/* Vom Bot-Team gesperrt */}
          {blocked && (
            <div className="rounded-2xl bg-red-500/[0.07] border border-red-500/30 p-4 flex gap-2.5">
              <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[13px] font-bold text-red-200">
                  Diese Vorlage wurde gesperrt
                </p>
                <p className="text-[12.5px] text-red-200/75 leading-relaxed mt-0.5">
                  {chosen.blocked_reason ||
                    preview?.blocked_reason ||
                    "Das Bot-Team hat sie aus dem Verkehr gezogen."}{" "}
                  Sie lässt sich nicht mehr anwenden.
                </p>
              </div>
            </div>
          )}

          {/* Verschlossen: erst der Code */}
          {chosen.locked ? (
            <div className="rounded-2xl bg-amber-500/[0.07] border border-amber-500/25 p-5 space-y-3">
              <div className="flex items-center gap-2.5">
                <Lock className="h-4 w-4 text-amber-400" />
                <p className="text-[13px] font-bold text-amber-200">
                  Diese Vorlage braucht einen Zugangscode
                </p>
              </div>
              <p className="text-[12px] text-amber-200/70 leading-relaxed">
                Ohne ihn bleibt auch die Vorschau verschlossen — Kanal- und
                Rollennamen sind erst danach zu sehen.
              </p>
              <div className="flex gap-2 flex-wrap">
                <input
                  value={keyInput}
                  onChange={(event) =>
                    setKeyInput(event.target.value.toUpperCase())
                  }
                  placeholder="CODE"
                  maxLength={16}
                  className={cn(
                    INPUT,
                    "flex-1 min-w-[160px] font-mono tracking-[0.25em] uppercase"
                  )}
                />
                <button
                  disabled={!keyInput.trim() || busy.startsWith("open")}
                  onClick={() => open(chosen, keyInput.trim())}
                  className="px-5 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/20 disabled:opacity-40 transition-all"
                >
                  Öffnen
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Vorschau */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  {
                    label: "Kategorien",
                    value: (payload.categories || []).length,
                  },
                  { label: "Kanäle", value: (payload.channels || []).length },
                  { label: "Rollen", value: (payload.roles || []).length },
                  { label: "Funktionen", value: features.length },
                ].map((entry) => (
                  <div
                    key={entry.label}
                    className="rounded-2xl bg-[#0a1628] border border-slate-800 px-4 py-3"
                  >
                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-600">
                      {entry.label}
                    </p>
                    <p className="text-lg font-black text-white mt-1">
                      {entry.value}
                    </p>
                  </div>
                ))}
              </div>

              <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 max-h-64 overflow-y-auto space-y-3">
                {(payload.roles || []).length > 0 && (
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2">
                      Rollen
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {payload.roles.map((role: any) => (
                        <span
                          key={role.name}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] text-slate-300"
                        >
                          <span
                            className="h-2 w-2 rounded-full shrink-0"
                            style={{ background: role.colour || "#99aab5" }}
                          />
                          {role.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {(payload.channels || []).length > 0 && (
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2">
                      Kanäle
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {payload.channels.slice(0, 60).map((channel: any) => (
                        <span
                          key={`${channel.category}-${channel.name}`}
                          className="px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] text-slate-400"
                        >
                          {channel.kind === "voice" ? "🔊" : "#"} {channel.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Was übernommen wird */}
              <div className="border-t border-slate-800 pt-4 space-y-3">
                <p className="text-[11px] font-black uppercase tracking-widest text-slate-500">
                  Was soll übernommen werden?
                </p>
                <InlineToggle
                  checked={options.roles}
                  onCheckedChange={(v: boolean) =>
                    setOptions((old) => ({ ...old, roles: v }))
                  }
                  label="Rollen"
                  hint="Gleichnamige Rollen werden wiederverwendet, nicht doppelt angelegt."
                />
                <InlineToggle
                  checked={options.channels}
                  onCheckedChange={(v: boolean) =>
                    setOptions((old) => ({ ...old, channels: v }))
                  }
                  label="Kanäle und Kategorien"
                />
                <InlineToggle
                  checked={options.permissions}
                  onCheckedChange={(v: boolean) =>
                    setOptions((old) => ({ ...old, permissions: v }))
                  }
                  label="Kanalrechte"
                  hint="Ohne das entstehen die Kanäle mit den Serverstandards."
                />
                <InlineToggle
                  checked={options.features}
                  onCheckedChange={(v: boolean) =>
                    setOptions((old) => ({ ...old, features: v }))
                  }
                  label="Dashboard-Einstellungen"
                  hint="Überschreibt, was hier bereits eingestellt ist."
                />

                {options.features && features.length > 0 && (
                  <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-1">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2">
                      Dashboard erweitert
                    </p>
                    {features.map((entry: any) => (
                      <label
                        key={entry.key}
                        className="flex items-center gap-3 py-1.5 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={featureKeys[entry.key] ?? true}
                          onChange={(event) =>
                            setFeatureKeys((old) => ({
                              ...old,
                              [entry.key]: event.target.checked,
                            }))
                          }
                          className="accent-primary h-4 w-4"
                        />
                        <span className="text-[13px] text-slate-200 flex-1">
                          {entry.label}
                        </span>
                        <span className="text-[11px] text-slate-600">
                          {entry.entries}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {/* Die gefährliche Option */}
              <div className="border-t border-slate-800 pt-4">
                <div
                  className={cn(
                    "rounded-2xl border p-4 transition-colors",
                    wipe
                      ? "bg-red-500/[0.08] border-red-500/40"
                      : "bg-[#0a1628] border-slate-800"
                  )}
                >
                  <InlineToggle
                    checked={wipe}
                    onCheckedChange={setWipe}
                    label="Vorher alles löschen"
                    hint="Entfernt alle bestehenden Kanäle und Rollen, bevor die Vorlage angelegt wird."
                  />

                  {wipe && (
                    <div className="mt-4 space-y-3">
                      <div className="flex gap-2.5">
                        <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                        <p className="text-[12.5px] text-red-200/90 leading-relaxed">
                          <b>Das lässt sich nicht rückgängig machen.</b> Discord
                          kennt keinen Papierkorb — Kanäle verschwinden samt
                          ihrem gesamten Verlauf. Die Rolle des Bots und
                          Pflichtkanäle bleiben stehen.
                        </p>
                      </div>

                      <div className="rounded-xl bg-[#0a1628]/60 border border-red-500/20 p-3.5 space-y-2">
                        <p className="text-[11px] font-black uppercase tracking-widest text-red-300/70">
                          Was passiert
                        </p>
                        <p className="text-[12px] text-red-200/70 leading-relaxed">
                          {preview ? (
                            <>
                              Auf <b>{preview.guild_name}</b> werden{" "}
                              <b>{(preview.will_delete || []).length} Einträge</b>{" "}
                              gelöscht und anschließend{" "}
                              <b>
                                {(preview.will_create?.roles || []).length} Rollen
                              </b>{" "}
                              und{" "}
                              <b>
                                {(preview.will_create?.channels || []).length}{" "}
                                Kanäle
                              </b>{" "}
                              neu angelegt.
                            </>
                          ) : (
                            <>
                              Erst prüfen &mdash; danach steht hier genau, was
                              gelöscht und was angelegt wird. Ab der Prüfung
                              läuft die Wartezeit von {WIPE_DELAY_SECONDS}{" "}
                              Sekunden.
                            </>
                          )}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Prüfen und anwenden */}
              <div className="flex items-center gap-2 flex-wrap pt-1">
                <button
                  disabled={busy === "preview"}
                  onClick={runPreview}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-slate-300 text-xs font-black uppercase tracking-widest hover:text-white disabled:opacity-40 transition-all"
                >
                  {busy === "preview" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Shield className="h-3.5 w-3.5" />
                  )}
                  Prüfen
                </button>

                <button
                  disabled={
                    busy === "apply" ||
                    !preview ||
                    (preview?.problems || []).length > 0 ||
                    blocked ||
                    (wipe && countdown > 0)
                  }
                  onClick={runApply}
                  className={cn(
                    "flex items-center gap-2 px-5 py-2.5 rounded-xl border text-xs font-black uppercase tracking-widest transition-all disabled:opacity-40",
                    wipe
                      ? "bg-red-500/15 border-red-500/45 text-red-300 hover:bg-red-500/25"
                      : "bg-primary/15 border-primary/40 text-primary hover:bg-primary/20"
                  )}
                >
                  {busy === "apply" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Check className="h-3.5 w-3.5" />
                  )}
                  {wipe && countdown > 0
                    ? `Bitte warten … ${countdown}s`
                    : wipe
                    ? "Löschen und anwenden"
                    : "Anwenden"}
                </button>
              </div>

              {wipe && countdown > 0 && (
                <p className="text-[11px] text-red-200/60">
                  Der Knopf ist {preview?.wipe_delay || WIPE_DELAY_SECONDS}{" "}
                  Sekunden gesperrt — Zeit, noch einmal zu lesen, was oben
                  steht.
                </p>
              )}

              {/* Warum der Knopf sonst noch aus sein kann. Ein
                  ausgegrauter Knopf ohne Erklärung sieht nach einem
                  Fehler aus. */}
              {!preview && (
                <p className="text-[11px] text-slate-600">
                  Erst „Prüfen“ — der Bot sagt dann, was er anlegen würde und
                  ob ihm etwas fehlt.
                </p>
              )}
            </>
          )}
        </div>

        {/* Ergebnis der Prüfung */}
        {preview && (
          <div className={cn(CARD, "space-y-4")}>
            <h3 className="font-bold text-white">Prüfung</h3>

            {(preview.problems || []).length > 0 ? (
              <div className="rounded-2xl bg-red-500/[0.07] border border-red-500/25 p-4 space-y-2">
                <p className="text-[13px] font-bold text-red-200">
                  So geht es nicht weiter:
                </p>
                {preview.problems.map((problem: string) => (
                  <p
                    key={problem}
                    className="text-[12.5px] text-red-200/80 leading-relaxed"
                  >
                    • {problem}
                  </p>
                ))}
              </div>
            ) : (
              <div className="rounded-2xl bg-emerald-500/[0.06] border border-emerald-500/25 p-4">
                <p className="text-[13px] text-emerald-200">
                  Alles bereit — der Bot hat die nötigen Rechte.
                </p>
              </div>
            )}

            <div className="grid sm:grid-cols-2 gap-3">
              <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4">
                <p className="text-[10px] font-black uppercase tracking-widest text-emerald-400/70 mb-2">
                  Wird angelegt
                </p>
                <p className="text-[12px] text-slate-400 leading-relaxed">
                  {(preview.will_create?.roles || []).length} Rollen,{" "}
                  {(preview.will_create?.categories || []).length} Kategorien,{" "}
                  {(preview.will_create?.channels || []).length} Kanäle
                </p>
              </div>
              {wipe && (
                <div className="rounded-2xl bg-red-500/[0.06] border border-red-500/25 p-4">
                  <p className="text-[10px] font-black uppercase tracking-widest text-red-400/70 mb-2">
                    Wird gelöscht
                  </p>
                  <p className="text-[12px] text-red-200/70 leading-relaxed">
                    {(preview.will_delete || []).length} Einträge
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Bericht nach dem Anwenden */}
        {report && (
          <div className={cn(CARD, "space-y-3")}>
            <h3 className="font-bold text-white">Ergebnis</h3>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: "Angelegt", value: report.created?.length || 0 },
                { label: "Gelöscht", value: report.deleted?.length || 0 },
                { label: "Fehler", value: report.errors?.length || 0 },
              ].map((entry) => (
                <div
                  key={entry.label}
                  className="rounded-2xl bg-[#0a1628] border border-slate-800 px-4 py-3"
                >
                  <p className="text-[9px] font-black uppercase tracking-widest text-slate-600">
                    {entry.label}
                  </p>
                  <p className="text-lg font-black text-white mt-1">
                    {entry.value}
                  </p>
                </div>
              ))}
            </div>

            {(report.errors || []).length > 0 && (
              <div className="rounded-2xl bg-red-500/[0.06] border border-red-500/25 p-4 space-y-1 max-h-52 overflow-y-auto">
                {report.errors.map((error: string, index: number) => (
                  <p key={index} className="text-[12px] text-red-200/80">
                    • {error}
                  </p>
                ))}
              </div>
            )}

            {(report.skipped || []).length > 0 && (
              <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-1 max-h-40 overflow-y-auto">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-1">
                  Übersprungen
                </p>
                {report.skipped.map((entry: string, index: number) => (
                  <p key={index} className="text-[12px] text-slate-500">
                    • {entry}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── Die Liste ────────────────────────────────────────────
  return (
    <div className="space-y-5">
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
            <Sparkles className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-bold text-white">Community-Vorlagen</h3>
            <p className="text-[12px] text-slate-500 mt-0.5">
              Von anderen Servern geteilt. {list.length}
              {list.length === 1 ? " Vorlage" : " Vorlagen"}
              {stats.up + stats.down > 0 && (
                <>
                  {" "}
                  &middot; {stats.up + stats.down} Bewertungen
                </>
              )}
            </p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={busy === "reload"}
            title="Neu laden"
            className="p-2.5 rounded-xl text-slate-600 hover:text-white hover:bg-white/[0.06] transition-all disabled:opacity-40"
          >
            <RefreshCcw
              className={cn(
                "h-4 w-4",
                busy === "reload" && "animate-spin"
              )}
            />
          </button>
        </div>

        <div className="relative">
          <Search className="h-4 w-4 text-slate-600 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Nach Name oder Beschreibung suchen …"
            className={cn(INPUT, "pl-11 pr-11")}
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              title="Suche leeren"
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-lg text-slate-600 hover:text-white transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Sortierung als Knöpfe statt als Auswahlliste.
            Ein <select> versteckt die Möglichkeiten hinter einem Klick;
            hier sieht man sofort, wonach sich ordnen lässt — und
            welche Ordnung gerade gilt. */}
        <div className="flex gap-1.5 flex-wrap">
          {SORTS.map((entry) => {
            const active = sort === entry.id;
            return (
              <button
                key={entry.id}
                onClick={() => setSort(entry.id)}
                title={entry.hint}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "flex items-center gap-1.5 px-3.5 py-2 rounded-xl border text-[11px] font-black uppercase tracking-widest transition-all",
                  active
                    ? "bg-primary/15 border-primary/40 text-primary"
                    : "bg-white/[0.03] border-white/10 text-slate-500 hover:text-slate-300"
                )}
              >
                <entry.icon className="h-3.5 w-3.5" />
                {entry.label}
              </button>
            );
          })}
        </div>

        {/* Filter. Bei drei Vorlagen unnötig, bei dreißig nicht mehr. */}
        <div className="flex gap-1.5 flex-wrap items-center">
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-600 mr-1">
            Zeigen
          </span>
          {FILTERS.map((entry) => {
            const active = filter === entry.id;
            return (
              <button
                key={entry.id}
                onClick={() => setFilter(entry.id)}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "px-3 py-1.5 rounded-lg border text-[11px] font-bold transition-all",
                  active
                    ? "bg-white/[0.08] border-white/20 text-white"
                    : "bg-transparent border-white/5 text-slate-600 hover:text-slate-400"
                )}
              >
                {entry.label}
              </button>
            );
          })}
        </div>

        {!canVote && (
          <p className="text-[11px] text-slate-600 leading-relaxed">
            Zum Bewerten musst du angemeldet sein.
          </p>
        )}
      </div>

      {visible.length === 0 ? (
        <div className={cn(CARD, "py-12 text-center space-y-3")}>
          <p className="text-[13px] text-slate-600">
            {search
              ? `Nichts gefunden für „${search}“.`
              : filter !== "alle"
              ? "Zu diesem Filter gibt es nichts."
              : "Noch keine Vorlagen. Lade als Erster deine hoch."}
          </p>
          {(search || filter !== "alle") && (
            <button
              onClick={() => {
                setSearch("");
                setFilter("alle");
              }}
              className="text-[11px] font-black uppercase tracking-widest text-primary/70 hover:text-primary transition-colors"
            >
              Filter zurücksetzen
            </button>
          )}
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          {visible.map((entry: any) => {
            const votes = entry.votes || { up: 0, down: 0, own: 0 };
            return (
              <div
                key={entry.id}
                className={cn(
                  "rounded-2xl border p-4 transition-all border-glow-card glow-r-2xl flex flex-col",
                  entry.blocked
                    ? "bg-red-500/[0.04] border-red-500/25"
                    : "bg-[#10233f] border-slate-800 hover:border-primary/40"
                )}
              >
                {/* Die Karte ist keine Schaltfläche mehr.
                    Vorher war die ganze Karte ein <button> — dann
                    lägen die Daumen als Schaltflächen darin, und ein
                    Klick auf »hoch« hätte zusätzlich die Vorlage
                    geöffnet. Verschachtelte Schaltflächen sind in HTML
                    ohnehin unzulässig. */}
                <button
                  onClick={() => open(entry)}
                  className="text-left min-w-0 group"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-[13.5px] font-bold text-white truncate group-hover:text-primary transition-colors">
                      {entry.name}
                    </p>
                    {entry.locked && (
                      <Lock className="h-3 w-3 text-amber-400 shrink-0" />
                    )}
                    {entry.blocked && (
                      <span className="text-[9px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded bg-red-500/15 text-red-300 border border-red-500/30 shrink-0">
                        Gesperrt
                      </span>
                    )}
                  </div>
                  {entry.description ? (
                    <p className="text-[12px] text-slate-500 mt-1 line-clamp-2 leading-relaxed">
                      {entry.description}
                    </p>
                  ) : (
                    <p className="text-[12px] text-slate-700 mt-1 italic">
                      Ohne Beschreibung.
                    </p>
                  )}
                </button>

                <div className="flex items-center gap-3 mt-3 text-[11px] text-slate-600 flex-wrap">
                  {entry.locked ? (
                    <span className="text-amber-400/70">
                      Vorschau nur mit Code
                    </span>
                  ) : (
                    <>
                      <span
                        className="flex items-center gap-1"
                        title={`${entry.summary.channels} Kanäle`}
                      >
                        <Hash className="h-3 w-3" />
                        {entry.summary.channels}
                      </span>
                      <span
                        className="flex items-center gap-1"
                        title={`${entry.summary.roles} Rollen`}
                      >
                        <Users className="h-3 w-3" />
                        {entry.summary.roles}
                      </span>
                      {entry.summary.features > 0 && (
                        <span
                          className="flex items-center gap-1"
                          title={`${entry.summary.features} Dashboard-Einstellungen`}
                        >
                          <Shield className="h-3 w-3" />
                          {entry.summary.features}
                        </span>
                      )}
                    </>
                  )}
                  <span
                    className="ml-auto"
                    title={`${entry.uses}× auf einen Server geholt`}
                  >
                    {entry.uses}&times; verwendet
                  </span>
                </div>

                {/* Bewertung */}
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-800/70">
                  <VoteButtons
                    votes={votes}
                    disabled={!canVote || busy === `vote${entry.id}`}
                    busy={busy === `vote${entry.id}`}
                    hint={
                      !canVote
                        ? "Zum Bewerten anmelden"
                        : entry.mine
                        ? "Die eigene Vorlage lässt sich nicht bewerten"
                        : ""
                    }
                    mine={Boolean(entry.mine)}
                    onVote={(value) => runVote(entry, value)}
                  />
                  {votes.up + votes.down > 0 && (
                    <span
                      className="ml-auto text-[10px] text-slate-600 tabular-nums"
                      title={`${votes.up} von ${votes.up + votes.down} Bewertungen positiv`}
                    >
                      {Math.round(
                        (votes.up / (votes.up + votes.down)) * 100
                      )}
                      % positiv
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
