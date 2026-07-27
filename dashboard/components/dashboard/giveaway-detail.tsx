"use client";

/**
 * One giveaway, in full.
 *
 * Opened by clicking a giveaway in the list. Three things live here that
 * the list cannot show:
 *
 *   * every text the giveaway sends, editable with a live preview
 *   * the entry requirements (role, messages, level, account age, …)
 *   * per-entrant odds — extra tickets or a guaranteed win
 *
 * The odds are deliberately kept out of the Discord message: the channel
 * only ever shows the plain entrant count, so nobody can read off that
 * somebody was favoured. That is also why the numbers are fetched from
 * the API instead of being computed here — only a signed-in dashboard
 * user with settings rights ever receives them.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowLeft, Clock, Crown, Dices, ExternalLink, Eye,
  Loader2, MessageSquare, Save, Search, Settings2, Shield, Ticket,
  Trophy, Users, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { RolePicker } from "@/components/dashboard/pickers";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

/** Every text the giveaway can send, with an explanation of when. */
const MESSAGE_FIELDS = [
  {
    key: "msg_joined",
    label: "Nach dem Teilnehmen",
    when: "Wird nur dem Teilnehmer gezeigt, direkt nach dem Knopfdruck.",
  },
  {
    key: "msg_left",
    label: "Beim Aussteigen",
    when: "Wenn jemand ein zweites Mal drückt und wieder rausgeht.",
  },
  {
    key: "msg_ended",
    label: "Gewinnspiel schon vorbei",
    when: "Wenn jemand drückt, nachdem ausgelost wurde.",
  },
  {
    key: "msg_denied",
    label: "Bedingungen nicht erfüllt",
    when: "Überschrift über der Liste, was noch fehlt.",
  },
  {
    key: "msg_winner_dm",
    label: "Private Nachricht an Gewinner",
    when: "Nur wenn „Gewinner per DM benachrichtigen\" an ist.",
  },
  {
    key: "msg_announce",
    label: "Bekanntgabe im Kanal",
    when: "Die öffentliche Nachricht mit den Gewinnern.",
  },
  {
    key: "msg_no_entries",
    label: "Niemand hat teilgenommen",
    when: "Statt der Bekanntgabe, wenn keiner mitgemacht hat.",
  },
] as const;

const TOKENS: Record<string, string> = {
  "{prize}": "Der Preis",
  "{winners}": "Anzahl Gewinner",
  "{entries}": "Teilnehmerzahl",
  "{ends}": "Endet in …",
  "{host}": "Wer es gestartet hat",
  "{winners_mentions}": "Die Gewinner (@…)",
  "{server}": "Servername",
};

const EXTEND = [
  { label: "+10 Min", minutes: 10 },
  { label: "+1 Std", minutes: 60 },
  { label: "+6 Std", minutes: 360 },
  { label: "+1 Tag", minutes: 1440 },
];

function fmt(unix: number) {
  if (!unix) return "—";
  return new Date(unix * 1000).toLocaleString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function relative(unix: number) {
  const diff = unix * 1000 - Date.now();
  const abs = Math.abs(diff);
  const m = 60_000, h = 60 * m, d = 24 * h;
  let text: string;
  if (abs < m) text = "unter 1 Min";
  else if (abs < h) text = `${Math.round(abs / m)} Min`;
  else if (abs < d) text = `${Math.round(abs / h)} Std`;
  else text = `${Math.round(abs / d)} Tage`;
  return diff > 0 ? `noch ${text}` : `vor ${text}`;
}

function Field({ label, hint, children }: any) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>}
    </div>
  );
}

function Toggle({ on, onChange, label }: any) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer">
      <button
        type="button"
        onClick={() => onChange(!on)}
        role="switch"
        aria-checked={on}
        className={cn(
          "relative h-6 w-11 rounded-full transition-colors shrink-0",
          on ? "bg-primary" : "bg-slate-700"
        )}
      >
        <span className={cn(
          "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform",
          on ? "translate-x-6" : "translate-x-1"
        )} />
      </button>
      <span className="text-sm text-slate-400">{label}</span>
    </label>
  );
}

/** Preview of one message, with the placeholders filled in. */
function Preview({ text, fallback, values }: any) {
  const filled = useMemo(() => {
    let out = (text || fallback || "").toString();
    for (const [token, value] of Object.entries(values)) {
      out = out.split(token).join(String(value));
    }
    return out;
  }, [text, fallback, values]);

  return (
    <div className="rounded-xl bg-[#0b1626] border border-slate-800/70 p-3.5">
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-1.5 flex items-center gap-1">
        <Eye className="h-3 w-3" /> So sieht es aus
      </p>
      <p className="text-sm text-slate-200 whitespace-pre-line break-words">
        {filled || <span className="italic text-slate-600">leer</span>}
      </p>
    </div>
  );
}

export function GiveawayDetail({
  guildId,
  messageId,
  onBack,
}: {
  guildId: string;
  messageId: string;
  onBack: () => void;
}) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"entries" | "texts" | "rules">("entries");
  const [draft, setDraft] = useState<any>({});
  const [query, setQuery] = useState("");
  const [boostFor, setBoostFor] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      const fresh = await api.getGiveaway(guildId, messageId);
      setData(fresh);
      setDraft({});
    } catch (err: any) {
      toast.error(err?.message || "Gewinnspiel konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId, messageId]);

  useEffect(() => { load(); }, [load]);

  const value = (key: string) =>
    draft[key] !== undefined ? draft[key] : data?.[key] ?? "";
  const set = (key: string, v: any) => setDraft((d: any) => ({ ...d, [key]: v }));
  const dirty = Object.keys(draft).length > 0;

  const save = async (extra: any = {}, note = "Gespeichert.") => {
    const payload = { ...draft, ...extra };
    if (Object.keys(payload).length === 0) return;
    setBusy(true);
    try {
      const res = await api.updateGiveaway(guildId, messageId, payload);
      toast.success(res?.result || note);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  // The unsaved winner count has to win over the stored one, otherwise
  // the preview shows the old number while you are typing the new one.
  const previewValues = useMemo(() => ({
    "{prize}": draft.prize ?? data?.prize ?? "…",
    "{winners}": String(draft.winners ?? data?.winners ?? 1),
    "{entries}": String(data?.entry_count ?? 0),
    "{ends}": fmt(data?.ends_at),
    "{host}": data?.host_name ? `@${data.host_name}` : "@Host",
    "{winners_mentions}": "@Alice, @Bob",
    "{server}": "dein Server",
  }), [data, draft]);

  const people = useMemo(() => {
    const list = data?.entries || [];
    const q = query.trim().toLowerCase();
    const filtered = q
      ? list.filter((p: any) => p.name.toLowerCase().includes(q) || p.id.includes(q))
      : list;
    // Favoured people first — they are the reason anybody opens this list.
    return [...filtered].sort((a: any, b: any) => {
      const rank = (p: any) => (p.guaranteed ? 2 : p.weight > 1 ? 1 : 0);
      return rank(b) - rank(a) || b.chance - a.chance;
    });
  }, [data, query]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-16 space-y-4">
        <p className="text-slate-400">Dieses Gewinnspiel gibt es nicht mehr.</p>
        <button onClick={onBack} className="text-primary text-sm font-bold">
          Zurück zur Übersicht
        </button>
      </div>
    );
  }

  return (
    <section className="space-y-6">
      {/* ── Boost dialog ─────────────────────────────── */}
      {boostFor && (
        <BoostDialog
          guildId={guildId}
          messageId={messageId}
          person={boostFor}
          onClose={() => setBoostFor(null)}
          onDone={async () => { setBoostFor(null); await load(); }}
        />
      )}

      {/* ── Header ───────────────────────────────────── */}
      <div className="flex items-start gap-4 flex-wrap">
        <button
          onClick={onBack}
          className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-white transition-all"
          title="Zurück"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-xl font-black text-white truncate">{data.prize}</h3>
            <span className={cn(
              "px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest",
              data.running
                ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                : "bg-slate-700/40 text-slate-400 border border-slate-700"
            )}>
              {data.running ? "läuft" : "beendet"}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            {data.channel && <>#{data.channel} · </>}
            {data.winners} Gewinner · {data.entry_count} Teilnehmer ·{" "}
            {fmt(data.ends_at)} ({relative(data.ends_at)})
          </p>
        </div>

        {data.url && (
          <a
            href={data.url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-primary transition-all"
            title="In Discord öffnen"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
      </div>

      {/* ── Quick actions ────────────────────────────── */}
      {data.running && (
        <div className="bg-[#10233f] border border-slate-800 rounded-2xl p-5 space-y-4">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
            <Clock className="h-3.5 w-3.5" /> Laufzeit verlängern
          </p>
          <div className="flex gap-2 flex-wrap">
            {EXTEND.map((e) => (
              <button
                key={e.minutes}
                disabled={busy}
                onClick={() => save({ extend_minutes: e.minutes }, "Verlängert.")}
                className="px-4 h-11 rounded-xl bg-[#0d1b31] border border-slate-800 text-sm font-bold text-slate-300 hover:text-primary hover:border-primary/40 transition-all disabled:opacity-40"
              >
                {e.label}
              </button>
            ))}
            <div className="flex items-center gap-2">
              <input
                type="number"
                placeholder="Min"
                id="extend-custom"
                className="h-11 w-24 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
              />
              <button
                disabled={busy}
                onClick={() => {
                  const el = document.getElementById("extend-custom") as HTMLInputElement;
                  const minutes = Number(el?.value);
                  if (!minutes) return toast.error("Bitte Minuten eintragen.");
                  save({ extend_minutes: minutes }, "Verlängert.");
                  el.value = "";
                }}
                className="h-11 px-4 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/25 transition-all disabled:opacity-40"
              >
                Verlängern
              </button>
            </div>
          </div>
          <p className="text-[11px] text-slate-600">
            Eine negative Zahl kürzt die Laufzeit. Ein bereits abgelaufenes
            Gewinnspiel läuft dadurch wieder weiter.
          </p>
        </div>
      )}

      {/* ── Tabs ─────────────────────────────────────── */}
      <div className="flex gap-1.5 flex-wrap">
        {[
          { id: "entries", label: "Teilnehmer", icon: Users },
          { id: "texts", label: "Texte", icon: MessageSquare },
          { id: "rules", label: "Bedingungen", icon: Shield },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id as any)}
            className={cn(
              "flex items-center gap-2 px-4 h-11 rounded-xl text-xs font-black uppercase tracking-widest border transition-all",
              tab === t.id
                ? "bg-primary/15 border-primary/40 text-primary"
                : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
            )}
          >
            <t.icon className="h-3.5 w-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* ══ Entrants ══════════════════════════════════ */}
      {tab === "entries" && (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-5">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Name oder ID suchen"
                className={cn(INPUT, "pl-10")}
              />
            </div>
            <span className="text-xs text-slate-500">
              {data.entry_count} Teilnehmer
            </span>
          </div>

          <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-amber-200/80 leading-relaxed">
              Extra-Lose und garantierte Gewinner stehen <b>nirgends</b> in
              Discord — weder in der Gewinnspiel-Nachricht noch in der
              Bekanntgabe. Nur wer dieses Dashboard öffnen darf, sieht sie.
            </p>
          </div>

          {people.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-10">
              {query ? "Niemand gefunden." : "Noch hat niemand teilgenommen."}
            </p>
          ) : (
            <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1">
              {people.map((p: any) => (
                <div
                  key={p.id}
                  className={cn(
                    "flex items-center gap-3 rounded-2xl border px-4 py-3 flex-wrap",
                    p.guaranteed
                      ? "bg-amber-500/[0.07] border-amber-500/30"
                      : p.weight > 1
                        ? "bg-primary/[0.05] border-primary/25"
                        : "bg-[#0d1b31] border-slate-800"
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-white truncate flex items-center gap-2">
                      {p.guaranteed && <Crown className="h-3.5 w-3.5 text-amber-400 shrink-0" />}
                      <span className={cn(p.left && "italic text-slate-500")}>
                        {p.name}
                      </span>
                      {p.won && (
                        <span className="px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 text-[10px] font-black uppercase">
                          hat gewonnen
                        </span>
                      )}
                      {p.not_entered && (
                        <span className="px-2 py-0.5 rounded-md bg-slate-700/50 text-slate-400 text-[10px] font-black uppercase">
                          nicht dabei
                        </span>
                      )}
                    </p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {p.guaranteed
                        ? "Gewinnt garantiert"
                        : p.weight > 1
                          ? `${p.weight} Lose · ${p.chance}% Chance`
                          : `${p.chance}% Chance`}
                      {p.note && <> · {p.note}</>}
                    </p>
                  </div>

                  <button
                    onClick={() => setBoostFor(p)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
                  >
                    <Ticket className="h-3.5 w-3.5" />
                    Chance
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ══ Texts ═════════════════════════════════════ */}
      {tab === "texts" && (
        <div className="space-y-5">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-5">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Die Nachricht im Kanal
            </p>

            <div className="grid lg:grid-cols-2 gap-5">
              <Field label="Überschrift" hint="Leer = 🎉 Gewinnspiel">
                <input
                  value={value("title")}
                  onChange={(e) => set("title", e.target.value)}
                  placeholder="🎉 Gewinnspiel"
                  className={INPUT}
                />
              </Field>
              <Field label="Knopf-Text" hint="Leer = 🎉 Teilnehmen">
                <div className="flex gap-2">
                  <input
                    value={value("button_emoji")}
                    onChange={(e) => set("button_emoji", e.target.value)}
                    placeholder="🎉"
                    className="w-16 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 py-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
                  />
                  <input
                    value={value("button_label")}
                    onChange={(e) => set("button_label", e.target.value)}
                    placeholder="Teilnehmen"
                    className={cn(INPUT, "flex-1")}
                  />
                </div>
              </Field>
            </div>

            <Field label="Beschreibung">
              <textarea
                value={value("description")}
                onChange={(e) => set("description", e.target.value)}
                rows={4}
                className={cn(INPUT, "resize-y font-mono text-[13px]")}
              />
            </Field>
            <Preview
              text={value("description")}
              fallback={"**{prize}**\n\nDrücke den Knopf, um teilzunehmen.\n**Gewinner:** {winners}\n**Endet:** {ends}"}
              values={previewValues}
            />
          </div>

          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-6">
            <div>
              <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                Antworten an die Teilnehmer
              </p>
              <p className="text-[11px] text-slate-600 mt-1.5">
                Jedes Feld leer lassen heißt: der Standardtext wird benutzt.
                Er steht als graue Vorschau darunter.
              </p>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {Object.entries(TOKENS).map(([token, hint]) => (
                <span
                  key={token}
                  title={hint}
                  className="px-2 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] font-mono text-slate-400"
                >
                  {token}
                </span>
              ))}
            </div>

            {MESSAGE_FIELDS.map((f) => (
              <div key={f.key} className="space-y-2.5 border-t border-slate-800 pt-5">
                <Field label={f.label} hint={f.when}>
                  <textarea
                    value={value(f.key)}
                    onChange={(e) => set(f.key, e.target.value)}
                    rows={2}
                    placeholder={data.defaults?.[f.key]}
                    className={cn(INPUT, "resize-y")}
                  />
                </Field>
                <Preview
                  text={value(f.key)}
                  fallback={data.defaults?.[f.key]}
                  values={previewValues}
                />
              </div>
            ))}

            <div className="border-t border-slate-800 pt-5 flex flex-wrap gap-5">
              <Toggle
                on={value("dm_winners")}
                onChange={(v: boolean) => set("dm_winners", v)}
                label="Gewinner per DM benachrichtigen"
              />
              <Toggle
                on={value("dm_host")}
                onChange={(v: boolean) => set("dm_host", v)}
                label="Zusammenfassung an den Veranstalter"
              />
              <Toggle
                on={value("allow_leave")}
                onChange={(v: boolean) => set("allow_leave", v)}
                label="Aussteigen erlauben (nochmal drücken)"
              />
            </div>
          </div>
        </div>
      )}

      {/* ══ Requirements ══════════════════════════════ */}
      {tab === "rules" && (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-6">
          <div>
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Wer darf teilnehmen
            </p>
            <p className="text-[11px] text-slate-600 mt-1.5">
              Alles auf 0 oder leer heißt: keine Einschränkung. Die Bedingungen
              stehen auch in der Gewinnspiel-Nachricht, damit niemand erst nach
              dem Klick erfährt, dass er nicht darf.
            </p>
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            <Field label="Rolle nötig" hint="Nur wer diese Rolle hat, darf mitmachen.">
              <RolePicker
                guildId={guildId}
                value={value("required_role_id") || ""}
                onChange={(id) => set("required_role_id", id || "")}
                placeholder="Keine Einschränkung"
              />
            </Field>

            <Field label="Rolle ausgeschlossen" hint="Wer diese Rolle hat, darf nicht.">
              <RolePicker
                guildId={guildId}
                value={value("blocked_role_id") || ""}
                onChange={(id) => set("blocked_role_id", id || "")}
                placeholder="Niemand ausgeschlossen"
              />
            </Field>

            <Field
              label="Mindestens X Nachrichten"
              hint="Zählt die Nachrichten aus dem Level-System dieses Servers."
            >
              <input
                type="number"
                min={0}
                value={value("min_messages") || 0}
                onChange={(e) => set("min_messages", Number(e.target.value) || 0)}
                className={INPUT}
              />
            </Field>

            <Field label="Mindestens Level X" hint="Ebenfalls aus dem Level-System.">
              <input
                type="number"
                min={0}
                value={value("min_level") || 0}
                onChange={(e) => set("min_level", Number(e.target.value) || 0)}
                className={INPUT}
              />
            </Field>

            <Field
              label="Discord-Account mindestens X Tage alt"
              hint="Hält frisch erstellte Zweitaccounts draußen."
            >
              <input
                type="number"
                min={0}
                value={value("min_account_days") || 0}
                onChange={(e) => set("min_account_days", Number(e.target.value) || 0)}
                className={INPUT}
              />
            </Field>

            <Field
              label="Mindestens X Tage auf dem Server"
              hint="Wer gerade erst beigetreten ist, darf noch nicht."
            >
              <input
                type="number"
                min={0}
                value={value("min_member_days") || 0}
                onChange={(e) => set("min_member_days", Number(e.target.value) || 0)}
                className={INPUT}
              />
            </Field>
          </div>

          <div className="border-t border-slate-800 pt-5 grid lg:grid-cols-2 gap-5">
            <Field label="Anzahl Gewinner">
              <input
                type="number"
                min={1}
                max={20}
                value={value("winners") || data.winners}
                onChange={(e) =>
                  set("winners", Math.max(1, Math.min(20, Number(e.target.value) || 1)))
                }
                className={INPUT}
              />
            </Field>
            <Field label="Preis">
              <input
                value={value("prize") || data.prize}
                onChange={(e) => set("prize", e.target.value)}
                className={INPUT}
              />
            </Field>
          </div>
        </div>
      )}

      {/* ── Sticky save bar ──────────────────────────── */}
      {dirty && (
        <div className="sticky bottom-4 z-30">
          <div className="bg-[#10233f]/95 backdrop-blur border border-primary/30 rounded-2xl p-4 flex items-center gap-4 flex-wrap shadow-2xl">
            <Settings2 className="h-4 w-4 text-primary shrink-0" />
            <p className="text-sm text-slate-300 flex-1 min-w-[160px]">
              {Object.keys(draft).length} Änderung
              {Object.keys(draft).length === 1 ? "" : "en"} noch nicht gespeichert.
            </p>
            <button
              onClick={() => setDraft({})}
              className="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white transition-all"
            >
              Verwerfen
            </button>
            <button
              onClick={() => save()}
              disabled={busy}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              Speichern
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * Boost dialog
 * ------------------------------------------------------------------ */

function BoostDialog({ guildId, messageId, person, onClose, onDone }: any) {
  const [mode, setMode] = useState<"weight" | "guaranteed" | "clear">(
    person.guaranteed ? "guaranteed" : person.weight > 1 ? "weight" : "weight"
  );
  const [weight, setWeight] = useState(person.weight > 1 ? person.weight : 100);
  const [note, setNote] = useState(person.note || "");
  const [busy, setBusy] = useState(false);

  const apply = async () => {
    setBusy(true);
    try {
      const res = await api.boostGiveawayEntrant(guildId, messageId, {
        user_id: person.id,
        mode,
        weight,
        note,
      });
      toast.success(res?.result || "Gespeichert.");
      await onDone();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl w-full max-w-lg shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-5 border-b border-slate-800 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-black text-white truncate">{person.name}</h3>
            <p className="text-[11px] text-slate-500">Gewinnchance anpassen</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white shrink-0">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-amber-200/80 leading-relaxed">
              Bleibt geheim: In Discord ändert sich nichts an der Nachricht.
              Im Server-Protokoll wird es aber festgehalten.
            </p>
          </div>

          <div className="space-y-2">
            {[
              {
                id: "weight",
                icon: Dices,
                label: "Bessere Chance",
                desc: "Mehrere Lose statt einem. Gewinnen ist wahrscheinlicher, aber nicht sicher.",
              },
              {
                id: "guaranteed",
                icon: Trophy,
                label: "Gewinnt garantiert",
                desc: "Wird auf jeden Fall gezogen — belegt einen der Gewinnerplätze.",
              },
              {
                id: "clear",
                icon: Users,
                label: "Normal wie alle",
                desc: "Alles zurücksetzen, ein Los wie jeder andere.",
              },
            ].map((o) => (
              <button
                key={o.id}
                onClick={() => setMode(o.id as any)}
                className={cn(
                  "w-full text-left flex gap-3 rounded-2xl border p-4 transition-all",
                  mode === o.id
                    ? "bg-primary/10 border-primary/40"
                    : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                )}
              >
                <o.icon className={cn(
                  "h-4 w-4 shrink-0 mt-0.5",
                  mode === o.id ? "text-primary" : "text-slate-500"
                )} />
                <div className="min-w-0">
                  <p className="text-sm font-bold text-white">{o.label}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                    {o.desc}
                  </p>
                </div>
              </button>
            ))}
          </div>

          {mode === "weight" && (
            <div className="space-y-3">
              <Field
                label="Anzahl Lose"
                hint="Jeder andere hat ein Los. Bei 100 Losen ist diese Person 100-mal so wahrscheinlich dran."
              >
                <div className="flex gap-1.5 flex-wrap">
                  {[2, 5, 10, 50, 100].map((n) => (
                    <button
                      key={n}
                      onClick={() => setWeight(n)}
                      className={cn(
                        "h-11 px-4 rounded-xl text-sm font-bold border transition-all",
                        weight === n
                          ? "bg-primary/15 border-primary/40 text-primary"
                          : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:text-slate-200"
                      )}
                    >
                      {n}
                    </button>
                  ))}
                  <input
                    type="number"
                    min={2}
                    value={weight}
                    onChange={(e) => setWeight(Math.max(2, Number(e.target.value) || 2))}
                    className="h-11 w-24 bg-[#0d1b31] border border-slate-800 rounded-xl px-3 text-sm text-white text-center focus:outline-none focus:border-primary/50"
                  />
                </div>
              </Field>
            </div>
          )}

          {mode !== "clear" && (
            <Field label="Notiz (nur für dich)" hint="Warum, damit du es später noch weißt.">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="z. B. Booster seit 2 Jahren"
                className={INPUT}
              />
            </Field>
          )}
        </div>

        <div className="p-5 border-t border-slate-800 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white transition-all"
          >
            Abbrechen
          </button>
          <button
            onClick={apply}
            disabled={busy}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            Übernehmen
          </button>
        </div>
      </div>
    </div>
  );
}
