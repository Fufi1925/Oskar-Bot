"use client";

/**
 * Der Tester-Reiter.
 *
 * Wer die Rolle **Tester** hat, sieht im Admin-Panel genau diese eine
 * Seite. Zwei Dinge stehen darauf:
 *
 *   1. **Was zuletzt ausgeliefert wurde** — aus den Git-Commits, also
 *      ohne dass jemand eine Liste pflegen muss. Neue Funktionen stehen
 *      oben und mit einer kurzen Erklärung, weil das die sind, die
 *      jemand ausprobieren soll.
 *   2. **Ein Formular für Fehler und Vorschläge.** Ein Tester sieht
 *      seine eigenen Meldungen wieder — damit er weiß, dass sie
 *      angekommen sind, und nicht dieselbe Sache dreimal schickt.
 *
 * Owner sehen zusätzlich alle Meldungen, können den Stand setzen und
 * sehen, wer die Rolle hat — also wer gerade Premium ohne Key hat.
 *
 * Die Rechte hängen nicht an dieser Datei. Der Bot prüft jede Anfrage
 * gegen die Tester-Rolle; wird sie entzogen, ist der Reiter beim
 * nächsten Laden weg und das Premium sofort mit.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bug,
  CheckCircle2,
  Clock,
  Gem,
  Lightbulb,
  Loader2,
  RefreshCw,
  Rocket,
  Send,
  Users,
  Wrench,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";

/** Wie ein Änderungstyp aussieht. */
const TONES: Record<string, { border: string; text: string; icon: any }> = {
  new: { border: "border-emerald-500/30", text: "text-emerald-300", icon: Rocket },
  fix: { border: "border-sky-500/30", text: "text-sky-300", icon: Wrench },
  chore: { border: "border-slate-700", text: "text-slate-400", icon: Clock },
};

const STATES: Record<string, { label: string; tone: string }> = {
  open: { label: "offen", tone: "text-amber-300 bg-amber-500/15" },
  planned: { label: "geplant", tone: "text-sky-300 bg-sky-500/15" },
  done: { label: "erledigt", tone: "text-emerald-300 bg-emerald-500/15" },
  rejected: { label: "abgelehnt", tone: "text-slate-400 bg-slate-700/40" },
};

function when(seconds?: number | null) {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TesterPanel() {
  const [loading, setLoading] = useState(true);
  const [state, setState] = useState<any>(null);
  const [log, setLog] = useState<any>(null);
  const [feedback, setFeedback] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [scope, setScope] = useState("own");
  const [members, setMembers] = useState<any[]>([]);
  const [error, setError] = useState("");

  // Formular
  const [kind, setKind] = useState("bug");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    // allSettled: fällt der Changelog aus, soll das Formular trotzdem
    // stehen. Mit Promise.all verlöre man beides.
    const [status, changes, entries] = await Promise.allSettled([
      api.testerStatus(),
      api.testerChangelog(30),
      api.testerFeedback(100),
    ]);

    if (status.status === "fulfilled") {
      setState(status.value);
      setError("");
      // Die Mitgliederliste gibt es nur für Owner — sonst wäre der
      // Aufruf ein garantierter 403 in der Konsole.
      if (status.value?.owner) {
        try {
          const list = await api.testerMembers();
          setMembers(list?.members ?? []);
        } catch {
          setMembers([]);
        }
      }
    } else {
      setError(status.reason?.message || "Der Zugang ließ sich nicht prüfen.");
    }

    if (changes.status === "fulfilled") setLog(changes.value);

    if (entries.status === "fulfilled") {
      setFeedback(entries.value?.entries ?? []);
      setStats(entries.value?.stats ?? null);
      setScope(entries.value?.scope ?? "own");
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (title.trim().length < 3) {
      toast.error("Der Titel ist zu kurz.");
      return;
    }
    setSending(true);
    try {
      await api.testerSubmit(kind, title.trim(), body.trim());
      toast.success("Danke — die Meldung ist angekommen.");
      setTitle("");
      setBody("");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setSending(false);
    }
  };

  const setEntryState = async (id: number, next: string) => {
    try {
      await api.testerSetState(id, next);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    }
  };

  // Neue Funktionen zuerst: das sind die, die ausprobiert werden
  // sollen. Danach Fehlerbehebungen, dann der Rest.
  const grouped = useMemo(() => {
    const entries = log?.entries ?? [];
    const order = ["new", "fix", "chore"];
    return order
      .map((tone) => ({
        tone,
        items: entries.filter((entry: any) => entry.tone === tone),
      }))
      .filter((group) => group.items.length > 0);
  }, [log]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const isOwner = Boolean(state?.owner);

  return (
    <section className="space-y-6">
      {/* ── Kopf ─────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex gap-3">
          <div className="h-10 w-10 rounded-2xl bg-violet-500/15 grid place-items-center shrink-0">
            <Bug className="h-5 w-5 text-violet-300" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white flex items-center gap-2 flex-wrap">
              Tester
              {state?.role_label && (
                <span className="px-1.5 py-0.5 rounded text-[9px] font-black tracking-widest bg-violet-500/15 text-violet-300">
                  {state.role_label.toUpperCase()}
                </span>
              )}
            </p>
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              Was zuletzt ausgeliefert wurde, und ein Weg, Fehler und
              Vorschläge loszuwerden.
            </p>
          </div>
          <button
            onClick={() => {
              setLoading(true);
              load();
            }}
            className="ml-auto shrink-0 h-9 w-9 rounded-xl border border-slate-800 grid place-items-center text-slate-400 hover:text-white hover:border-slate-700 transition-colors"
            title="Neu laden"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <div className="rounded-xl bg-red-500/[0.06] border border-red-500/20 p-3.5 flex gap-2.5">
            <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-200/80 leading-relaxed">{error}</p>
          </div>
        )}

        {state?.premium_bypass && (
          <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
            <Gem className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-[12px] text-amber-200/90 font-bold">
                Premium ist für dich freigeschaltet
              </p>
              <p className="text-[11px] text-amber-200/70 mt-1 leading-relaxed">
                Solange du die Tester-Rolle hast, gilt jede Premium-Funktion
                als freigeschaltet — ohne Key. Wird die Rolle entzogen, ist
                der Zugang sofort weg.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── Was zuletzt kam ──────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex items-center gap-3 flex-wrap">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            Zuletzt ausgeliefert
          </p>
          {log?.commit && (
            <span className="text-[10px] font-mono text-slate-600">
              {log.commit} · {when(log.deployed_at)}
            </span>
          )}
          {log?.features > 0 && (
            <span className="ml-auto text-[10px] font-black uppercase tracking-wider text-emerald-300">
              {log.features} neue{log.features === 1 ? "" : ""} Funktion
              {log.features === 1 ? "" : "en"}
            </span>
          )}
        </div>

        {!log?.entries?.length ? (
          <p className="text-[12px] text-slate-500">
            Hier steht noch nichts. Die Liste kommt aus den Git-Commits —
            fehlt sie, wurde beim Bauen keine Historie mitgegeben.
          </p>
        ) : (
          <div className="space-y-4">
            {grouped.map((group) => {
              const tone = TONES[group.tone] ?? TONES.chore;
              const Icon = tone.icon;
              return (
                <div key={group.tone} className="space-y-2">
                  <p
                    className={cn(
                      "text-[10px] font-black uppercase tracking-widest",
                      tone.text
                    )}
                  >
                    {group.tone === "new"
                      ? "Neue Funktionen"
                      : group.tone === "fix"
                      ? "Behoben"
                      : "Sonstiges"}
                  </p>
                  {group.items.map((entry: any) => (
                    <div
                      key={entry.commit}
                      className={cn(
                        "rounded-2xl border bg-[#0d1b31] p-4",
                        tone.border
                      )}
                    >
                      <div className="flex items-start gap-2.5">
                        <Icon
                          className={cn("h-4 w-4 shrink-0 mt-0.5", tone.text)}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-bold text-white leading-snug">
                            {entry.scope && (
                              <span className={cn("mr-1.5", tone.text)}>
                                {entry.scope}:
                              </span>
                            )}
                            {entry.summary}
                          </p>
                          {entry.detail && (
                            <p className="text-[11px] text-slate-500 mt-1.5 leading-relaxed">
                              {entry.detail}
                            </p>
                          )}
                          <p className="text-[10px] text-slate-600 font-mono mt-2">
                            {entry.commit} · {when(entry.at)}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Melden ───────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <p className="text-xs font-black uppercase tracking-widest text-slate-500">
          Fehler oder Vorschlag
        </p>

        <div className="flex gap-2">
          {[
            { id: "bug", label: "Fehler", icon: Bug },
            { id: "idea", label: "Vorschlag", icon: Lightbulb },
          ].map((option) => (
            <button
              key={option.id}
              onClick={() => setKind(option.id)}
              className={cn(
                "px-3.5 py-2 rounded-xl text-[11px] font-black uppercase tracking-wider transition-colors inline-flex items-center gap-2 border",
                kind === option.id
                  ? "border-violet-500/50 text-violet-200 bg-violet-500/10"
                  : "border-slate-800 text-slate-500 hover:text-slate-300"
              )}
            >
              <option.icon className="h-3.5 w-3.5" />
              {option.label}
            </button>
          ))}
        </div>

        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={120}
          placeholder={
            kind === "bug"
              ? "Was geht nicht? In einem Satz."
              : "Was schlägst du vor?"
          }
          className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-violet-500/50 transition-colors"
        />

        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          rows={4}
          maxLength={2000}
          placeholder={
            kind === "bug"
              ? "Was hast du getan, was ist passiert, was hättest du erwartet?"
              : "Wofür wäre das gut?"
          }
          className="w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-violet-500/50 transition-colors resize-y"
        />

        <div className="flex items-center gap-3">
          <span className="text-[11px] text-slate-600">
            {body.length} / 2000
          </span>
          <button
            onClick={submit}
            disabled={sending || title.trim().length < 3}
            className={cn(
              "ml-auto px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-wider transition-all inline-flex items-center gap-2",
              title.trim().length >= 3 && !sending
                ? "bg-violet-500 text-white hover:bg-violet-400"
                : "bg-slate-800 text-slate-600 cursor-not-allowed"
            )}
          >
            {sending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            Abschicken
          </button>
        </div>
      </div>

      {/* ── Meldungen ────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-3")}>
        <div className="flex items-center gap-3 flex-wrap">
          <p className="text-xs font-black uppercase tracking-widest text-slate-500">
            {scope === "all" ? "Alle Meldungen" : "Deine Meldungen"}
          </p>
          {stats?.total > 0 && (
            <span className="text-[11px] text-slate-600">
              {stats.open} offen · {stats.bugs} Fehler · {stats.ideas}{" "}
              Vorschläge
            </span>
          )}
        </div>

        {feedback.length === 0 ? (
          <p className="text-[12px] text-slate-500">
            {scope === "all"
              ? "Noch hat niemand etwas gemeldet."
              : "Du hast noch nichts gemeldet."}
          </p>
        ) : (
          <div className="space-y-2">
            {feedback.map((entry) => {
              const meta = STATES[entry.state] ?? STATES.open;
              return (
                <div
                  key={entry.id}
                  className="rounded-2xl border border-slate-800 bg-[#0d1b31] p-4"
                >
                  <div className="flex items-start gap-2.5 flex-wrap">
                    {entry.kind === "bug" ? (
                      <Bug className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                    ) : (
                      <Lightbulb className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold text-white leading-snug">
                        {entry.title}
                      </p>
                      {entry.body && (
                        <p className="text-[11px] text-slate-500 mt-1.5 leading-relaxed whitespace-pre-wrap">
                          {entry.body}
                        </p>
                      )}
                      <p className="text-[10px] text-slate-600 mt-2 font-mono">
                        #{entry.id} · {when(entry.at)}
                        {scope === "all" && ` · ${entry.user_id}`}
                      </p>
                      {entry.note && (
                        <p className="text-[11px] text-sky-200/70 mt-1.5 leading-relaxed">
                          Antwort: {entry.note}
                        </p>
                      )}
                    </div>

                    <span
                      className={cn(
                        "px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-widest shrink-0",
                        meta.tone
                      )}
                    >
                      {meta.label}
                    </span>
                  </div>

                  {isOwner && (
                    <div className="flex gap-1.5 mt-3 pt-3 border-t border-slate-800/70 flex-wrap">
                      {Object.entries(STATES).map(([key, value]) => (
                        <button
                          key={key}
                          onClick={() => setEntryState(entry.id, key)}
                          disabled={entry.state === key}
                          className={cn(
                            "px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider border transition-colors",
                            entry.state === key
                              ? "border-slate-700 text-slate-600 cursor-default"
                              : "border-slate-800 text-slate-500 hover:text-white hover:border-slate-700"
                          )}
                        >
                          {value.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Wer die Rolle hat (nur Owner) ────────────────── */}
      {isOwner && (
        <div className={cn(CARD, "space-y-3")}>
          <div className="flex items-center gap-2.5">
            <Users className="h-4 w-4 text-slate-500" />
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Wer die Tester-Rolle hat
            </p>
            <span className="ml-auto text-[11px] text-slate-600">
              {members.length}
            </span>
          </div>

          {members.length === 0 ? (
            <p className="text-[12px] text-slate-500">
              Noch niemand. Die Rolle wird unter „Dashboard Users“ vergeben.
            </p>
          ) : (
            <div className="space-y-1.5">
              {members.map((member) => (
                <div
                  key={member.user_id}
                  className="flex items-baseline gap-2.5 text-[11px] py-1"
                >
                  <span className="font-mono text-slate-400">
                    {member.user_id}
                  </span>
                  <span className="text-slate-600">
                    seit {when(member.granted_at)}
                  </span>
                  {member.other_roles?.length > 0 && (
                    <span className="text-slate-600 truncate">
                      · auch {member.other_roles.join(", ")}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="rounded-xl bg-amber-500/[0.05] border border-amber-500/20 p-3 flex gap-2.5">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[11px] text-amber-200/70 leading-relaxed">
              Jeder hier hat Premium ohne Key. Die Rolle unter „Dashboard
              Users“ wegzunehmen entzieht beides sofort — Reiter und
              Premium.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
