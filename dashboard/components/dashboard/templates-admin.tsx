"use client";

/**
 * Vorlagen-Verwaltung im Admin-Panel.
 *
 * ── Wozu ────────────────────────────────────────────────────────────
 *
 * Community-Vorlagen werden von fremden Servern hochgeladen und auf
 * fremden Servern angewendet. Ohne diesen Reiter hätte niemand einen
 * Überblick darüber, was da eigentlich verteilt wird — und keine
 * Handhabe, wenn etwas dabei ist, das nicht verteilt werden sollte.
 *
 * ── Was hier sichtbar ist und sonst nirgends ────────────────────────
 *
 *   * jede Vorlage, auch die privaten,
 *   * der Zugangscode im Klartext,
 *   * woher sie kommt und wer sie hochgeladen hat,
 *   * wer sie wann angewendet hat.
 *
 * Der Bot lässt hierher nur globale Admins durch. Das steht im Proxy,
 * nicht in dieser Datei: eine Prüfung im Browser ist eine Bitte, keine
 * Sperre.
 *
 * ── Sperren statt löschen ───────────────────────────────────────────
 *
 * Eine gesperrte Vorlage bleibt stehen, lässt sich aber nicht mehr
 * anwenden, und ihr Hochlader sieht den Grund. Das ist der mildere und
 * fast immer richtige Eingriff — ein Irrtum ist zurücknehmbar.
 * Gelöscht wird nur, was wirklich weg muss, und auch das erst nach
 * einer Wartezeit.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Ban, Check, ChevronDown, Copy, Eye, Hash, History,
  Key, Loader2, Lock, Search, Server, Shield, Sparkles, Trash2,
  Unlock, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";
const INPUT =
  "w-full bg-[#0a1628] border border-slate-800 rounded-xl px-4 py-3 text-sm " +
  "text-white placeholder:text-slate-600 focus:outline-none " +
  "focus:border-primary/50 transition-colors";

/** Wie lange der Löschen-Knopf hier gesperrt bleibt. */
const DELETE_DELAY_SECONDS = 10;

function stamp(value: any): string {
  const seconds = Number(value || 0);
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function bytes(value: number): string {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-[#0a1628] border border-slate-800 px-4 py-3">
      <p className="text-[9px] font-black uppercase tracking-widest text-slate-600">
        {label}
      </p>
      <p className="text-lg font-black text-white mt-1 tabular-nums">{value}</p>
    </div>
  );
}

export function TemplatesAdmin() {
  const [list, setList] = useState<any[]>([]);
  const [stats, setStats] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("neu");
  const [busy, setBusy] = useState("");

  // Aufgeklappter Eintrag samt nachgeladenem Inhalt.
  const [openId, setOpenId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Record<number, any>>({});
  const [history, setHistory] = useState<Record<number, any[]>>({});

  // Sperren
  const [blockFor, setBlockFor] = useState<number | null>(null);
  const [blockReason, setBlockReason] = useState("");

  // Löschen: erst fragen, dann warten, dann geht der Knopf auf.
  const [deleteFor, setDeleteFor] = useState<number | null>(null);
  const [countdown, setCountdown] = useState(0);

  const load = useCallback(async () => {
    try {
      const answer = await api.templateAdminList(search, sort);
      setList(answer?.templates || []);
      setStats(answer?.stats || {});
    } catch (error: any) {
      toast.error(error?.message || "Die Vorlagen ließen sich nicht laden.");
    } finally {
      setLoading(false);
    }
  }, [search, sort]);

  useEffect(() => {
    // Kurz warten, damit nicht jeder Tastendruck eine Abfrage auslöst.
    const handle = setTimeout(load, 250);
    return () => clearTimeout(handle);
  }, [load]);

  // Der Countdown vor dem Löschen. Er hängt an `deleteFor`, damit ein
  // Wechsel auf eine andere Vorlage die Wartezeit neu startet — sonst
  // hätte man einmal gewartet und könnte danach alles wegklicken.
  useEffect(() => {
    if (deleteFor === null) {
      setCountdown(0);
      return;
    }
    setCountdown(DELETE_DELAY_SECONDS);
    const handle = setInterval(() => {
      setCountdown((old) => {
        if (old <= 1) {
          clearInterval(handle);
          return 0;
        }
        return old - 1;
      });
    }, 1000);
    return () => clearInterval(handle);
  }, [deleteFor]);

  const toggleOpen = async (entry: any) => {
    if (openId === entry.id) {
      setOpenId(null);
      return;
    }
    setOpenId(entry.id);
    if (detail[entry.id]) return;

    setBusy(`open${entry.id}`);
    try {
      const [content, events] = await Promise.all([
        api.templateAdminPayload(entry.id),
        api.templateAdminHistory(entry.id),
      ]);
      setDetail((old) => ({ ...old, [entry.id]: content }));
      setHistory((old) => ({ ...old, [entry.id]: events?.events || [] }));
    } catch (error: any) {
      toast.error(error?.message || "Der Inhalt ließ sich nicht laden.");
    } finally {
      setBusy("");
    }
  };

  const runBlock = async (entry: any, blocked: boolean) => {
    if (blocked && !blockReason.trim()) {
      toast.error("Bitte einen Grund angeben.");
      return;
    }
    setBusy(`block${entry.id}`);
    try {
      await api.templateAdminBlock(entry.id, blocked, blockReason.trim());
      toast.success(blocked ? "Gesperrt." : "Wieder freigegeben.");
      setBlockFor(null);
      setBlockReason("");
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Das ging nicht.");
    } finally {
      setBusy("");
    }
  };

  const runDelete = async (entry: any) => {
    setBusy(`del${entry.id}`);
    try {
      await api.templateAdminDelete(entry.id);
      toast.success("Endgültig gelöscht.");
      setDeleteFor(null);
      setOpenId(null);
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Das ging nicht.");
    } finally {
      setBusy("");
    }
  };

  const copy = (text: string) => {
    navigator.clipboard?.writeText(text);
    toast.success("Kopiert.");
  };

  const blockedCount = useMemo(
    () => list.filter((entry) => entry.blocked).length,
    [list]
  );

  if (loading) {
    return (
      <div className={cn(CARD, "flex items-center justify-center py-16")}>
        <Loader2 className="h-6 w-6 text-primary animate-spin opacity-50" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Kopf */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
            <Sparkles className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <h3 className="font-bold text-white">Community-Vorlagen</h3>
            <p className="text-[12px] text-slate-500 mt-0.5">
              Alles, was hochgeladen wurde &mdash; mit Zugangscode, Herkunft und
              Verlauf.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <Stat label="Vorlagen" value={stats.total ?? 0} />
          <Stat label="Mit Code" value={stats.with_key ?? 0} />
          <Stat label="Gesperrt" value={blockedCount} />
          <Stat label="Anwendungen" value={stats.applies ?? 0} />
          <Stat label="Aufrufe" value={stats.uses ?? 0} />
        </div>

        <div className="flex gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="h-4 w-4 text-slate-600 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Name, Beschreibung, Hochlader oder Server-ID …"
              className={cn(INPUT, "pl-11")}
            />
          </div>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value)}
            className={cn(INPUT, "w-auto")}
          >
            <option value="neu">Neueste</option>
            <option value="beliebt">Meistgenutzt</option>
            <option value="name">Name</option>
          </select>
        </div>
      </div>

      {list.length === 0 ? (
        <div className={cn(CARD, "py-12 text-center")}>
          <p className="text-[13px] text-slate-600">
            {search
              ? `Nichts gefunden für „${search}“.`
              : "Es wurde noch keine Vorlage hochgeladen."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {list.map((entry: any) => {
            const open = openId === entry.id;
            const content = detail[entry.id];
            const events = history[entry.id] || [];

            return (
              <div
                key={entry.id}
                className={cn(
                  "rounded-3xl border transition-colors",
                  entry.blocked
                    ? "bg-red-500/[0.05] border-red-500/30"
                    : "bg-[#10233f] border-slate-800"
                )}
              >
                {/* Kopfzeile */}
                <div className="p-4 sm:p-5 flex items-start gap-3 flex-wrap">
                  <button
                    onClick={() => toggleOpen(entry)}
                    className="min-w-0 flex-1 text-left group"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <ChevronDown
                        className={cn(
                          "h-4 w-4 text-slate-600 transition-transform shrink-0",
                          open && "rotate-180"
                        )}
                      />
                      <p className="text-[14px] font-bold text-white group-hover:text-primary transition-colors">
                        {entry.name}
                      </p>
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                        #{entry.id}
                      </span>
                      {entry.visibility === "key" && (
                        <span className="flex items-center gap-1 text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-amber-400/10 text-amber-400 border border-amber-400/20">
                          <Lock className="h-2.5 w-2.5" />
                          Code
                        </span>
                      )}
                      {entry.visibility === "private" && (
                        <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-slate-500/10 text-slate-400 border border-slate-500/20">
                          Privat
                        </span>
                      )}
                      {entry.blocked && (
                        <span className="flex items-center gap-1 text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-red-500/15 text-red-300 border border-red-500/30">
                          <Ban className="h-2.5 w-2.5" />
                          Gesperrt
                        </span>
                      )}
                    </div>

                    {entry.description && (
                      <p className="text-[12px] text-slate-500 mt-1.5 line-clamp-2 leading-relaxed pl-6">
                        {entry.description}
                      </p>
                    )}

                    <div className="flex items-center gap-3 mt-2 pl-6 text-[11px] text-slate-600 flex-wrap">
                      <span className="flex items-center gap-1">
                        <Hash className="h-3 w-3" />
                        {entry.summary?.channels ?? 0}
                      </span>
                      <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        {entry.summary?.roles ?? 0}
                      </span>
                      <span className="flex items-center gap-1">
                        <Shield className="h-3 w-3" />
                        {entry.summary?.features ?? 0}
                      </span>
                      <span>{bytes(entry.size_bytes || 0)}</span>
                      <span>{entry.uses ?? 0}&times; verwendet</span>
                      <span>{stamp(entry.created_at)}</span>
                    </div>
                  </button>

                  <div className="flex items-center gap-1.5">
                    {entry.blocked ? (
                      <button
                        disabled={busy === `block${entry.id}`}
                        onClick={() => runBlock(entry, false)}
                        title="Wieder freigeben"
                        className="p-2.5 rounded-xl text-slate-600 hover:text-emerald-400 hover:bg-emerald-500/10 transition-all disabled:opacity-40"
                      >
                        <Unlock className="h-4 w-4" />
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setBlockFor(blockFor === entry.id ? null : entry.id);
                          setBlockReason("");
                        }}
                        title="Sperren"
                        className="p-2.5 rounded-xl text-slate-600 hover:text-amber-400 hover:bg-amber-500/10 transition-all"
                      >
                        <Ban className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      onClick={() =>
                        setDeleteFor(deleteFor === entry.id ? null : entry.id)
                      }
                      title="Endgültig löschen"
                      className="p-2.5 rounded-xl text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-all"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Grund der Sperre */}
                {entry.blocked && entry.blocked_reason && (
                  <div className="px-4 sm:px-5 pb-4">
                    <div className="rounded-2xl bg-red-500/[0.07] border border-red-500/25 p-3.5 flex gap-2.5">
                      <Ban className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                      <p className="text-[12.5px] text-red-200/85 leading-relaxed">
                        {entry.blocked_reason}
                        {entry.blocked_by && (
                          <span className="text-red-200/50">
                            {" "}
                            &mdash; von {entry.blocked_by}
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                )}

                {/* Sperren: Grund eingeben */}
                {blockFor === entry.id && (
                  <div className="px-4 sm:px-5 pb-4 space-y-3">
                    <div className="rounded-2xl bg-amber-500/[0.06] border border-amber-500/25 p-4 space-y-3">
                      <p className="text-[12.5px] text-amber-200/85 leading-relaxed">
                        Die Vorlage bleibt sichtbar, lässt sich aber nicht mehr
                        anwenden. Der Grund wird ihrem Hochlader angezeigt
                        &mdash; ohne ihn sieht er nur, dass etwas nicht mehr
                        geht, und meldet es als Fehler.
                      </p>
                      <input
                        value={blockReason}
                        onChange={(event) => setBlockReason(event.target.value)}
                        placeholder="Grund, z. B. »Rollennamen verstoßen gegen die Regeln«"
                        maxLength={500}
                        className={cn(
                          INPUT,
                          "border-amber-500/30 focus:border-amber-500/60"
                        )}
                      />
                      <div className="flex gap-2 flex-wrap">
                        <button
                          disabled={
                            !blockReason.trim() || busy === `block${entry.id}`
                          }
                          onClick={() => runBlock(entry, true)}
                          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-300 text-xs font-black uppercase tracking-widest hover:bg-amber-500/25 disabled:opacity-40 transition-all"
                        >
                          {busy === `block${entry.id}` ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Ban className="h-3.5 w-3.5" />
                          )}
                          Sperren
                        </button>
                        <button
                          onClick={() => setBlockFor(null)}
                          className="px-4 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-slate-400 text-xs font-black uppercase tracking-widest hover:text-white transition-all"
                        >
                          Abbrechen
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Löschen: rot, mit Wartezeit */}
                {deleteFor === entry.id && (
                  <div className="px-4 sm:px-5 pb-4">
                    <div className="rounded-2xl bg-red-500/[0.08] border border-red-500/40 p-4 space-y-3">
                      <div className="flex gap-2.5">
                        <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                        <p className="text-[12.5px] text-red-200/90 leading-relaxed">
                          <b>Bist du sicher?</b> Die Vorlage wird endgültig
                          gelöscht, samt ihrem Verlauf. Der Hochlader erfährt
                          nichts davon und kann sie nicht wiederherstellen. In
                          fast allen Fällen ist <b>Sperren</b> die bessere Wahl
                          &mdash; das lässt sich zurücknehmen.
                        </p>
                      </div>
                      <div className="flex gap-2 flex-wrap">
                        <button
                          disabled={countdown > 0 || busy === `del${entry.id}`}
                          onClick={() => runDelete(entry)}
                          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/15 border border-red-500/45 text-red-300 text-xs font-black uppercase tracking-widest hover:bg-red-500/25 disabled:opacity-40 transition-all"
                        >
                          {busy === `del${entry.id}` ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                          {countdown > 0
                            ? `Bitte warten … ${countdown}s`
                            : "Ja, endgültig löschen"}
                        </button>
                        <button
                          onClick={() => setDeleteFor(null)}
                          className="px-4 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-slate-400 text-xs font-black uppercase tracking-widest hover:text-white transition-all"
                        >
                          Nein, abbrechen
                        </button>
                      </div>
                      {countdown > 0 && (
                        <p className="text-[11px] text-red-200/60">
                          Der Knopf ist {DELETE_DELAY_SECONDS} Sekunden gesperrt
                          &mdash; Zeit, noch einmal zu lesen, was oben steht.
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Aufgeklappt */}
                {open && (
                  <div className="px-4 sm:px-5 pb-5 space-y-4 border-t border-slate-800 pt-4">
                    {/* Herkunft und Code */}
                    <div className="grid sm:grid-cols-2 gap-3">
                      <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-2">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 flex items-center gap-1.5">
                          <Server className="h-3 w-3" />
                          Herkunft
                        </p>
                        <p className="text-[12.5px] text-slate-300">
                          {entry.source_guild_name || "Unbekannter Server"}
                        </p>
                        <button
                          onClick={() => copy(entry.source_guild_id)}
                          className="text-[11px] font-mono text-slate-600 hover:text-slate-400 transition-colors flex items-center gap-1.5"
                        >
                          {entry.source_guild_id}
                          <Copy className="h-3 w-3" />
                        </button>
                        <p className="text-[11px] text-slate-600">
                          Hochgeladen von{" "}
                          {entry.author_name || "unbekannt"}
                          {entry.author_id ? ` (${entry.author_id})` : ""}
                        </p>
                        <p className="text-[11px] text-slate-600">
                          Bot ist dort{" "}
                          {entry.bot_present ? "noch drauf" : "nicht mehr"}.
                        </p>
                      </div>

                      <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-2">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 flex items-center gap-1.5">
                          <Key className="h-3 w-3" />
                          Zugangscode
                        </p>
                        {!entry.has_key ? (
                          <p className="text-[12.5px] text-slate-500">
                            Diese Vorlage ist offen &mdash; sie hat keinen Code.
                          </p>
                        ) : entry.key ? (
                          <div className="flex items-center gap-2 flex-wrap">
                            <code className="px-3 py-2 rounded-xl bg-[#10233f] border border-amber-500/25 text-[15px] font-black tracking-[0.25em] text-amber-300">
                              {entry.key}
                            </code>
                            <button
                              onClick={() => copy(entry.key)}
                              className="p-2 rounded-xl text-slate-600 hover:text-white hover:bg-white/[0.06] transition-all"
                              title="Kopieren"
                            >
                              <Copy className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ) : (
                          <p className="text-[12px] text-slate-500 leading-relaxed">
                            Nicht mehr anzeigbar. Die Vorlage stammt aus der
                            Zeit, als nur die Prüfsumme gespeichert wurde
                            &mdash; sie funktioniert weiter, nur nachschlagen
                            geht nicht.
                          </p>
                        )}
                        <p className="text-[11px] text-slate-600">
                          Zuletzt angewendet: {stamp(entry.last_used)}
                        </p>
                      </div>
                    </div>

                    {/* Inhalt */}
                    {busy === `open${entry.id}` ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-5 w-5 text-primary animate-spin opacity-50" />
                      </div>
                    ) : (
                      content && (
                        <>
                          <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-3 max-h-72 overflow-y-auto">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 flex items-center gap-1.5">
                              <Eye className="h-3 w-3" />
                              Was drin steht
                            </p>

                            {(content.roles || []).length > 0 && (
                              <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2">
                                  Rollen
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                  {content.roles.map(
                                    (role: any, index: number) => (
                                      <span
                                        key={`${role.name}-${index}`}
                                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] text-slate-300"
                                      >
                                        <span
                                          className="h-2 w-2 rounded-full shrink-0"
                                          style={{
                                            background: role.colour || "#99aab5",
                                          }}
                                        />
                                        {role.name}
                                      </span>
                                    )
                                  )}
                                </div>
                              </div>
                            )}

                            {(content.channels || []).length > 0 && (
                              <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2 mt-3">
                                  Kanäle
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                  {content.channels
                                    .slice(0, 80)
                                    .map((channel: any, index: number) => (
                                      <span
                                        key={`${channel.category}-${channel.name}-${index}`}
                                        className="px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] text-slate-400"
                                      >
                                        {channel.kind === "voice" ? "🔊" : "#"}{" "}
                                        {channel.name}
                                      </span>
                                    ))}
                                  {content.channels.length > 80 && (
                                    <span className="px-2.5 py-1 text-[11px] text-slate-600">
                                      … und {content.channels.length - 80}{" "}
                                      weitere
                                    </span>
                                  )}
                                </div>
                              </div>
                            )}

                            {(content.features || []).length > 0 && (
                              <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2 mt-3">
                                  Dashboard-Einstellungen
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                  {content.features.map((feature: any) => (
                                    <span
                                      key={feature.key}
                                      className="px-2.5 py-1 rounded-lg bg-primary/10 border border-primary/25 text-[11px] text-primary"
                                    >
                                      {feature.label} ({feature.entries})
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Verlauf */}
                          <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-2 max-h-56 overflow-y-auto">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 flex items-center gap-1.5">
                              <History className="h-3 w-3" />
                              Wer hat sie angewendet
                            </p>
                            {events.length === 0 ? (
                              <p className="text-[12px] text-slate-600">
                                Noch niemand.
                              </p>
                            ) : (
                              events.map((event: any, index: number) => (
                                <div
                                  key={index}
                                  className="flex items-center gap-2 text-[11.5px] text-slate-500 flex-wrap"
                                >
                                  <span className="font-mono text-slate-400">
                                    {event.guild_id}
                                  </span>
                                  <span>{stamp(event.created_at)}</span>
                                  {event.wiped && (
                                    <span className="text-red-400/80 font-bold">
                                      Server vorher geleert
                                    </span>
                                  )}
                                </div>
                              ))
                            )}
                          </div>
                        </>
                      )
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className={cn(CARD, "flex gap-3")}>
        <Check className="h-4 w-4 text-slate-600 shrink-0 mt-0.5" />
        <p className="text-[12px] text-slate-500 leading-relaxed">
          Sperren ist fast immer die richtige Wahl: die Vorlage bleibt stehen,
          ihr Hochlader sieht den Grund, und ein Irrtum lässt sich zurücknehmen.
          Löschen ist endgültig und wird nirgends angekündigt.
        </p>
      </div>
    </div>
  );
}
