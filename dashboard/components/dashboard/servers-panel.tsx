"use client";

/**
 * Every server the bot is in, from above.
 *
 * The per-guild pages configure one server; this is the fleet view: copy an
 * invite, see who owns it, spot the servers where the bot is missing
 * permissions, hand yourself a role, or make the bot leave.
 */

import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowUpRight, Ban, CheckCircle2, Copy, Crown, Diamond, DoorOpen,
  ChevronDown, ExternalLink, Loader2, Link2, RefreshCw, Search, Shield, ShieldAlert, Sparkles,
  Trash2, UserPlus, Users, X, Zap,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Select } from "@/components/ui/select";

interface ServerRow {
  id: string;
  name: string;
  icon_url: string | null;
  description: string;
  owner_id: string;
  owner_name: string | null;
  owner_avatar: string | null;
  member_count: number;
  bot_count: number;
  human_count: number;
  bot_ratio: number;
  channel_count: number;
  role_count: number;
  boost_level: number;
  boost_count: number;
  created_at: number;
  joined_at: number;
  vanity_url: string;
  premium: boolean;
  blacklisted: boolean;
  permissions: { known: boolean; administrator: boolean; missing: string[]; highest_role_name?: string };
}

const SORTS = [
  { value: "members", label: "Meiste Mitglieder" },
  { value: "name", label: "Name A–Z" },
  { value: "joined", label: "Zuletzt beigetreten" },
  { value: "created", label: "Neueste Server" },
  { value: "bots", label: "Höchster Bot-Anteil" },
  { value: "boosts", label: "Meiste Boosts" },
];

function formatDate(timestamp: number): string {
  if (!timestamp) return "unbekannt";
  return new Date(timestamp * 1000).toLocaleDateString();
}

export function ServersPanel({ currentUserId }: { currentUserId?: string }) {
  const [servers, setServers] = useState<ServerRow[]>([]);
  const [totals, setTotals] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("members");
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [invites, setInvites] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<string | null>(null);

  // Leave dialog
  const [leaveTarget, setLeaveTarget] = useState<ServerRow | null>(null);
  const [leaveConfirm, setLeaveConfirm] = useState("");
  const [leaveReason, setLeaveReason] = useState("");
  const [leaveMessage, setLeaveMessage] = useState("");
  const [leaveBlacklist, setLeaveBlacklist] = useState(false);

  // Role dialog
  const [roleTarget, setRoleTarget] = useState<ServerRow | null>(null);
  const [roleList, setRoleList] = useState<any[]>([]);
  const [roleUserId, setRoleUserId] = useState("");
  const [roleId, setRoleId] = useState("");
  const [roleMode, setRoleMode] = useState<"existing" | "new">("existing");
  const [newRoleName, setNewRoleName] = useState("");
  const [newRoleAdmin, setNewRoleAdmin] = useState(false);

  /**
   * Close the "leave server" dialog, but not over a typed-out reason.
   *
   * Cancel and the X threw away the reason and the goodbye message
   * without a word -- and left them filled in, so opening the dialog
   * for a different server showed the previous server's text as though
   * it belonged there. Both are fixed here: ask, then clear.
   *
   * A modal has nowhere to put a sticky bar and no page left to scroll
   * one into view, so a confirm() is the right tool in this one spot.
   */
  const closeLeaveDialog = () => {
    const typed = leaveReason.trim() || leaveMessage.trim() || leaveConfirm.trim();
    if (typed && !confirm("Die Eingaben für diesen Server verwerfen?")) return;
    setLeaveTarget(null);
    setLeaveConfirm("");
    setLeaveReason("");
    setLeaveMessage("");
    setLeaveBlacklist(false);
  };

  /** Same for the role dialog. */
  const closeRoleDialog = () => {
    if (newRoleName.trim() && !confirm("Den eingetippten Rollennamen verwerfen?")) {
      return;
    }
    setRoleTarget(null);
    setNewRoleName("");
    setNewRoleAdmin(false);
  };
  const [memberRoles, setMemberRoles] = useState<any[] | null>(null);
  // Why roles cannot be handed out here, straight from the bot.
  const [roleAdvice, setRoleAdvice] = useState("");

  const selectedRole = useMemo(
    () => roleList.find((r: any) => String(r.id) === String(roleId)) || null,
    [roleList, roleId]
  );

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await api.getServers(sort);
      setServers(data.servers || []);
      setTotals(data);
    } catch (err: any) {
      toast.error(err?.message || "Server konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sort]);

  const copyInvite = async (server: ServerRow, forceNew = false) => {
    setBusy(`invite-${server.id}`);
    try {
      const data = await api.createServerInvite(server.id, forceNew);
      setInvites((prev) => ({ ...prev, [server.id]: data.invite }));

      // navigator.clipboard needs a secure context; fall back to a text area.
      let copied = false;
      try {
        await navigator.clipboard.writeText(data.invite);
        copied = true;
      } catch {
        const field = document.createElement("textarea");
        field.value = data.invite;
        field.style.position = "fixed";
        field.style.opacity = "0";
        document.body.appendChild(field);
        field.select();
        try {
          copied = document.execCommand("copy");
        } catch {
          copied = false;
        }
        document.body.removeChild(field);
      }

      toast.success(copied ? "Einladung wurde kopiert." : `Invite: ${data.invite}`);
    } catch (err: any) {
      toast.error(err?.message || "Einladung konnte nicht erstellt werden.");
    } finally {
      setBusy("");
    }
  };

  const openRoleDialog = async (server: ServerRow) => {
    setRoleTarget(server);
    setRoleUserId(currentUserId || "");
    setRoleId("");
    setRoleMode("existing");
    setNewRoleName("");
    setNewRoleAdmin(false);
    setMemberRoles(null);
    setRoleList([]);
    try {
      const data = await api.getServerRoles(server.id);
      setRoleList(data.roles || []);
      setRoleAdvice(data.advice || "");
      if (currentUserId) {
        const member = await api.getServerMember(server.id, currentUserId);
        setMemberRoles(member.in_guild ? member.roles : null);
      }
    } catch (err: any) {
      toast.error(err?.message || "Rollen konnten nicht geladen werden.");
    }
  };

  const grantRole = async () => {
    if (!roleTarget) return;
    const uid = roleUserId.trim();
    if (!/^\d{15,20}$/.test(uid)) return toast.error("Bitte gib eine gültige Discord-Nutzer-ID ein.");
    if (roleMode === "existing" && !roleId) return toast.error("Bitte wähle eine Rolle aus.");
    if (roleMode === "existing" && selectedRole && !selectedRole.assignable) {
      return toast.error(selectedRole.hint || "Der Bot kann diese Rolle nicht vergeben.");
    }
    if (roleMode === "new" && !newRoleName.trim()) return toast.error("Bitte gib einen Rollennamen ein.");

    setBusy("role");
    try {
      const data = await api.grantServerRole(roleTarget.id, uid,
        roleMode === "existing"
          ? { role_id: roleId }
          : { role_name: newRoleName.trim(), administrator: newRoleAdmin }
      );
      toast.success(data.result || "Rolle wurde vergeben.");
      const member = await api.getServerMember(roleTarget.id, uid);
      setMemberRoles(member.in_guild ? member.roles : null);
      const roles = await api.getServerRoles(roleTarget.id);
      setRoleList(roles.roles || []);
      setRoleAdvice(roles.advice || "");
    } catch (err: any) {
      toast.error(err?.message || "Rolle konnte nicht vergeben werden.");
    } finally {
      setBusy("");
    }
  };

  const takeRole = async (rid: string) => {
    if (!roleTarget) return;
    setBusy("role");
    try {
      const data = await api.revokeServerRole(roleTarget.id, roleUserId.trim(), rid);
      toast.success(data.result || "Rolle wurde entfernt.");
      const member = await api.getServerMember(roleTarget.id, roleUserId.trim());
      setMemberRoles(member.in_guild ? member.roles : null);
    } catch (err: any) {
      toast.error(err?.message || "Rolle konnte nicht entfernt werden.");
    } finally {
      setBusy("");
    }
  };

  const submitLeave = async () => {
    if (!leaveTarget) return;
    if (leaveConfirm.trim().toLowerCase() !== leaveTarget.name.toLowerCase()) {
      return toast.error("Der Servername stimmt nicht überein.");
    }
    setBusy("leave");
    try {
      const data = await api.leaveServer(leaveTarget.id, {
        confirm_name: leaveConfirm.trim(),
        reason: leaveReason.trim(),
        message: leaveMessage.trim(),
        blacklist: leaveBlacklist,
      });
      toast.success(`Der Bot hat ${data.name} verlassen.`);
      setLeaveTarget(null);
      setLeaveConfirm("");
      setLeaveReason("");
      setLeaveMessage("");
      setLeaveBlacklist(false);
      await load(true);
    } catch (err: any) {
      toast.error(err?.message || "Der Server konnte nicht verlassen werden.");
    } finally {
      setBusy("");
    }
  };

  const copyInstallLink = async () => {
    try {
      const data = await api.getInstallLink(8);
      await navigator.clipboard.writeText(data.url);
      toast.success("Bot-Einladungslink wurde kopiert.");
    } catch (err: any) {
      toast.error(err?.message || "Einladungslink konnte nicht erstellt werden.");
    }
  };

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return servers.filter((server) => {
      if (onlyProblems && !(server.permissions.missing.length || server.blacklisted || server.bot_ratio > 0.5)) {
        return false;
      }
      if (!needle) return true;
      return (
        server.name.toLowerCase().includes(needle) ||
        server.id.includes(needle) ||
        (server.owner_name || "").toLowerCase().includes(needle) ||
        server.owner_id.includes(needle)
      );
    });
  }, [servers, query, onlyProblems]);

  if (loading) {
    return (
      <div className="flex min-h-72 items-center justify-center rounded-3xl border border-slate-800 bg-[#131318]">
        <div className="text-center">
          <Loader2 className="mx-auto h-6 w-6 animate-spin text-indigo-400" />
          <p className="mt-3 text-xs font-bold text-slate-500">Server werden geladen …</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Ruhiger Flottenkopf: Kontext, Zustand und wichtigste Aktionen. */}
      <section className="overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-indigo-500/[0.08] via-[#131318] to-[#111116]">
        <div className="flex flex-col gap-5 p-5 sm:p-6 lg:flex-row lg:items-center">
          <div className="flex min-w-0 flex-1 items-start gap-4">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-indigo-500/20 bg-indigo-500/10">
              <Shield className="h-5 w-5 text-indigo-400" />
            </span>
            <div className="min-w-0">
              <h2 className="text-xl font-black tracking-tight text-white">Server-Flotte</h2>
              <p className="mt-1 max-w-xl text-sm leading-relaxed text-slate-400">Alle Server, auf denen University Bot aktiv ist. Zustand prüfen, Einstellungen öffnen oder direkt eingreifen.</p>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button onClick={copyInstallLink} className="inline-flex items-center justify-center gap-2 rounded-xl border border-indigo-500/25 bg-indigo-500/10 px-4 py-2.5 text-xs font-bold text-indigo-300 transition hover:bg-indigo-500/15">
              <Link2 className="h-4 w-4" /> Bot-Einladungslink
            </button>
            <button onClick={() => load()} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-800 bg-[#0b0b0f] px-4 py-2.5 text-xs font-bold text-slate-300 transition hover:border-slate-700 hover:text-white">
              <RefreshCw className="h-4 w-4" /> Aktualisieren
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 border-t border-slate-800 sm:grid-cols-5">
          {[
            { label: "Server", value: totals?.count ?? 0, icon: Shield, color: "text-indigo-400" },
            { label: "Mitglieder", value: (totals?.total_members ?? 0).toLocaleString(), icon: Users, color: "text-emerald-400" },
            { label: "Ø Mitglieder", value: totals?.average_members ?? 0, icon: Sparkles, color: "text-cyan-400" },
            { label: "Premium", value: totals?.premium_count ?? 0, icon: Diamond, color: "text-amber-400" },
            { label: "Handlungsbedarf", value: totals?.missing_permissions_count ?? 0, icon: ShieldAlert, color: "text-rose-400" },
          ].map((card, index) => <div key={card.label} className={cn("flex items-center gap-3 border-slate-800 px-4 py-4", index > 0 && "border-l", index === 4 && "col-span-2 border-l-0 border-t sm:col-span-1 sm:border-l sm:border-t-0")}>
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-black/20"><card.icon className={cn("h-4 w-4", card.color)} /></span>
            <div className="min-w-0"><p className="truncate text-lg font-black tabular-nums text-white">{card.value}</p><p className="truncate text-[10px] font-bold uppercase tracking-wider text-slate-600">{card.label}</p></div>
          </div>)}
        </div>
      </section>

      {/* Suche und Filter stehen in einer Zeile; sekundäre Aktionen sind im Kopf. */}
      <section className="rounded-2xl border border-slate-800 bg-[#131318] p-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Server, ID oder Besitzer suchen …" className="w-full rounded-xl border border-slate-800 bg-[#0b0b0f] py-2.5 pl-10 pr-4 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-indigo-500/35" />
          </div>
          <div className="w-full lg:w-56"><Select value={sort} onValueChange={setSort} options={SORTS} /></div>
          <button onClick={() => setOnlyProblems(!onlyProblems)} aria-pressed={onlyProblems} className={cn("inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-xs font-bold transition", onlyProblems ? "border-rose-500/30 bg-rose-500/10 text-rose-300" : "border-slate-800 bg-[#0b0b0f] text-slate-400 hover:text-white")}>
            <AlertTriangle className="h-4 w-4" /> Nur Probleme
          </button>
        </div>
      </section>

      <div className="flex items-center justify-between px-1">
        <p className="text-xs font-bold text-slate-400">{visible.length} {visible.length === 1 ? "Server" : "Server"}</p>
        {(query || onlyProblems) && <button onClick={() => { setQuery(""); setOnlyProblems(false); }} className="text-xs font-bold text-indigo-400 hover:text-indigo-300">Filter zurücksetzen</button>}
      </div>

      {visible.length === 0 ? (
        <section className="rounded-3xl border border-dashed border-slate-800 bg-[#111116] px-5 py-16 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-slate-800/50"><Search className="h-5 w-5 text-slate-600" /></span>
          <p className="mt-4 text-sm font-bold text-slate-300">Kein Server gefunden</p>
          <p className="mt-1 text-xs text-slate-600">Passe die Suche oder den Problemfilter an.</p>
        </section>
      ) : <div className="grid items-start gap-3 xl:grid-cols-2">
        {visible.map((server) => {
          const open = expanded === server.id;
          const warn = server.permissions.missing.length > 0;
          const botFarm = server.bot_ratio > 0.5 && server.member_count > 20;
          return <article key={server.id} className={cn("overflow-hidden rounded-2xl border bg-[#131318] transition-colors", server.blacklisted ? "border-rose-500/30" : warn ? "border-amber-500/20" : "border-slate-800")}>
            <div className="p-4">
              <div className="flex items-start gap-3">
                {server.icon_url ? <img src={server.icon_url} alt="" className="h-11 w-11 shrink-0 rounded-xl border border-white/10 object-cover" /> : <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-slate-800"><Shield className="h-5 w-5 text-slate-500" /></span>}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2"><h3 className="truncate text-sm font-black text-white">{server.name}</h3>{server.premium && <Diamond className="h-3.5 w-3.5 shrink-0 text-amber-400" />}</div>
                  <p className="mt-0.5 truncate text-[11px] text-slate-500">Besitzer: {server.owner_name || server.owner_id}</p>
                </div>
                <div className="flex gap-1">
                  {server.blacklisted && <span title="Gesperrt" className="rounded-lg bg-rose-500/10 p-1.5 text-rose-400"><Ban className="h-3.5 w-3.5" /></span>}
                  {warn && <span title="Fehlende Rechte" className="rounded-lg bg-amber-500/10 p-1.5 text-amber-400"><ShieldAlert className="h-3.5 w-3.5" /></span>}
                  {botFarm && <span title="Hoher Bot-Anteil" className="rounded-lg bg-rose-500/10 p-1.5 text-rose-400"><AlertTriangle className="h-3.5 w-3.5" /></span>}
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 overflow-hidden rounded-xl border border-slate-800 bg-[#0c0c10]">
                <div className="px-3 py-2.5"><p className="text-sm font-black text-white">{server.member_count.toLocaleString()}</p><p className="text-[9px] uppercase tracking-wider text-slate-600">Mitglieder</p></div>
                <div className="border-l border-slate-800 px-3 py-2.5"><p className="text-sm font-black text-white">{server.channel_count}</p><p className="text-[9px] uppercase tracking-wider text-slate-600">Kanäle</p></div>
                <div className="border-l border-slate-800 px-3 py-2.5"><p className="text-sm font-black text-white">{server.boost_count}</p><p className="text-[9px] uppercase tracking-wider text-slate-600">Boosts</p></div>
              </div>

              <div className="mt-3 grid grid-cols-4 gap-2">
                <button onClick={() => copyInvite(server)} disabled={busy === `invite-${server.id}`} title="Einladung kopieren" className="grid place-items-center rounded-xl border border-indigo-500/20 bg-indigo-500/10 py-2.5 text-indigo-300 hover:bg-indigo-500/15 disabled:opacity-40">{busy === `invite-${server.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <Copy className="h-4 w-4" />}</button>
                <button onClick={() => openRoleDialog(server)} title="Rolle vergeben" className="grid place-items-center rounded-xl border border-slate-800 bg-[#0c0c10] py-2.5 text-slate-400 hover:text-white"><UserPlus className="h-4 w-4" /></button>
                <Link href={`/dashboard/guild/${server.id}`} title="Server verwalten" className="grid place-items-center rounded-xl border border-slate-800 bg-[#0c0c10] py-2.5 text-slate-400 hover:text-white"><ArrowUpRight className="h-4 w-4" /></Link>
                <button onClick={() => setExpanded(open ? null : server.id)} aria-expanded={open} title="Details" className="grid place-items-center rounded-xl border border-slate-800 bg-[#0c0c10] py-2.5 text-slate-400 hover:text-white"><ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} /></button>
              </div>
            </div>

            {open && <div className="space-y-3 border-t border-slate-800 bg-[#0c0c10]/70 p-4">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[{ label: "Menschen", value: server.human_count.toLocaleString() }, { label: "Bots", value: server.bot_count.toLocaleString() }, { label: "Rollen", value: server.role_count }, { label: "Boost-Level", value: server.boost_level }].map(stat => <div key={stat.label} className="rounded-xl border border-slate-800 bg-[#101014] p-2.5"><p className="text-sm font-black text-white">{stat.value}</p><p className="text-[9px] uppercase tracking-wider text-slate-600">{stat.label}</p></div>)}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                <button onClick={() => { navigator.clipboard?.writeText(server.id); toast.success("Server-ID kopiert."); }} className="inline-flex items-center gap-1 font-mono hover:text-white">{server.id}<Copy className="h-3 w-3" /></button>
                <span>Beigetreten: {formatDate(server.joined_at)}</span><span>Erstellt: {formatDate(server.created_at)}</span>
              </div>
              {warn && <div className="flex gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-200"><ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" /><span>Fehlende Rechte: <b>{server.permissions.missing.slice(0, 6).join(", ")}</b>{server.permissions.missing.length > 6 && ` +${server.permissions.missing.length - 6}`}</span></div>}
              {botFarm && <div className="flex gap-2 rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-xs text-rose-200"><AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />{Math.round(server.bot_ratio * 100)} % der Mitglieder sind Bots.</div>}
              {invites[server.id] && <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3"><CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" /><a href={invites[server.id]} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-xs text-emerald-300 hover:underline">{invites[server.id]}</a><ExternalLink className="h-3.5 w-3.5 text-emerald-400" /></div>}
              <button onClick={() => { setLeaveTarget(server); setLeaveConfirm(""); }} className="inline-flex items-center gap-2 rounded-xl border border-rose-500/20 bg-rose-500/10 px-3.5 py-2.5 text-xs font-bold text-rose-300 hover:bg-rose-500/15"><DoorOpen className="h-3.5 w-3.5" /> Server verlassen</button>
            </div>}
          </article>;
        })}
      </div>}

      {/* Leave dialog */}
      {leaveTarget && (
        <div className="fixed inset-0 z-[60] overflow-y-auto bg-black/70 backdrop-blur-sm p-4 sm:p-6">
          <div className="w-full max-w-lg mx-auto my-8 bg-[#131318] border border-slate-800 rounded-3xl overflow-hidden">
            <div className="p-6 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-2xl bg-rose-500/15 border border-rose-500/25 flex items-center justify-center">
                  <DoorOpen className="h-5 w-5 text-rose-400" />
                </div>
                <div>
                  <h3 className="font-black text-white">Server verlassen</h3>
                  <p className="text-xs text-slate-500 truncate max-w-[240px]">{leaveTarget.name}</p>
                </div>
              </div>
              <button onClick={closeLeaveDialog} className="text-slate-500 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <div className="flex gap-3 p-4 rounded-2xl bg-rose-500/10 border border-rose-500/25 text-sm text-rose-200/90">
                <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                Der Bot verlässt einen Server mit {leaveTarget.member_count.toLocaleString()} Mitgliedern. Die Einstellungen bleiben gespeichert und sind bei einer erneuten Einladung wieder verfügbar.
              </div>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Servernamen zur Bestätigung eingeben
                </span>
                <input
                  value={leaveConfirm}
                  onChange={(e) => setLeaveConfirm(e.target.value)}
                  placeholder={leaveTarget.name}
                  className="w-full bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-rose-500/40"
                />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Abschiedsnachricht (optional)
                </span>
                <textarea
                  value={leaveMessage}
                  onChange={(e) => setLeaveMessage(e.target.value)}
                  placeholder="Wird vor dem Verlassen in den Systemkanal gesendet"
                  className="w-full h-20 bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Grund für das Protokoll
                </span>
                <input
                  value={leaveReason}
                  onChange={(e) => setLeaveReason(e.target.value)}
                  className="w-full bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <label className="flex items-center gap-3 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={leaveBlacklist}
                  onChange={(e) => setLeaveBlacklist(e.target.checked)}
                  className="h-4 w-4 rounded accent-primary"
                />
                Server sperren, damit der Bot nicht erneut eingeladen werden kann
              </label>
            </div>

            <div className="p-6 border-t border-slate-800 flex gap-3">
              <button
                onClick={closeLeaveDialog}
                className="flex-1 py-3 rounded-2xl bg-[#0e0e12] border border-slate-800 text-sm font-bold text-slate-300 hover:bg-white/[0.06]"
              >
                Abbrechen
              </button>
              <button
                onClick={submitLeave}
                disabled={busy === "leave" || leaveConfirm.trim().toLowerCase() !== leaveTarget.name.toLowerCase()}
                className="flex-1 py-3 rounded-2xl bg-rose-500/90 hover:bg-rose-500 text-sm font-black uppercase tracking-widest disabled:opacity-30"
              >
                {busy === "leave" ? <Loader2 className="h-4 w-4 inline animate-spin" /> : "Jetzt verlassen"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Role dialog */}
      {roleTarget && (
        <div className="fixed inset-0 z-[60] overflow-y-auto bg-black/70 backdrop-blur-sm p-4 sm:p-6">
          <div className="w-full max-w-xl mx-auto my-8 bg-[#131318] border border-slate-800 rounded-3xl overflow-hidden">
            <div className="p-6 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
                  <UserPlus className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-black text-white">Rolle vergeben</h3>
                  <p className="text-xs text-slate-500 truncate max-w-[240px]">{roleTarget.name}</p>
                </div>
              </div>
              <button onClick={closeRoleDialog} className="text-slate-500 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">Nutzer-ID</span>
                <div className="flex gap-2">
                  <input
                    value={roleUserId}
                    onChange={(e) => setRoleUserId(e.target.value)}
                    placeholder="Discord-Nutzer-ID"
                    className="flex-1 bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  {currentUserId && (
                    <button
                      onClick={async () => {
                        setRoleUserId(currentUserId);
                        try {
                          const member = await api.getServerMember(roleTarget.id, currentUserId);
                          setMemberRoles(member.in_guild ? member.roles : null);
                        } catch { /* ignore */ }
                      }}
                      className="px-4 rounded-2xl bg-[#0e0e12] border border-slate-800 text-xs font-bold text-slate-300 hover:bg-white/[0.06] whitespace-nowrap"
                    >
                      Ich
                    </button>
                  )}
                </div>
              </label>

              {memberRoles !== null && (
                <div className="space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                    Vorhandene Rollen dieser Person
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {memberRoles.length === 0 && <span className="text-sm text-slate-500">Keine</span>}
                    {memberRoles.map((role: any) => (
                      <button
                        key={role.id}
                        onClick={() => takeRole(role.id)}
                        disabled={busy === "role" || role.managed}
                        title={role.managed ? "Verwaltete Rollen können nicht entfernt werden" : "Zum Entfernen anklicken"}
                        className="group px-3 py-1.5 rounded-xl text-xs font-bold border flex items-center gap-1.5 disabled:opacity-40"
                        style={{
                          color: role.color,
                          borderColor: `${role.color}40`,
                          backgroundColor: `${role.color}14`,
                        }}
                      >
                        {role.name}
                        {!role.managed && <X className="h-3 w-3 opacity-50 group-hover:opacity-100" />}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-2 p-1.5 bg-[#0e0e12] border border-slate-800 rounded-2xl">
                {(["existing", "new"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setRoleMode(mode)}
                    className={cn(
                      "flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all",
                      roleMode === mode ? "bg-primary text-white" : "text-slate-400 hover:text-white"
                    )}
                  >
                    {mode === "existing" ? "Vorhandene Rolle" : "Neue erstellen"}
                  </button>
                ))}
              </div>

              {roleMode === "existing" ? (
                <label className="block space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-500">Rolle</span>
                  <Select
                    value={roleId}
                    onValueChange={setRoleId}
                    placeholder={
                      roleList.some((r: any) => r.assignable)
                        ? "Rolle auswählen"
                        : "Aktuell kann keine Rolle vergeben werden"
                    }
                    options={roleList.map((r: any) => ({
                      value: r.id,
                      label: r.assignable
                        ? `${r.name}${r.administrator ? " (Admin)" : ""}`
                        : `${r.name} — ${
                            r.blocked_reason === "own_role"
                              ? "eigene Bot-Rolle"
                              : r.blocked_reason === "managed"
                              ? "Bot-/Integrationsrolle"
                              : r.blocked_reason === "no_permission"
                              ? "dem Bot fehlt Rollen verwalten"
                              : "über der Bot-Rolle"
                          }`,
                    }))}
                  />

                  {/* The old build hid unusable roles and just said "99 hidden",
                      which gave no clue what to actually do about it. */}
                  {selectedRole && !selectedRole.assignable && (
                    <div className="flex gap-2 p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 text-xs text-amber-200/90">
                      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                      <span>{selectedRole.hint}</span>
                    </div>
                  )}

                  {roleAdvice && !selectedRole && (
                    <div className="flex gap-2 p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 text-xs text-amber-200/90">
                      <ShieldAlert className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                      <span>{roleAdvice}</span>
                    </div>
                  )}
                </label>
              ) : (
                <div className="space-y-4">
                  <label className="block space-y-2">
                    <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                      Neuer Rollenname
                    </span>
                    <input
                      value={newRoleName}
                      onChange={(e) => setNewRoleName(e.target.value)}
                      placeholder="z. B. Bot-Team"
                      className="w-full bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </label>
                  <label className="flex items-center gap-3 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newRoleAdmin}
                      onChange={(e) => setNewRoleAdmin(e.target.checked)}
                      className="h-4 w-4 rounded accent-primary"
                    />
                    Administrator-Berechtigung vergeben
                  </label>
                  {newRoleAdmin && (
                    <div className="flex gap-3 p-3 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-xs text-amber-200/90">
                      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                      Administrator bedeutet vollständige Kontrolle über den Server. Der Bot benötigt selbst Administrator, um diese Rolle anzulegen.
                    </div>
                  )}
                </div>
              )}

              {!roleTarget.permissions.administrator && (
                <p className="text-[11px] text-slate-500">
                  Der Bot kann nur Rollen unter seiner höchsten Rolle vergeben. Fehlt eine Rolle, verschiebe die Bot-Rolle in Discord weiter nach oben.
                </p>
              )}
            </div>

            <div className="p-6 border-t border-slate-800 flex gap-3">
              <button
                onClick={closeRoleDialog}
                className="flex-1 py-3 rounded-2xl bg-[#0e0e12] border border-slate-800 text-sm font-bold text-slate-300 hover:bg-white/[0.06]"
              >
                Schließen
              </button>
              <button
                onClick={grantRole}
                disabled={busy === "role"}
                className="flex-1 py-3 rounded-2xl bg-primary text-sm font-semibold hover:brightness-110 disabled:opacity-40"
              >
                {busy === "role" ? <Loader2 className="h-4 w-4 inline animate-spin" /> : "Rolle vergeben"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
