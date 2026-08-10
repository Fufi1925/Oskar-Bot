"use client";

/**
 * Nutzer nachschlagen und Massnahmen ergreifen.
 *
 * Eine ID eingeben, und man sieht das Profil und **jeden** Server, auf
 * dem die Person ist -- auch die, auf die man selbst keinen Zugriff
 * hat. Genau das konnte das Dashboard vorher nicht: die bestehende
 * Nutzeransicht listet nur Server, in denen die Person selbst Rechte
 * hat.
 *
 * Drei Massnahmen, absichtlich unterschiedlich schwer auszuloesen:
 *
 *   * **Vom Bot sperren** -- ein Klick mit Grund. Umkehrbar.
 *   * **Inhaber warnen** -- ein Klick mit Grund. Verschickt nur DMs.
 *   * **Auf allen Servern bannen** -- 10 Sekunden Wartezeit, dazu muss
 *     der Name der Person abgetippt werden. Nicht umkehrbar.
 *
 * Vor dem Bann wird eine Probe gefahren (`dry_run`), damit im Dialog
 * die echte Zahl steht und nicht eine geschaetzte.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle, Ban, Crown, Loader2, Search, Shield, ShieldOff,
  Trash2, Users, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const BAN_DELAY_SECONDS = 10;

const GRUENDE = [
  "Nuke-Versuch",
  "Raid / Massenspam",
  "Werbung per DM",
  "Betrug",
  "Belästigung",
  "Umgehung einer Sperre",
];

interface GuildEntry {
  guild_id: string;
  guild_name: string;
  guild_icon: string | null;
  member_count: number;
  is_owner: boolean;
  is_admin: boolean;
  top_role: string | null;
  joined_at: number;
  roles: string[];
  bot_can_ban: boolean;
}

interface Lookup {
  user_id: string;
  found: boolean;
  username: string | null;
  display_name: string | null;
  avatar: string | null;
  is_bot: boolean;
  created_at: number;
  guilds: GuildEntry[];
  guild_count: number;
  bannable_count: number;
  owner_of_count: number;
  admin_of_count: number;
  bot_ban: { reason: string; banned_at: number; banned_by: string } | null;
  history: Array<{
    id: number; kind: string; reason: string; ok_count: number;
    fail_count: number; created_at: number;
  }>;
}

function datum(unix: number) {
  if (!unix) return "unbekannt";
  return new Date(unix * 1000).toLocaleDateString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-3.5 text-center">
      <div className={cn("text-2xl font-black", tone || "text-white")}>{value}</div>
      <div className="text-[10px] text-slate-500 mt-1 font-bold uppercase tracking-wider">
        {label}
      </div>
    </div>
  );
}

export function UserLookupPanel() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Lookup | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [reason, setReason] = useState("");
  const [banDialog, setBanDialog] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [countdown, setCountdown] = useState(0);
  const [probe, setProbe] = useState<{ ok: number; skipped: number } | null>(null);

  const [bans, setBans] = useState<any[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadBans = useCallback(async () => {
    try {
      const res = await api.getBotBans();
      setBans(res.bans || []);
    } catch {
      // Die Sperrliste ist Beiwerk; ein Fehler hier darf die Suche nicht stören.
    }
  }, []);

  useEffect(() => {
    loadBans();
  }, [loadBans]);

  // Der Countdown im Bann-Dialog.
  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (!banDialog) {
      setCountdown(0);
      return;
    }
    setCountdown(BAN_DELAY_SECONDS);
    timer.current = setInterval(() => {
      setCountdown((alt) => {
        if (alt <= 1) {
          if (timer.current) clearInterval(timer.current);
          return 0;
        }
        return alt - 1;
      });
    }, 1000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [banDialog]);

  const suchen = async (id?: string) => {
    const ziel = (id ?? query).trim();
    if (!/^\d{15,20}$/.test(ziel)) {
      return toast.error("Bitte eine gültige Discord-ID eingeben (15–20 Ziffern).");
    }
    setLoading(true);
    setData(null);
    try {
      const res = await api.lookupUser(ziel);
      setData(res);
      if (!res.found) {
        toast.warning("Discord kennt diese ID nicht — sperren geht trotzdem.");
      }
    } catch (err: any) {
      toast.error(err?.message || "Nachschlagen fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const sperren = async () => {
    if (!data) return;
    if (!reason.trim()) return toast.error("Bitte einen Grund angeben.");
    setBusy("ban");
    try {
      await api.addBotBan({ user_id: data.user_id, reason: reason.trim() });
      toast.success("Die Person kann den Bot nicht mehr benutzen.");
      await suchen(data.user_id);
      await loadBans();
    } catch (err: any) {
      toast.error(err?.message || "Sperren fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  const entsperren = async (userId: string) => {
    setBusy(`unban${userId}`);
    try {
      await api.removeBotBan(userId);
      toast.success("Sperre aufgehoben.");
      if (data?.user_id === userId) await suchen(userId);
      await loadBans();
    } catch (err: any) {
      toast.error(err?.message || "Aufheben fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  const warnen = async () => {
    if (!data) return;
    if (!reason.trim()) return toast.error("Bitte einen Grund angeben.");
    setBusy("warn");
    try {
      const res = await api.userMassAction({
        user_id: data.user_id, kind: "warn_owners", reason: reason.trim(),
      });
      toast.success(
        `${res.ok_count} Inhaber benachrichtigt` +
        (res.fail_count ? `, ${res.fail_count} nicht erreichbar.` : "."),
      );
      await suchen(data.user_id);
    } catch (err: any) {
      toast.error(err?.message || "Warnen fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  /** Probe fahren, dann den Dialog öffnen — mit echter Zahl. */
  const bannDialogOeffnen = async () => {
    if (!data) return;
    if (!reason.trim()) return toast.error("Bitte zuerst einen Grund angeben.");
    setBusy("probe");
    try {
      const res = await api.userMassAction({
        user_id: data.user_id, kind: "ban_all", reason: reason.trim(), dry_run: true,
      });
      setProbe({ ok: res.ok_count, skipped: res.skipped_count });
      setConfirmText("");
      setBanDialog(true);
    } catch (err: any) {
      toast.error(err?.message || "Probe fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  const ueberallBannen = async () => {
    if (!data) return;
    setBusy("banall");
    try {
      const res = await api.userMassAction({
        user_id: data.user_id, kind: "ban_all", reason: reason.trim(),
      });
      toast.success(
        `Auf ${res.ok_count} Servern gebannt` +
        (res.fail_count ? `, ${res.fail_count} fehlgeschlagen.` : "."),
      );
      setBanDialog(false);
      await suchen(data.user_id);
    } catch (err: any) {
      toast.error(err?.message || "Bann fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  const erwarteterText = data?.username || data?.user_id || "";
  const darfBannen =
    countdown === 0 && confirmText.trim() === erwarteterText && busy !== "banall";

  return (
    <div className="space-y-5">
      {/* ── Suche ─────────────────────────────────────────────── */}
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card">
        <div>
          <h3 className="font-bold text-white">Nutzer nachschlagen</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Discord-ID eingeben. Du siehst das Profil und jeden Server, auf dem
            die Person ist — auch die, auf die du sonst keinen Zugriff hast.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-2.5">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && suchen()}
            placeholder="z. B. 1303627964734246944"
            inputMode="numeric"
            className="flex-1 bg-slate-900/60 border border-slate-700 rounded-2xl px-4 py-3 text-sm text-white outline-none focus:border-blue-500 font-mono"
          />
          <button
            onClick={() => suchen()}
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-2xl bg-blue-500/15 border border-blue-500/30 text-blue-200 font-bold text-sm hover:bg-blue-500/25 transition-colors disabled:opacity-40"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            Suchen
          </button>
        </div>
      </div>

      {/* ── Ergebnis ──────────────────────────────────────────── */}
      {data && (
        <>
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
            <div className="flex items-start gap-4 flex-wrap">
              {data.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={data.avatar}
                  alt=""
                  className="h-16 w-16 rounded-2xl border border-slate-700"
                />
              ) : (
                <div className="h-16 w-16 rounded-2xl bg-slate-800 grid place-items-center">
                  <Users className="h-7 w-7 text-slate-600" />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-bold text-white text-lg">
                    {data.username || "Unbekanntes Konto"}
                  </h3>
                  {data.is_bot && (
                    <span className="text-[10px] font-black px-2 py-0.5 rounded-md bg-blue-500/20 text-blue-300">
                      BOT
                    </span>
                  )}
                  {data.bot_ban && (
                    <span className="text-[10px] font-black px-2 py-0.5 rounded-md bg-red-500/20 text-red-300">
                      GESPERRT
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 font-mono mt-1">{data.user_id}</p>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Konto erstellt: {datum(data.created_at)}
                </p>
              </div>
            </div>

            {data.bot_ban && (
              <div className="bg-red-500/8 border border-red-500/25 rounded-2xl p-4 flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-red-300">
                    Diese Person ist vom Bot gesperrt
                  </p>
                  <p className="text-xs text-slate-400 mt-1">
                    {data.bot_ban.reason || "Kein Grund angegeben."}
                  </p>
                  <p className="text-[11px] text-slate-600 mt-1">
                    seit {datum(data.bot_ban.banned_at)}
                  </p>
                </div>
                <button
                  onClick={() => entsperren(data.user_id)}
                  disabled={busy === `unban${data.user_id}`}
                  className="shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-slate-300 text-xs font-bold hover:text-white transition-colors disabled:opacity-40"
                >
                  <ShieldOff className="h-3.5 w-3.5" />
                  Aufheben
                </button>
              </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Stat label="Server gesamt" value={data.guild_count} />
              <Stat label="Bot kann bannen" value={data.bannable_count} tone="text-amber-300" />
              <Stat label="Ist Inhaber" value={data.owner_of_count} tone="text-purple-300" />
              <Stat label="Ist Admin" value={data.admin_of_count} tone="text-blue-300" />
            </div>
          </div>

          {/* ── Maßnahmen ───────────────────────────────────── */}
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card">
            <div>
              <h3 className="font-bold text-white">Maßnahmen</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Der Grund steht später im Protokoll und bei einem Bann auch im
                Discord-Auditlog jedes Servers.
              </p>
            </div>

            <div>
              <label className="text-[11px] font-black uppercase tracking-wider text-slate-400">
                Grund
              </label>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Was ist vorgefallen?"
                maxLength={450}
                className="mt-1.5 w-full bg-slate-900/60 border border-slate-700 rounded-2xl px-4 py-3 text-sm text-white outline-none focus:border-blue-500"
              />
              <div className="flex gap-1.5 flex-wrap mt-2">
                {GRUENDE.map((g) => (
                  <button
                    key={g}
                    onClick={() => setReason(g)}
                    className="text-[11px] px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-colors"
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid sm:grid-cols-3 gap-3">
              <button
                onClick={sperren}
                disabled={!!busy || !!data.bot_ban}
                className="flex flex-col items-start gap-1.5 p-4 rounded-2xl bg-slate-900/40 border border-slate-700 hover:border-slate-500 transition-colors text-left disabled:opacity-40"
              >
                <Shield className="h-4 w-4 text-slate-300" />
                <span className="text-sm font-bold text-white">Vom Bot sperren</span>
                <span className="text-[11px] text-slate-500 leading-snug">
                  Keine Befehle, kein Dashboard, kann den Bot nicht einladen.
                  Umkehrbar.
                </span>
              </button>

              <button
                onClick={warnen}
                disabled={!!busy || data.guild_count === 0}
                className="flex flex-col items-start gap-1.5 p-4 rounded-2xl bg-amber-500/8 border border-amber-500/25 hover:border-amber-500/50 transition-colors text-left disabled:opacity-40"
              >
                {busy === "warn"
                  ? <Loader2 className="h-4 w-4 animate-spin text-amber-300" />
                  : <AlertTriangle className="h-4 w-4 text-amber-300" />}
                <span className="text-sm font-bold text-amber-200">Inhaber warnen</span>
                <span className="text-[11px] text-slate-500 leading-snug">
                  DM an jeden Server-Inhaber. Es wird niemand gebannt.
                </span>
              </button>

              <button
                onClick={bannDialogOeffnen}
                disabled={!!busy || data.bannable_count === 0}
                className="flex flex-col items-start gap-1.5 p-4 rounded-2xl bg-red-500/8 border border-red-500/25 hover:border-red-500/50 transition-colors text-left disabled:opacity-40"
              >
                {busy === "probe"
                  ? <Loader2 className="h-4 w-4 animate-spin text-red-300" />
                  : <Ban className="h-4 w-4 text-red-300" />}
                <span className="text-sm font-bold text-red-200">
                  Auf allen Servern bannen
                </span>
                <span className="text-[11px] text-slate-500 leading-snug">
                  {data.bannable_count} von {data.guild_count} Servern.
                  Nicht umkehrbar.
                </span>
              </button>
            </div>
          </div>

          {/* ── Die Server ──────────────────────────────────── */}
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-3 border-glow-card">
            <h3 className="font-bold text-white">
              Server ({data.guild_count})
            </h3>
            {data.guild_count === 0 ? (
              <p className="text-sm text-slate-500 py-4 text-center">
                Der Bot teilt keinen Server mit dieser Person.
              </p>
            ) : (
              <div className="space-y-2 max-h-[460px] overflow-y-auto pr-1">
                {data.guilds.map((g) => (
                  <div
                    key={g.guild_id}
                    className="flex items-center gap-3 p-3 rounded-2xl bg-white/[0.02] border border-white/5"
                  >
                    {g.guild_icon ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={g.guild_icon} alt="" className="h-9 w-9 rounded-xl shrink-0" />
                    ) : (
                      <div className="h-9 w-9 rounded-xl bg-slate-800 grid place-items-center shrink-0 text-[10px] font-black text-slate-500">
                        {g.guild_name.slice(0, 2).toUpperCase()}
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-sm font-bold text-white truncate">
                          {g.guild_name}
                        </span>
                        {g.is_owner && (
                          <Crown className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                        )}
                        {g.is_admin && !g.is_owner && (
                          <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300">
                            ADMIN
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {g.member_count.toLocaleString("de-DE")} Mitglieder
                        {g.top_role ? ` · ${g.top_role}` : ""}
                        {g.joined_at ? ` · seit ${datum(g.joined_at)}` : ""}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "text-[10px] font-black px-2 py-1 rounded-lg shrink-0",
                        g.bot_can_ban
                          ? "bg-red-500/15 text-red-300"
                          : "bg-slate-700/40 text-slate-500",
                      )}
                      title={
                        g.bot_can_ban
                          ? "Der Bot kann hier bannen."
                          : "Der Bot kann hier nicht bannen — fehlende Rechte, zu niedrige Rolle oder die Person ist Inhaber."
                      }
                    >
                      {g.bot_can_ban ? "bannbar" : "nicht bannbar"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Verlauf ─────────────────────────────────────── */}
          {data.history.length > 0 && (
            <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-2">
              <h3 className="font-bold text-white text-sm">Bisherige Maßnahmen</h3>
              {data.history.map((h) => (
                <div key={h.id} className="text-[12px] text-slate-400 flex gap-2 flex-wrap">
                  <span className="text-slate-600">{datum(h.created_at)}</span>
                  <span className="font-bold text-slate-300">
                    {h.kind === "ban_all" ? "Bann auf allen Servern" : "Inhaber gewarnt"}
                  </span>
                  <span>· {h.ok_count} erfolgreich, {h.fail_count} nicht</span>
                  {h.reason && <span className="text-slate-600">· {h.reason}</span>}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Sperrliste ────────────────────────────────────────── */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-3">
        <h3 className="font-bold text-white text-sm">
          Vom Bot gesperrt ({bans.length})
        </h3>
        {bans.length === 0 ? (
          <p className="text-[12px] text-slate-500">Niemand ist gesperrt.</p>
        ) : (
          <div className="space-y-2">
            {bans.map((b) => (
              <div
                key={b.user_id}
                className="flex items-center gap-3 p-3 rounded-2xl bg-white/[0.02] border border-white/5"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white font-bold truncate">
                    {b.username || b.user_id}
                  </p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {b.reason || "Kein Grund angegeben."} · {datum(b.banned_at)}
                  </p>
                </div>
                <button
                  onClick={() => suchen(b.user_id)}
                  className="text-[11px] px-2.5 py-1.5 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-colors shrink-0"
                >
                  Ansehen
                </button>
                <button
                  onClick={() => entsperren(b.user_id)}
                  disabled={busy === `unban${b.user_id}`}
                  className="text-slate-600 hover:text-red-400 transition-colors shrink-0 disabled:opacity-40"
                  aria-label="Sperre aufheben"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Bestätigung für den Massenbann ────────────────────── */}
      {banDialog && data && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4">
          <div className="w-full max-w-lg bg-[#0d1b30] border border-red-500/30 rounded-3xl p-6 space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex gap-3">
                <div className="h-10 w-10 rounded-2xl bg-red-500/15 border border-red-500/30 grid place-items-center shrink-0">
                  <Ban className="h-5 w-5 text-red-300" />
                </div>
                <div>
                  <h3 className="font-bold text-white">Auf allen Servern bannen</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Das lässt sich nicht rückgängig machen.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setBanDialog(false)}
                className="text-slate-600 hover:text-white transition-colors"
                aria-label="Abbrechen"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="bg-red-500/8 border border-red-500/20 rounded-2xl p-4 space-y-2">
              <p className="text-sm text-slate-300">
                <b className="text-white">{data.username || data.user_id}</b> wird auf{" "}
                <b className="text-red-300">{probe?.ok ?? data.bannable_count} Servern</b> gebannt.
              </p>
              {!!probe?.skipped && (
                <p className="text-[11px] text-slate-500">
                  {probe.skipped} Server werden übersprungen — dort ist die Person
                  Inhaber oder dem Bot fehlen die Rechte.
                </p>
              )}
              <p className="text-[11px] text-slate-500">Grund: {reason}</p>
            </div>

            <div>
              <label className="text-[11px] font-black uppercase tracking-wider text-slate-400">
                Zum Bestätigen abtippen: <span className="text-white font-mono">{erwarteterText}</span>
              </label>
              <input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={erwarteterText}
                className="mt-1.5 w-full bg-slate-900/60 border border-slate-700 rounded-2xl px-4 py-3 text-sm text-white outline-none focus:border-red-500 font-mono"
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setBanDialog(false)}
                className="flex-1 px-4 py-3 rounded-2xl bg-white/5 border border-white/10 text-slate-300 font-bold text-sm hover:text-white transition-colors"
              >
                Abbrechen
              </button>
              <button
                onClick={ueberallBannen}
                disabled={!darfBannen}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-3 rounded-2xl bg-red-500/20 border border-red-500/40 text-red-200 font-bold text-sm hover:bg-red-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {busy === "banall" && <Loader2 className="h-4 w-4 animate-spin" />}
                {countdown > 0 ? `Bitte warten … ${countdown}s` : "Jetzt überall bannen"}
              </button>
            </div>

            {countdown > 0 && (
              <p className="text-[11px] text-slate-600 text-center">
                Die Wartezeit ist Absicht — lies noch einmal, was hier steht.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
