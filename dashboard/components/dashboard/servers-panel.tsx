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
  { value: "members", label: "Most members" },
  { value: "name", label: "Name A–Z" },
  { value: "joined", label: "Recently joined" },
  { value: "created", label: "Newest server" },
  { value: "bots", label: "Highest bot share" },
  { value: "boosts", label: "Most boosts" },
];

function formatDate(timestamp: number): string {
  if (!timestamp) return "unknown";
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
      toast.error(err?.message || "Could not load the servers.");
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

      toast.success(copied ? "Invite copied to the clipboard." : `Invite: ${data.invite}`);
    } catch (err: any) {
      toast.error(err?.message || "Could not create an invite.");
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
      toast.error(err?.message || "Could not load the roles.");
    }
  };

  const grantRole = async () => {
    if (!roleTarget) return;
    const uid = roleUserId.trim();
    if (!/^\d{15,20}$/.test(uid)) return toast.error("Please enter a valid Discord user ID.");
    if (roleMode === "existing" && !roleId) return toast.error("Please pick a role.");
    if (roleMode === "existing" && selectedRole && !selectedRole.assignable) {
      return toast.error(selectedRole.hint || "The bot cannot assign this role.");
    }
    if (roleMode === "new" && !newRoleName.trim()) return toast.error("Please enter a role name.");

    setBusy("role");
    try {
      const data = await api.grantServerRole(roleTarget.id, uid,
        roleMode === "existing"
          ? { role_id: roleId }
          : { role_name: newRoleName.trim(), administrator: newRoleAdmin }
      );
      toast.success(data.result || "Role granted.");
      const member = await api.getServerMember(roleTarget.id, uid);
      setMemberRoles(member.in_guild ? member.roles : null);
      const roles = await api.getServerRoles(roleTarget.id);
      setRoleList(roles.roles || []);
      setRoleAdvice(roles.advice || "");
    } catch (err: any) {
      toast.error(err?.message || "Could not grant the role.");
    } finally {
      setBusy("");
    }
  };

  const takeRole = async (rid: string) => {
    if (!roleTarget) return;
    setBusy("role");
    try {
      const data = await api.revokeServerRole(roleTarget.id, roleUserId.trim(), rid);
      toast.success(data.result || "Role removed.");
      const member = await api.getServerMember(roleTarget.id, roleUserId.trim());
      setMemberRoles(member.in_guild ? member.roles : null);
    } catch (err: any) {
      toast.error(err?.message || "Could not remove the role.");
    } finally {
      setBusy("");
    }
  };

  const submitLeave = async () => {
    if (!leaveTarget) return;
    if (leaveConfirm.trim().toLowerCase() !== leaveTarget.name.toLowerCase()) {
      return toast.error("The server name does not match.");
    }
    setBusy("leave");
    try {
      const data = await api.leaveServer(leaveTarget.id, {
        confirm_name: leaveConfirm.trim(),
        reason: leaveReason.trim(),
        message: leaveMessage.trim(),
        blacklist: leaveBlacklist,
      });
      toast.success(`The bot left ${data.name}.`);
      setLeaveTarget(null);
      setLeaveConfirm("");
      setLeaveReason("");
      setLeaveMessage("");
      setLeaveBlacklist(false);
      await load(true);
    } catch (err: any) {
      toast.error(err?.message || "Could not leave the server.");
    } finally {
      setBusy("");
    }
  };

  const copyInstallLink = async () => {
    try {
      const data = await api.getInstallLink(8);
      await navigator.clipboard.writeText(data.url);
      toast.success("Invite link for the bot copied.");
    } catch (err: any) {
      toast.error(err?.message || "Could not build the link.");
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
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-16 flex items-center justify-center">
        <Loader2 className="h-6 w-6 text-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Totals */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {[
          { label: "Servers", value: totals?.count ?? 0, icon: Shield, color: "text-primary" },
          { label: "Members", value: (totals?.total_members ?? 0).toLocaleString(), icon: Users, color: "text-emerald-400" },
          { label: "Average", value: totals?.average_members ?? 0, icon: Sparkles, color: "text-blue-400" },
          { label: "Premium", value: totals?.premium_count ?? 0, icon: Diamond, color: "text-amber-400" },
          { label: "Needs attention", value: totals?.missing_permissions_count ?? 0, icon: ShieldAlert, color: "text-rose-400" },
        ].map((card) => (
          <div key={card.label} className="bg-[#131318] border border-slate-800 rounded-3xl p-5">
            <card.icon className={cn("h-5 w-5 mb-3", card.color)} />
            <p className="text-3xl font-black text-white">{card.value}</p>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-6 flex flex-col lg:flex-row gap-4 lg:items-center">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by server name, ID or owner"
            className="w-full bg-[#0e0e12] border border-slate-800 rounded-2xl pl-11 pr-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="w-full lg:w-52">
          <Select value={sort} onValueChange={setSort} options={SORTS} />
        </div>
        <button
          onClick={() => setOnlyProblems(!onlyProblems)}
          className={cn(
            "px-5 py-3 rounded-2xl text-sm font-bold border transition-all whitespace-nowrap",
            onlyProblems
              ? "bg-rose-500/15 border-rose-500/30 text-rose-300"
              : "bg-[#0e0e12] border-slate-800 text-slate-300 hover:bg-white/[0.06]"
          )}
        >
          <AlertTriangle className="h-4 w-4 inline mr-2" />
          Problems only
        </button>
        <button
          onClick={copyInstallLink}
          className="px-5 py-3 rounded-2xl bg-primary/15 border border-primary/30 text-sm font-bold text-primary hover:bg-primary/25 whitespace-nowrap"
        >
          <Link2 className="h-4 w-4 inline mr-2" />
          Bot invite link
        </button>
        <button
          onClick={() => load()}
          className="px-5 py-3 rounded-2xl bg-[#0e0e12] border border-slate-800 text-sm font-bold text-slate-300 hover:bg-white/[0.06]"
        >
          <RefreshCw className="h-4 w-4 inline mr-2" />
          Refresh
        </button>
      </div>

      {/* Server list */}
      <div className="space-y-2">
        {visible.length === 0 && (
          <div className="bg-[#131318] border border-slate-800 rounded-3xl p-12 text-center text-slate-500">
            No server matches this filter.
          </div>
        )}

        {visible.map((server) => {
          const open = expanded === server.id;
          const warn = server.permissions.missing.length > 0;
          const botFarm = server.bot_ratio > 0.5 && server.member_count > 20;

          return (
            <div
              key={server.id}
              className={cn(
                "bg-[#131318] border rounded-2xl overflow-hidden transition-colors",
                server.blacklisted
                  ? "border-rose-500/30 bg-rose-500/[0.03]"
                  : warn
                  ? "border-amber-500/20"
                  : "border-slate-800"
              )}
            >
              {/* Compact row: everything important on one line. */}
              <div className="flex items-center gap-3 p-3">
                {server.icon_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={server.icon_url} alt="" className="h-10 w-10 rounded-xl border border-white/10 shrink-0" />
                ) : (
                  <div className="h-10 w-10 rounded-xl bg-slate-800 flex items-center justify-center shrink-0">
                    <Shield className="h-5 w-5 text-slate-500" />
                  </div>
                )}

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white truncate">{server.name}</span>
                    {server.premium && (
                      <Diamond className="h-3.5 w-3.5 text-amber-400 shrink-0" aria-label="Premium" />
                    )}
                    {server.blacklisted && (
                      <Ban className="h-3.5 w-3.5 text-rose-400 shrink-0" aria-label="Blacklisted" />
                    )}
                    {warn && (
                      <ShieldAlert className="h-3.5 w-3.5 text-amber-400 shrink-0" aria-label="Missing permissions" />
                    )}
                    {botFarm && (
                      <AlertTriangle className="h-3.5 w-3.5 text-rose-400 shrink-0" aria-label="Bot farm" />
                    )}
                  </div>
                  <p className="text-xs text-slate-500 truncate">
                    {server.member_count.toLocaleString()} members · {server.owner_name || server.owner_id}
                  </p>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    onClick={() => copyInvite(server)}
                    disabled={busy === `invite-${server.id}`}
                    title="Copy an invite link to this server"
                    className="p-2.5 rounded-xl bg-primary/15 border border-primary/30 text-primary hover:bg-primary/25 disabled:opacity-40"
                  >
                    {busy === `invite-${server.id}` ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>

                  <button
                    onClick={() => openRoleDialog(server)}
                    title="Give somebody a role here"
                    className="p-2.5 rounded-xl bg-[#0e0e12] border border-slate-800 text-slate-300 hover:bg-white/[0.06]"
                  >
                    <UserPlus className="h-4 w-4" />
                  </button>

                  <Link
                    href={`/dashboard/guild/${server.id}`}
                    title="Open this server's settings"
                    className="p-2.5 rounded-xl bg-[#0e0e12] border border-slate-800 text-slate-300 hover:bg-white/[0.06] inline-flex"
                  >
                    <ArrowUpRight className="h-4 w-4" />
                  </Link>

                  <button
                    onClick={() => setExpanded(open ? null : server.id)}
                    title={open ? "Show less" : "Show details"}
                    className="p-2.5 rounded-xl bg-[#0e0e12] border border-slate-800 text-slate-400 hover:bg-white/[0.06]"
                  >
                    <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
                  </button>
                </div>
              </div>

              {/* Details only when asked for, so the list stays short. */}
              {open && (
                <div className="border-t border-slate-800 p-4 bg-[#0e0e12]/60 space-y-4">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[
                      { label: "Members", value: server.member_count.toLocaleString() },
                      { label: "Humans", value: server.human_count.toLocaleString() },
                      { label: "Channels", value: server.channel_count },
                      { label: "Roles", value: server.role_count },
                    ].map((stat) => (
                      <div key={stat.label} className="bg-[#0e0e12] rounded-xl py-2 px-2 border border-slate-800 text-center">
                        <p className="text-base font-black text-white">{stat.value}</p>
                        <p className="text-[9px] font-black uppercase tracking-widest text-slate-500">{stat.label}</p>
                      </div>
                    ))}
                  </div>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
                    <button
                      onClick={() => {
                        navigator.clipboard?.writeText(server.id);
                        toast.success("Server ID copied.");
                      }}
                      className="font-mono hover:text-slate-300 inline-flex items-center gap-1"
                    >
                      {server.id}
                      <Copy className="h-3 w-3" />
                    </button>
                    <span>Joined {formatDate(server.joined_at)}</span>
                    <span>Created {formatDate(server.created_at)}</span>
                    {server.boost_count > 0 && <span>{server.boost_count} boosts</span>}
                  </div>

                  {warn && (
                    <div className="flex gap-2 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-200/90">
                      <ShieldAlert className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                      <span>
                        Missing permissions:{" "}
                        <span className="font-bold">{server.permissions.missing.slice(0, 6).join(", ")}</span>
                        {server.permissions.missing.length > 6 && ` +${server.permissions.missing.length - 6}`}
                      </span>
                    </div>
                  )}

                  {botFarm && (
                    <div className="flex gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-xs text-rose-200/90">
                      <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                      {Math.round(server.bot_ratio * 100)} % of the members are bots — this looks like a bot farm.
                    </div>
                  )}

                  {invites[server.id] && (
                    <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                      <a
                        href={invites[server.id]}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-emerald-300 hover:underline truncate flex-1"
                      >
                        {invites[server.id]}
                      </a>
                      <ExternalLink className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                    </div>
                  )}

                  <button
                    onClick={() => { setLeaveTarget(server); setLeaveConfirm(""); }}
                    className="px-4 py-2.5 rounded-xl bg-rose-500/10 border border-rose-500/25 text-xs font-black uppercase tracking-wider text-rose-400 hover:bg-rose-500/20"
                  >
                    <DoorOpen className="h-3.5 w-3.5 inline mr-1.5" />
                    Leave server
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

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
                  <h3 className="font-black text-white">Leave server</h3>
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
                The bot leaves {leaveTarget.member_count.toLocaleString()} members behind. The
                settings stay in the database, so a later re-invite picks up where it left off.
              </div>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Type the server name to confirm
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
                  Goodbye message (optional)
                </span>
                <textarea
                  value={leaveMessage}
                  onChange={(e) => setLeaveMessage(e.target.value)}
                  placeholder="Sent to the system channel before leaving"
                  className="w-full h-20 bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Reason (audit log)
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
                Blacklist this server so the bot cannot be re-invited
              </label>
            </div>

            <div className="p-6 border-t border-slate-800 flex gap-3">
              <button
                onClick={closeLeaveDialog}
                className="flex-1 py-3 rounded-2xl bg-[#0e0e12] border border-slate-800 text-sm font-bold text-slate-300 hover:bg-white/[0.06]"
              >
                Cancel
              </button>
              <button
                onClick={submitLeave}
                disabled={busy === "leave" || leaveConfirm.trim().toLowerCase() !== leaveTarget.name.toLowerCase()}
                className="flex-1 py-3 rounded-2xl bg-rose-500/90 hover:bg-rose-500 text-sm font-black uppercase tracking-widest disabled:opacity-30"
              >
                {busy === "leave" ? <Loader2 className="h-4 w-4 inline animate-spin" /> : "Leave now"}
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
                  <h3 className="font-black text-white">Give a role</h3>
                  <p className="text-xs text-slate-500 truncate max-w-[240px]">{roleTarget.name}</p>
                </div>
              </div>
              <button onClick={closeRoleDialog} className="text-slate-500 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">User ID</span>
                <div className="flex gap-2">
                  <input
                    value={roleUserId}
                    onChange={(e) => setRoleUserId(e.target.value)}
                    placeholder="Discord user ID"
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
                      Me
                    </button>
                  )}
                </div>
              </label>

              {memberRoles !== null && (
                <div className="space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                    Roles this person already has
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {memberRoles.length === 0 && <span className="text-sm text-slate-500">None</span>}
                    {memberRoles.map((role: any) => (
                      <button
                        key={role.id}
                        onClick={() => takeRole(role.id)}
                        disabled={busy === "role" || role.managed}
                        title={role.managed ? "Managed roles cannot be removed" : "Click to remove"}
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
                    {mode === "existing" ? "Existing role" : "Create new"}
                  </button>
                ))}
              </div>

              {roleMode === "existing" ? (
                <label className="block space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-500">Role</span>
                  <Select
                    value={roleId}
                    onValueChange={setRoleId}
                    placeholder={
                      roleList.some((r: any) => r.assignable)
                        ? "Pick a role"
                        : "No role can be assigned yet"
                    }
                    options={roleList.map((r: any) => ({
                      value: r.id,
                      label: r.assignable
                        ? `${r.name}${r.administrator ? " (Admin)" : ""}`
                        : `${r.name} — ${
                            r.blocked_reason === "own_role"
                              ? "the bot's own role"
                              : r.blocked_reason === "managed"
                              ? "bot/integration role"
                              : r.blocked_reason === "no_permission"
                              ? "bot lacks Manage Roles"
                              : "above the bot's role"
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
                      New role name
                    </span>
                    <input
                      value={newRoleName}
                      onChange={(e) => setNewRoleName(e.target.value)}
                      placeholder="e.g. Bot Owner"
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
                    Grant Administrator permission
                  </label>
                  {newRoleAdmin && (
                    <div className="flex gap-3 p-3 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-xs text-amber-200/90">
                      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                      Administrator means full control over the server. The bot needs Administrator
                      itself to create such a role.
                    </div>
                  )}
                </div>
              )}

              {!roleTarget.permissions.administrator && (
                <p className="text-[11px] text-slate-500">
                  The bot can only hand out roles below its own highest role. If a role is missing,
                  move the bot&apos;s role further up in the Discord settings.
                </p>
              )}
            </div>

            <div className="p-6 border-t border-slate-800 flex gap-3">
              <button
                onClick={closeRoleDialog}
                className="flex-1 py-3 rounded-2xl bg-[#0e0e12] border border-slate-800 text-sm font-bold text-slate-300 hover:bg-white/[0.06]"
              >
                Close
              </button>
              <button
                onClick={grantRole}
                disabled={busy === "role"}
                className="flex-1 py-3 rounded-2xl bg-primary text-sm font-semibold hover:brightness-110 disabled:opacity-40"
              >
                {busy === "role" ? <Loader2 className="h-4 w-4 inline animate-spin" /> : "Grant a role"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
