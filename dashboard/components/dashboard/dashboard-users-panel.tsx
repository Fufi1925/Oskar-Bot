"use client";

/**
 * The people who authorised this bot through Discord OAuth — and the button
 * to throw them out.
 *
 * The list is deliberately limited to accounts that actually signed in here,
 * plus owners and team-role holders. An earlier version also listed every
 * Discord server admin the bot could see, which drowned the handful of real
 * dashboard users in hundreds of accounts that never authorised anything.
 * That view is still available behind the "Discord admins" toggle.
 *
 * A ban beats every route in: the OAuth sign-in itself is refused, open
 * sessions are cut off on their next request, and it outranks Manage Server.
 */

import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Ban, Check, Clock, Copy, Crown, Loader2, LogIn, RefreshCw,
  Search, Shield, ShieldCheck, Trash2, UserX, Users, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Select } from "@/components/ui/select";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";

interface DashboardUser {
  user_id: string;
  username: string | null;
  display_name: string | null;
  avatar: string | null;
  sources: string[];
  is_owner: boolean;
  owner_kind: string | null;
  roles: Array<{ key: string; label: string; color: string }>;
  highest_rank: number;
  permission_count: number;
  guild_admin_of: Array<{
    guild_id: string;
    guild_name: string;
    is_guild_owner: boolean;
    administrator: boolean;
  }>;
  first_seen: number;
  last_seen: number;
  login_count: number;
  banned: boolean;
  ban: { reason: string; banned_at: number; expires_at: number; banned_by: string } | null;
}

const DURATIONS: Array<{ value: string; label: string }> = [
  { value: "0", label: "Permanent" },
  { value: "3600", label: "1 hour" },
  { value: "86400", label: "1 day" },
  { value: "604800", label: "7 days" },
  { value: "2592000", label: "30 days" },
];

const FILTERS: Array<{ value: string; label: string }> = [
  { value: "all", label: "All users" },
  { value: "banned", label: "Banned" },
  { value: "owner", label: "Owners" },
  { value: "team_role", label: "Team roles" },
  { value: "login", label: "Has signed in" },
];

function timeAgo(timestamp: number): string {
  if (!timestamp) return "never";
  const seconds = Math.floor(Date.now() / 1000) - timestamp;
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days < 31) return `${days} d ago`;
  return new Date(timestamp * 1000).toLocaleDateString();
}

function SourceBadge({ source }: { source: string }) {
  const styles: Record<string, { label: string; className: string; icon: any }> = {
    owner: { label: "Owner", className: "bg-amber-500/10 text-amber-400 border-amber-500/25", icon: Crown },
    team_role: { label: "Team role", className: "bg-primary/10 text-primary border-primary/25", icon: Shield },
    discord_admin: { label: "Discord admin", className: "bg-indigo-500/10 text-indigo-300 border-indigo-500/25", icon: ShieldCheck },
    login: { label: "Signed in", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25", icon: LogIn },
  };
  const style = styles[source];
  if (!style) return null;
  const Icon = style.icon;
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-black uppercase tracking-wider", style.className)}>
      <Icon className="h-3 w-3" />
      {style.label}
    </span>
  );
}

export function DashboardUsersPanel({ currentUserId }: { currentUserId?: string }) {
  const [users, setUsers] = useState<DashboardUser[]>([]);
  const [summary, setSummary] = useState<{
    count: number; authorised_count: number; banned_count: number;
    owner_count: number; role_count: number; discord_admin_count: number;
  } | null>(null);
  // Off by default: these people never authorised the bot.
  const [showDiscordAdmins, setShowDiscordAdmins] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  // Ban dialog
  // Two ways to ban, and they used to share one set of fields.
  //
  // Typing a reason into the "Ban by user ID" form and then clicking
  // Ban on somebody in the list wiped what you had typed, because
  // opening the dialog reset banReason and banDuration. The revoke
  // checkbox was not reset at all, so it silently carried over in the
  // other direction: unticking it up top left the next dialog unticked
  // without showing why.
  const [banTarget, setBanTarget] = useState<DashboardUser | null>(null);
  const [banReason, setBanReason] = useState("");
  const [banDuration, setBanDuration] = useState("0");
  const [banRevokeRoles, setBanRevokeRoles] = useState(true);

  // The by-ID form keeps its own copy of all three.
  const [manualReason, setManualReason] = useState("");
  const [manualDuration, setManualDuration] = useState("0");
  const [manualRevokeRoles, setManualRevokeRoles] = useState(true);

  // Manual ban by ID, for someone who never signed in
  const [manualId, setManualId] = useState("");

  // A typed-out ban reason is an unsaved edit like any other: leaving
  // the tab used to drop it silently. Only the id counts as "started" --
  // a reason with no target is nothing to protect.
  const manualDirty = manualId.trim() ? 1 : 0;
  const manualGuard = useSaveGuard(manualDirty, "banbyid-save-bar");

  /**
   * Close the ban dialog, but not over a typed-out reason.
   *
   * A modal has nowhere to put a sticky bar and no page left to scroll
   * one into view, so this is the one place a confirm() is right.
   */
  const closeBanDialog = () => {
    if (banReason.trim() && !confirm("Den eingetippten Grund verwerfen?")) return;
    setBanTarget(null);
  };

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      // Only people who went through Discord OAuth. Including every server
      // admin buried the handful of real dashboard users among hundreds of
      // accounts that never authorised anything.
      const data = await api.getDashboardUsers(showDiscordAdmins);
      setUsers(data.users || []);
      setSummary({
        count: data.count,
        authorised_count: (data as any).authorised_count ?? data.count,
        banned_count: data.banned_count,
        owner_count: data.owner_count,
        role_count: data.role_count,
        discord_admin_count: data.discord_admin_count,
      });
    } catch (err: any) {
      toast.error(err?.message || "Could not load the user list.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(() => load(true), 60000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showDiscordAdmins]);

  /**
   * Ban somebody. The caller says who and with what -- nothing is read
   * back out of the other form's state.
   *
   * The by-ID button used to run `setBanTarget(null); submitBan();`.
   * That does not do what it looks like: a state setter does not take
   * effect until the next render, so submitBan() still saw the old
   * banTarget and would have banned the person from the dialog rather
   * than the id that was typed in.
   */
  const submitBan = async (
    targetId: string,
    reason: string,
    duration: string,
    revokeRoles: boolean,
    onDone: () => void,
  ) => {
    const clean = targetId.trim();
    if (!/^\d{15,20}$/.test(clean)) {
      return toast.error("Please enter a valid Discord user ID.");
    }
    if (clean === currentUserId) return toast.error("You cannot ban yourself.");

    setBusy(true);
    try {
      await api.banDashboardUser({
        user_id: clean,
        reason: reason.trim(),
        duration_seconds: Number(duration) || 0,
        revoke_roles: revokeRoles,
      });
      toast.success("User banned from the dashboard.");
      onDone();
      await load(true);
    } catch (err: any) {
      toast.error(err?.message || "The ban failed.");
    } finally {
      setBusy(false);
    }
  };

  const unban = async (user: DashboardUser) => {
    setBusy(true);
    try {
      await api.unbanDashboardUser(user.user_id);
      toast.success("Ban lifted.");
      await load(true);
    } catch (err: any) {
      toast.error(err?.message || "Could not lift the ban.");
    } finally {
      setBusy(false);
    }
  };

  const forget = async (user: DashboardUser) => {
    setBusy(true);
    try {
      await api.forgetDashboardLogin(user.user_id);
      toast.success("Login record deleted.");
      await load(true);
    } catch (err: any) {
      toast.error(err?.message || "Could not delete the record.");
    } finally {
      setBusy(false);
    }
  };

  const copyId = (id: string) => {
    navigator.clipboard?.writeText(id);
    toast.success("User ID copied.");
  };

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return users.filter((user) => {
      if (filter === "banned" && !user.banned) return false;
      if (filter !== "all" && filter !== "banned" && !user.sources.includes(filter)) return false;
      if (!needle) return true;
      return (
        user.user_id.includes(needle) ||
        (user.username || "").toLowerCase().includes(needle) ||
        (user.display_name || "").toLowerCase().includes(needle) ||
        user.roles.some((r) => r.label.toLowerCase().includes(needle)) ||
        user.guild_admin_of.some((g) => g.guild_name.toLowerCase().includes(needle))
      );
    });
  }, [users, query, filter]);

  if (loading) {
    return (
      <div className="glass border border-white/5 rounded-[2rem] p-16 flex items-center justify-center">
        <Loader2 className="h-6 w-6 text-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {[
          { label: "Authorised", value: summary?.authorised_count ?? 0, icon: LogIn, color: "text-primary" },
          { label: "Bot owners", value: summary?.owner_count ?? 0, icon: Crown, color: "text-amber-400" },
          { label: "Team roles", value: summary?.role_count ?? 0, icon: Shield, color: "text-blue-400" },
          { label: "Discord admins", value: summary?.discord_admin_count ?? 0, icon: ShieldCheck, color: "text-indigo-300" },
          { label: "Banned", value: summary?.banned_count ?? 0, icon: Ban, color: "text-rose-400" },
        ].map((card) => (
          <div key={card.label} className="glass border border-white/5 rounded-3xl p-5">
            <card.icon className={cn("h-5 w-5 mb-3", card.color)} />
            <p className="text-3xl font-black text-white">{card.value}</p>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Ban somebody who never signed in */}
      <div className="glass border border-white/5 rounded-[2rem] p-6 space-y-4">
        <div className="flex items-center gap-3">
          <UserX className="h-5 w-5 text-rose-400" />
          <h3 className="font-black text-white">Ban by user ID</h3>
        </div>
        <p className="text-sm text-slate-400">
          Works for people who have never signed in yet. A ban blocks the sign-in itself,
          the dashboard pages and every API call — even with Manage Server on Discord.
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          <input
            value={manualId}
            onChange={(e) => setManualId(e.target.value)}
            placeholder="Discord user ID"
            className="bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <input
            value={manualReason}
            onChange={(e) => setManualReason(e.target.value)}
            placeholder="Reason (optional)"
            className="lg:col-span-2 bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <Select value={manualDuration} onValueChange={setManualDuration} options={DURATIONS} />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={manualRevokeRoles}
              onChange={(e) => setManualRevokeRoles(e.target.checked)}
              className="h-4 w-4 rounded accent-primary"
            />
            Also remove all their dashboard roles
          </label>
          <button
            onClick={() =>
              submitBan(manualId, manualReason, manualDuration, manualRevokeRoles, () => {
                setManualId("");
                setManualReason("");
                setManualDuration("0");
              })
            }
            disabled={busy || !manualId.trim()}
            className="px-6 py-3 bg-rose-500/90 hover:bg-rose-500 rounded-2xl font-black uppercase tracking-widest text-xs disabled:opacity-40"
          >
            <Ban className="h-4 w-4 inline mr-2" />
            Ban
          </button>
        </div>
      </div>

      {/* Search and filter */}
      <div className="glass border border-white/5 rounded-[2rem] p-6 flex flex-col lg:flex-row gap-4 lg:items-center">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, ID, role or server"
            className="w-full bg-white/[0.03] border border-white/5 rounded-2xl pl-11 pr-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="w-full lg:w-56">
          <Select value={filter} onValueChange={setFilter} options={FILTERS} />
        </div>
        <button
          onClick={() => setShowDiscordAdmins(!showDiscordAdmins)}
          title="Also list people who merely have Manage Server somewhere, without ever signing in here"
          className={cn(
            "px-5 py-3 rounded-2xl text-sm font-bold border transition-all whitespace-nowrap",
            showDiscordAdmins
              ? "bg-indigo-500/15 border-indigo-500/30 text-indigo-300"
              : "bg-white/[0.03] border-white/5 text-slate-300 hover:bg-white/[0.06]"
          )}
        >
          <ShieldCheck className="h-4 w-4 inline mr-2" />
          Discord admins
        </button>
        <button
          onClick={() => load()}
          disabled={busy}
          className="px-5 py-3 bg-white/[0.03] border border-white/5 rounded-2xl text-sm font-bold text-slate-300 hover:bg-white/[0.06] disabled:opacity-40"
        >
          <RefreshCw className="h-4 w-4 inline mr-2" />
          Refresh
        </button>
      </div>

      {/* List */}
      <div className="space-y-3">
        {visible.length === 0 && (
          <div className="glass border border-white/5 rounded-[2rem] p-12 text-center text-slate-500">
            {users.length === 0
              ? "Nobody has authorised the bot through this dashboard yet. People appear here the moment they sign in with Discord."
              : "Nobody matches this filter."}
          </div>
        )}

        {visible.map((user) => {
          const open = expanded === user.user_id;
          const isSelf = user.user_id === currentUserId;

          return (
            <div
              key={user.user_id}
              className={cn(
                "glass border rounded-[2rem] overflow-hidden transition-all",
                user.banned ? "border-rose-500/30 bg-rose-500/[0.03]" : "border-white/5"
              )}
            >
              <div className="p-5 flex flex-col lg:flex-row lg:items-center gap-4">
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  {user.avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={user.avatar} alt="" className="h-12 w-12 rounded-2xl border border-white/10" />
                  ) : (
                    <div className="h-12 w-12 rounded-2xl bg-slate-800 flex items-center justify-center">
                      <Users className="h-5 w-5 text-slate-500" />
                    </div>
                  )}

                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-black text-white truncate">
                        {user.display_name || user.username || "Unknown user"}
                      </p>
                      {isSelf && (
                        <span className="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
                          You
                        </span>
                      )}
                      {user.banned && (
                        <span className="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30">
                          Banned
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => copyId(user.user_id)}
                      className="text-xs text-slate-500 hover:text-slate-300 font-mono flex items-center gap-1.5 mt-0.5"
                    >
                      {user.user_id}
                      <Copy className="h-3 w-3" />
                    </button>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {user.sources.map((source) => (
                    <SourceBadge key={source} source={source} />
                  ))}
                </div>

                <div className="flex items-center gap-4 text-xs text-slate-500 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5" />
                    {timeAgo(user.last_seen)}
                  </span>
                  {user.login_count > 0 && <span>{user.login_count}× signed in</span>}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setExpanded(open ? null : user.user_id)}
                    className="px-4 py-2 rounded-xl bg-white/[0.03] border border-white/5 text-xs font-bold text-slate-300 hover:bg-white/[0.06]"
                  >
                    {open ? "Less" : "Details"}
                  </button>

                  {user.banned ? (
                    <button
                      onClick={() => unban(user)}
                      disabled={busy}
                      className="px-4 py-2 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-xs font-black uppercase tracking-wider text-emerald-400 hover:bg-emerald-500/25 disabled:opacity-40"
                    >
                      <Check className="h-3.5 w-3.5 inline mr-1.5" />
                      Unban
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        setBanTarget(user);
                        setBanReason("");
                        setBanDuration("0");
                        setBanRevokeRoles(true);
                      }}
                      disabled={busy || isSelf || user.is_owner}
                      title={
                        isSelf ? "You cannot ban yourself"
                        : user.is_owner ? "Owners cannot be banned — remove their owner access first"
                        : "Ban from the dashboard"
                      }
                      className="px-4 py-2 rounded-xl bg-rose-500/10 border border-rose-500/25 text-xs font-black uppercase tracking-wider text-rose-400 hover:bg-rose-500/20 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      <Ban className="h-3.5 w-3.5 inline mr-1.5" />
                      Ban
                    </button>
                  )}
                </div>
              </div>

              {open && (
                <div className="border-t border-white/5 p-6 bg-white/[0.01] space-y-5">
                  {user.banned && user.ban && (
                    <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/25 space-y-1">
                      <p className="text-sm font-bold text-rose-300">
                        Banned {timeAgo(user.ban.banned_at)}
                        {user.ban.expires_at
                          ? ` — expires ${new Date(user.ban.expires_at * 1000).toLocaleString()}`
                          : " — permanent"}
                      </p>
                      {user.ban.reason && <p className="text-sm text-rose-200/80">Reason: {user.ban.reason}</p>}
                      {user.ban.banned_by && (
                        <p className="text-xs text-rose-200/60 font-mono">by {user.ban.banned_by}</p>
                      )}
                    </div>
                  )}

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">
                        Dashboard roles
                      </p>
                      {user.roles.length === 0 ? (
                        <p className="text-sm text-slate-500">None</p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {user.roles.map((role) => (
                            <span
                              key={role.key}
                              className="px-3 py-1.5 rounded-xl text-xs font-bold border"
                              style={{
                                color: role.color,
                                borderColor: `${role.color}40`,
                                backgroundColor: `${role.color}14`,
                              }}
                            >
                              {role.label}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="flex gap-4 mt-3 text-xs text-slate-500">
                        <span>Permissions: {user.permission_count}</span>
                        <span>Rank: {user.highest_rank}</span>
                      </div>
                    </div>

                    <div>
                      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">
                        Discord admin on
                      </p>
                      {user.guild_admin_of.length === 0 ? (
                        <p className="text-sm text-slate-500">No server</p>
                      ) : (
                        <ul className="space-y-1.5">
                          {user.guild_admin_of.slice(0, 8).map((guild) => (
                            <li key={guild.guild_id} className="text-sm text-slate-300 flex items-center gap-2">
                              {guild.is_guild_owner ? (
                                <Crown className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                              ) : (
                                <ShieldCheck className="h-3.5 w-3.5 text-indigo-300 shrink-0" />
                              )}
                              <span className="truncate">{guild.guild_name}</span>
                            </li>
                          ))}
                          {user.guild_admin_of.length > 8 && (
                            <li className="text-xs text-slate-500">
                              +{user.guild_admin_of.length - 8} more
                            </li>
                          )}
                        </ul>
                      )}
                    </div>

                    <div>
                      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">
                        Activity
                      </p>
                      <dl className="space-y-1.5 text-sm">
                        <div className="flex justify-between gap-4">
                          <dt className="text-slate-500">First sign-in</dt>
                          <dd className="text-slate-300">{timeAgo(user.first_seen)}</dd>
                        </div>
                        <div className="flex justify-between gap-4">
                          <dt className="text-slate-500">Last seen</dt>
                          <dd className="text-slate-300">{timeAgo(user.last_seen)}</dd>
                        </div>
                        <div className="flex justify-between gap-4">
                          <dt className="text-slate-500">Sign-ins</dt>
                          <dd className="text-slate-300">{user.login_count}</dd>
                        </div>
                      </dl>
                      {user.login_count > 0 && (
                        <button
                          onClick={() => forget(user)}
                          disabled={busy}
                          className="mt-4 text-xs text-slate-500 hover:text-rose-400 flex items-center gap-1.5"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete login record
                        </button>
                      )}
                    </div>
                  </div>

                  {user.is_owner && (
                    <div className="flex gap-3 p-4 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-sm text-amber-200/90">
                      <Crown className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                      This person is an owner or dashboard admin and cannot be banned. Remove
                      that access in the Access tab first.
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Ban dialog */}
      {banTarget && (
        <div className="fixed inset-0 z-[60] overflow-y-auto bg-black/70 backdrop-blur-sm p-4 sm:p-6">
          <div className="w-full max-w-lg mx-auto my-8 glass border border-white/10 rounded-[2rem] overflow-hidden">
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-2xl bg-rose-500/15 border border-rose-500/25 flex items-center justify-center">
                  <Ban className="h-5 w-5 text-rose-400" />
                </div>
                <div>
                  <h3 className="font-black text-white">Ban from dashboard</h3>
                  <p className="text-xs text-slate-500 font-mono">{banTarget.user_id}</p>
                </div>
              </div>
              <button onClick={closeBanDialog} className="text-slate-500 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <p className="text-sm text-slate-400">
                <span className="text-white font-bold">
                  {banTarget.display_name || banTarget.username || banTarget.user_id}
                </span>{" "}
                loses access immediately: the sign-in is refused, open sessions are cut off on the
                next request.
              </p>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">Reason</span>
                <input
                  value={banReason}
                  onChange={(e) => setBanReason(e.target.value)}
                  placeholder="Shown in the audit log"
                  className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">Duration</span>
                <Select value={banDuration} onValueChange={setBanDuration} options={DURATIONS} />
              </label>

              <label className="flex items-center gap-3 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={banRevokeRoles}
                  onChange={(e) => setBanRevokeRoles(e.target.checked)}
                  className="h-4 w-4 rounded accent-primary"
                />
                Also remove all their dashboard roles
              </label>

              {banTarget.guild_admin_of.length > 0 && (
                <div className="flex gap-3 p-4 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-xs text-amber-200/90">
                  <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                  This person is a Discord admin on {banTarget.guild_admin_of.length} server(s).
                  The ban blocks the dashboard, not their rights inside Discord itself.
                </div>
              )}
            </div>

            <div className="p-6 border-t border-white/5 flex gap-3">
              <button
                onClick={closeBanDialog}
                className="flex-1 py-3 rounded-2xl bg-white/[0.03] border border-white/5 text-sm font-bold text-slate-300 hover:bg-white/[0.06]"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  banTarget &&
                  submitBan(
                    banTarget.user_id,
                    banReason,
                    banDuration,
                    banRevokeRoles,
                    () => setBanTarget(null),
                  )
                }
                disabled={busy}
                className="flex-1 py-3 rounded-2xl bg-rose-500/90 hover:bg-rose-500 text-sm font-black uppercase tracking-widest disabled:opacity-40"
              >
                {busy ? <Loader2 className="h-4 w-4 inline animate-spin" /> : "Ban now"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Not a save bar in the usual sense -- there is nothing to
          "save" until the ban is sent -- but the same refusal, so a
          half-filled ban form is not thrown away by a stray click. */}
      <StickySaveBar
        id="banbyid-save-bar"
        count={manualDirty}
        busy={busy}
        shake={manualGuard.shake}
        onDiscard={() => {
          setManualId("");
          setManualReason("");
          setManualDuration("0");
        }}
        onSave={() =>
          submitBan(manualId, manualReason, manualDuration, manualRevokeRoles, () => {
            setManualId("");
            setManualReason("");
            setManualDuration("0");
          })
        }
      />
    </div>
  );
}
