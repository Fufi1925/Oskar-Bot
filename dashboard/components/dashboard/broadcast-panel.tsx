"use client";

/**
 * Admin broadcast: one message to every server the bot is on.
 *
 * The tab this replaces was called "Global Broadcast" and sent nothing
 * to Discord at all — it wrote the dashboard's own notification banner.
 * The route that actually delivered had no interface and was reachable
 * with curl only.
 *
 * Because a broadcast cannot be recalled once it is out, the flow here
 * is deliberately slow: write, preview where it would land, optionally
 * send to one server first, and only then to everybody.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, CalendarClock, Check, ChevronDown, Clock, Eye, Loader2,
  Megaphone, RefreshCw, Send, Server, X, XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { EmojiPicker } from "@/components/dashboard/emoji-picker";

const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

const TONES = [
  { id: "info", label: "Neutral", colour: "#3d7cff" },
  { id: "success", label: "Gut", colour: "#2ecc71" },
  { id: "warning", label: "Achtung", colour: "#f1c40f" },
  { id: "error", label: "Dringend", colour: "#e74c3c" },
  { id: "brand", label: "Marke", colour: "#5865f2" },
];

const STATUS_LABEL: Record<string, string> = {
  draft: "Entwurf",
  scheduled: "Eingeplant",
  sending: "Wird gesendet",
  sent: "Verschickt",
  cancelled: "Zurückgenommen",
};

function when(unix?: number | null) {
  if (!unix) return "—";
  return new Date(unix * 1000).toLocaleString("de-DE", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
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

export function BroadcastPanel({ guilds }: { guilds?: any[] }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<any>(null);
  const [openResult, setOpenResult] = useState<any>(null);

  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [tone, setTone] = useState("info");
  const [imageUrl, setImageUrl] = useState("");
  const [target, setTarget] = useState("channel");
  const [scheduleAt, setScheduleAt] = useState("");
  const [testGuild, setTestGuild] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api.getBroadcasts());
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const payload = useMemo(() => ({
    title: title.trim(),
    message: message.trim(),
    tone,
    image_url: imageUrl.trim(),
    target,
  }), [title, message, tone, imageUrl, target]);

  const ready = payload.message.length > 0;

  const preview = async () => {
    if (!ready) return toast.error("Bitte zuerst eine Nachricht schreiben.");
    setBusy(true);
    try {
      setPlan(await api.previewBroadcast(payload));
    } catch (err: any) {
      toast.error(err?.message || "Vorschau fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async () => {
    if (!ready) return toast.error("Bitte zuerst eine Nachricht schreiben.");
    if (!testGuild) return toast.error("Bitte einen Server für den Test wählen.");
    setBusy(true);
    try {
      const res = await api.testBroadcast({ ...payload, guild_id: testGuild });
      toast.success(res?.result || "Test verschickt.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Test fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!ready) return toast.error("Bitte zuerst eine Nachricht schreiben.");

    const reach = plan?.reachable ?? data?.guild_count ?? 0;
    const scheduled = scheduleAt
      ? Math.floor(new Date(scheduleAt).getTime() / 1000)
      : null;

    if (!scheduled) {
      const ok = confirm(
        `Diese Nachricht geht an ${reach} Server und lässt sich danach nicht ` +
        `mehr zurückholen.\n\nWirklich jetzt senden?`
      );
      if (!ok) return;
    }

    setBusy(true);
    try {
      const res = await api.sendBroadcast({ ...payload, send_at: scheduled });
      toast.success(res?.result || "Verschickt.");
      setMessage("");
      setTitle("");
      setScheduleAt("");
      setPlan(null);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Senden fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<any>, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.result || "Erledigt.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const openDetail = async (id: number) => {
    try {
      setOpenResult(await api.getBroadcast(id));
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    }
  };

  const toneColour = TONES.find((t) => t.id === tone)?.colour || "#3d7cff";

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      {/* ── Result dialog ────────────────────────────── */}
      {openResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-[#131318] border border-slate-800 rounded-3xl w-full max-w-lg shadow-2xl max-h-[85vh] flex flex-col border-glow-card">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-black text-white truncate">
                  {openResult.title || "Ohne Überschrift"}
                </h3>
                <p className="text-[11px] text-slate-500">
                  {openResult.delivered} zugestellt · {openResult.failed} fehlgeschlagen
                </p>
              </div>
              <button
                onClick={() => setOpenResult(null)}
                className="text-slate-500 hover:text-white shrink-0"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-5 overflow-y-auto space-y-1.5">
              {(openResult.results || []).length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-6">
                  Noch keine Ergebnisse.
                </p>
              ) : (
                openResult.results.map((r: any) => (
                  <div
                    key={r.guild_id}
                    className="flex items-center gap-2.5 text-sm py-1.5"
                  >
                    {r.ok ? (
                      <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
                    )}
                    <span className="truncate flex-1 text-slate-300">
                      {r.guild_name || r.guild_id}
                    </span>
                    {r.detail && (
                      <span className="text-[10px] text-slate-600 shrink-0">
                        {r.detail}
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>

            {openResult.failed > 0 && (
              <div className="p-5 border-t border-slate-800">
                <button
                  onClick={() =>
                    act(async () => {
                      const res = await api.resendBroadcast(openResult.id);
                      setOpenResult(null);
                      return res;
                    })
                  }
                  disabled={busy}
                  className="w-full py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
                >
                  Die {openResult.failed} fehlgeschlagenen erneut versuchen
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Compose ──────────────────────────────────── */}
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
              <Megaphone className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="font-black text-white">Nachricht an alle Server</p>
              <p className="text-[11px] text-slate-500">
                Der Bot ist auf {data?.guild_count ?? 0} Servern.
              </p>
            </div>
          </div>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06]"
          >
            <RefreshCw className="h-4 w-4 text-primary" />
          </button>
        </div>

        <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-amber-200/80 leading-relaxed">
            Eine verschickte Nachricht lässt sich nicht zurückholen. Schau dir
            erst die Vorschau an und schick sie testweise an einen Server.
          </p>
        </div>

        <Field label="Überschrift" hint="Leer = „Nachricht vom Bot-Team“">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Wartungsarbeiten am Sonntag"
            maxLength={200}
            className={INPUT}
          />
          <div className="mt-2">
            <EmojiPicker
              onPick={(raw) =>
                setTitle((old) => ((old + raw).length > 200 ? old : old + raw))
              }
            />
          </div>
        </Field>

        <Field label="Nachricht">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={6}
            placeholder="Was alle Server wissen sollen …"
            maxLength={3500}
            className={cn(INPUT, "resize-y")}
          />
          <div className="mt-2">
            <EmojiPicker
              onPick={(raw) =>
                setMessage((old) => ((old + raw).length > 3500 ? old : old + raw))
              }
            />
          </div>
          <p className="text-[11px] text-slate-600 text-right">
            {message.length} / 3500
          </p>
        </Field>

        <div className="grid lg:grid-cols-2 gap-5">
          <Field label="Farbe / Dringlichkeit">
            <div className="flex gap-1.5 flex-wrap">
              {TONES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTone(t.id)}
                  className={cn(
                    "flex items-center gap-2 px-3 h-11 rounded-xl text-xs font-bold border transition-all",
                    tone === t.id
                      ? "border-primary/40 bg-primary/10 text-white"
                      : "bg-[#0e0e12] border-slate-800 text-slate-400 hover:text-slate-200"
                  )}
                >
                  <span
                    className="h-3 w-3 rounded-full shrink-0"
                    style={{ background: t.colour }}
                  />
                  {t.label}
                </button>
              ))}
            </div>
          </Field>

          <Field label="Bild (URL)" hint="Optional, muss mit https:// anfangen.">
            <input
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              placeholder="https://…"
              className={INPUT}
            />
          </Field>
        </div>

        <Field label="Wohin">
          <div className="grid md:grid-cols-3 gap-2">
            {(data?.targets || []).map((t: any) => (
              <button
                key={t.id}
                onClick={() => { setTarget(t.id); setPlan(null); }}
                className={cn(
                  "text-left rounded-2xl border p-4 transition-all",
                  target === t.id
                    ? "bg-primary/10 border-primary/40"
                    : "bg-[#0e0e12] border-slate-800 hover:border-slate-700"
                )}
              >
                <Server className={cn(
                  "h-4 w-4 mb-2",
                  target === t.id ? "text-primary" : "text-slate-500"
                )} />
                <p className="text-sm font-bold text-white">{t.label}</p>
              </button>
            ))}
          </div>
        </Field>

        {/* Live preview of the card the servers will see */}
        <div className="rounded-2xl bg-[#0b1626] border border-slate-800/70 p-4">
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2 flex items-center gap-1">
            <Eye className="h-3 w-3" /> So kommt es an
          </p>
          <div
            className="rounded border-l-4 bg-[#2b2d31] p-4"
            style={{ borderLeftColor: toneColour }}
          >
            <p className="font-bold text-white text-[15px]">
              {title || "Nachricht vom Bot-Team"}
            </p>
            <p className="text-sm text-[#dbdee1] whitespace-pre-line break-words mt-1.5">
              {message || <span className="italic text-slate-600">leer</span>}
            </p>
          </div>
        </div>

        {/* Where it would land */}
        {plan && (
          <div className="rounded-2xl bg-[#0b1626] border border-slate-800/70 p-4 space-y-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-600">
              Vorschau — {plan.reachable} von {plan.guilds} Servern erreichbar
            </p>
            <div className="max-h-52 overflow-y-auto space-y-1">
              {(plan.plan || []).map((p: any) => (
                <div key={p.guild_id} className="flex items-center gap-2 text-[12px]">
                  {p.reachable ? (
                    <Check className="h-3 w-3 text-emerald-400 shrink-0" />
                  ) : (
                    <XCircle className="h-3 w-3 text-red-400 shrink-0" />
                  )}
                  <span className="truncate flex-1 text-slate-300">{p.guild_name}</span>
                  <span className="text-[10px] text-slate-600 shrink-0">
                    {p.channel ? `#${p.channel}` : p.owner ? "DM" : "kein Weg"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Test to one server */}
        <div className="grid md:grid-cols-[1fr_auto] gap-3 items-end">
          <Field label="Testweise an einen Server">
            <select
              value={testGuild}
              onChange={(e) => setTestGuild(e.target.value)}
              className={INPUT}
            >
              <option value="">Server wählen …</option>
              {(guilds || []).map((g: any) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </Field>
          <button
            onClick={sendTest}
            disabled={busy || !ready || !testGuild}
            className="h-[46px] px-5 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
          >
            Test senden
          </button>
        </div>

        <Field
          label="Später senden"
          hint="Leer lassen, um sofort zu verschicken. Eingeplante Nachrichten lassen sich zurücknehmen."
        >
          <input
            type="datetime-local"
            value={scheduleAt}
            onChange={(e) => setScheduleAt(e.target.value)}
            className={INPUT}
          />
        </Field>

        <div className="flex gap-3 flex-wrap">
          <button
            onClick={preview}
            disabled={busy || !ready}
            className="flex-1 min-w-[160px] flex items-center justify-center gap-2 py-4 rounded-2xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
            Wohin geht es?
          </button>
          <button
            onClick={send}
            disabled={busy || !ready}
            className="flex-1 min-w-[160px] flex items-center justify-center gap-2 py-4 rounded-2xl bg-primary text-xs font-black uppercase tracking-widest shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : scheduleAt ? (
              <CalendarClock className="h-4 w-4" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            {scheduleAt ? "Einplanen" : "Jetzt an alle senden"}
          </button>
        </div>
      </div>

      {/* ── History ──────────────────────────────────── */}
      <div>
        <h3 className="font-black text-white flex items-center gap-2 mb-3">
          <Clock className="h-5 w-5 text-slate-500" />
          Bisherige Nachrichten
          <span className="text-xs font-normal text-slate-500">
            ({data?.broadcasts?.length || 0})
          </span>
        </h3>

        {!data?.broadcasts?.length ? (
          <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-800 rounded-2xl">
            Noch nichts verschickt.
          </p>
        ) : (
          <div className="space-y-2">
            {data.broadcasts.map((b: any) => (
              <div
                key={b.id}
                className="bg-[#131318] border border-slate-800 rounded-2xl px-5 py-3.5 flex items-center gap-4 flex-wrap"
              >
                <button
                  onClick={() => openDetail(b.id)}
                  className="min-w-0 flex-1 text-left group"
                >
                  <p className="font-bold text-slate-200 truncate group-hover:text-primary transition-colors">
                    {b.title || b.message.slice(0, 60)}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {STATUS_LABEL[b.status] || b.status}
                    {b.status === "sent" && ` · ${b.delivered} zugestellt`}
                    {b.failed > 0 && ` · ${b.failed} fehlgeschlagen`}
                    {b.status === "scheduled" && ` · ${when(b.send_at)}`}
                    {b.created_at && ` · erstellt ${when(b.created_at)}`}
                  </p>
                </button>

                {b.status === "scheduled" && (
                  <button
                    onClick={() =>
                      act(
                        () => api.cancelBroadcast(b.id),
                        "Diese eingeplante Nachricht zurücknehmen?"
                      )
                    }
                    disabled={busy}
                    className="px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-400 hover:text-red-400 disabled:opacity-40 transition-all shrink-0"
                  >
                    Zurücknehmen
                  </button>
                )}
                {b.failed > 0 && (
                  <span className="px-2.5 py-1 rounded-lg bg-red-500/10 text-red-300 text-[10px] font-black uppercase shrink-0">
                    {b.failed} offen
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
