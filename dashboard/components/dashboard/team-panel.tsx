"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Check, Loader2, Search, Shield, Trash2, UserPlus, Users, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface RoleInfo {
  key: string;
  label: string;
  category: string;
  description: string;
  rank: number;
  color: string;
  permissions: string[];
  permission_count: number;
  dangerous_count: number;
  holders: number;
}

interface MemberInfo {
  user_id: string;
  username: string | null;
  avatar: string | null;
  highest_rank: number;
  permission_count: number;
  roles: Array<{
    key: string;
    label: string;
    color: string;
    guild_ids: string[];
    granted_by: string;
    granted_at: number;
    note: string;
  }>;
}

export function TeamPanel() {
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [members, setMembers] = useState<MemberInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"team" | "roles">("team");
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  // Assign form
  const [userId, setUserId] = useState("");
  const [roleKey, setRoleKey] = useState("");
  const [guildScope, setGuildScope] = useState("");
  const [note, setNote] = useState("");

  const load = async () => {
    try {
      const [roleData, memberData] = await Promise.all([
        api.getTeamRoles(),
        api.getTeamMembers(),
      ]);
      setRoles(roleData.roles || []);
      setCategories(roleData.categories || []);
      setMembers(memberData.members || []);
    } catch (err: any) {
      toast.error(err?.message || "Could not load the team.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const assign = async () => {
    const id = userId.trim();
    if (!/^\d{15,20}$/.test(id)) return toast.error("Please enter a valid Discord user ID.");
    if (!roleKey) return toast.error("Please pick a role.");

    const guildIds = guildScope
      .split(",")
      .map((g) => g.trim())
      .filter((g) => /^\d{17,20}$/.test(g));

    setBusy(true);
    try {
      await api.assignTeamRole(id, roleKey, guildIds, note.trim());
      toast.success("Role assigned.");
      setUserId("");
      setNote("");
      setGuildScope("");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Assignment failed.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string, key: string, label: string) => {
    setBusy(true);
    try {
      await api.revokeTeamRole(id, key);
      toast.success(`${label} removed.`);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not remove the role.");
    } finally {
      setBusy(false);
    }
  };

  const visibleRoles = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return roles.filter((role) => {
      if (activeCategory !== "all" && role.category !== activeCategory) return false;
      if (!needle) return true;
      return (
        role.label.toLowerCase().includes(needle) ||
        role.description.toLowerCase().includes(needle) ||
        role.key.toLowerCase().includes(needle)
      );
    });
  }, [roles, query, activeCategory]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      {/* Header */}
      <div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
              <Users className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h3 className="text-xl font-black text-white">Dashboard Team</h3>
              <p className="text-sm text-slate-400 mt-1">
                {members.length} people · {roles.length} roles available
              </p>
            </div>
          </div>

          <div className="flex gap-2 p-1.5 bg-[#10233f]/70 border border-slate-800 rounded-2xl">
            {(["team", "roles"] as const).map((id) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={cn(
                  "px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-wider transition-all",
                  tab === id ? "bg-primary text-white" : "text-slate-400 hover:text-white"
                )}
              >
                {id === "team" ? "Team" : "Role catalogue"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {tab === "team" && (
        <>
          {/* Assign */}
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-8 border-glow-card">
            <h4 className="font-black text-white flex items-center gap-2 mb-6">
              <UserPlus className="h-5 w-5 text-primary" /> Grant a role
            </h4>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Discord user ID
                </span>
                <input
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  placeholder="123456789012345678"
                  className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Role
                </span>
                <select
                  value={roleKey}
                  onChange={(e) => setRoleKey(e.target.value)}
                  className="w-full appearance-none bg-[#0b1f3a] border border-white/10 rounded-2xl px-4 py-3 pr-9 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2024%2024%22%20stroke%3D%22%2394a3b8%22%20stroke-width%3D%222%22%3E%3Cpath%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20d%3D%22M19%209l-7%207-7-7%22/%3E%3C/svg%3E')] bg-[length:1.1rem] bg-[right_0.6rem_center] bg-no-repeat cursor-pointer"
                >
                  <option value="">Pick a role...</option>
                  {categories.map((category) => (
                    <optgroup key={category} label={category}>
                      {roles
                        .filter((r) => r.category === category)
                        .map((r) => (
                          <option key={r.key} value={r.key}>
                            {r.label} ({r.permission_count} permissions)
                          </option>
                        ))}
                    </optgroup>
                  ))}
                </select>
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Limit to servers <span className="text-slate-600">(optional)</span>
                </span>
                <input
                  value={guildScope}
                  onChange={(e) => setGuildScope(e.target.value)}
                  placeholder="Empty = all servers. Otherwise IDs separated by commas"
                  className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Note <span className="text-slate-600">(optional)</span>
                </span>
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. trial until end of month"
                  className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>
            </div>

            {roleKey && (
              <div className="mt-5 p-4 bg-white/[0.02] border border-white/5 rounded-2xl">
                {(() => {
                  const role = roles.find((r) => r.key === roleKey);
                  if (!role) return null;
                  return (
                    <>
                      <p className="text-sm text-slate-300">{role.description}</p>
                      <div className="flex flex-wrap gap-3 mt-3 text-[10px] font-black uppercase tracking-widest">
                        <span className="text-slate-500">Rank {role.rank}</span>
                        <span className="text-primary">{role.permission_count} permissions</span>
                        {role.dangerous_count > 0 && (
                          <span className="text-amber-400 flex items-center gap-1">
                            <AlertTriangle className="h-3 w-3" />
                            {role.dangerous_count} destructive
                          </span>
                        )}
                      </div>
                    </>
                  );
                })()}
              </div>
            )}

            <button
              onClick={assign}
              disabled={busy}
              className="mt-6 w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-50"
            >
              {busy ? "Working..." : "Grant role"}
            </button>
          </div>

          {/* Members */}
          <div className="space-y-4">
            {members.length === 0 && (
              <p className="text-center text-slate-500 py-12">
                Nobody has a dashboard role yet.
              </p>
            )}

            {members.map((member) => (
              <div
                key={member.user_id}
                className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card"
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex items-center gap-4">
                    {member.avatar ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={member.avatar}
                        alt=""
                        className="h-12 w-12 rounded-2xl border border-white/10"
                      />
                    ) : (
                      <div className="h-12 w-12 rounded-2xl bg-slate-800 flex items-center justify-center">
                        <Users className="h-5 w-5 text-slate-500" />
                      </div>
                    )}
                    <div>
                      <p className="font-black text-white">
                        {member.username || "Unknown user"}
                      </p>
                      <code className="text-[11px] text-slate-500 font-mono">
                        {member.user_id}
                      </code>
                    </div>
                  </div>

                  <div className="text-right">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">
                      Rank {member.highest_rank}
                    </p>
                    <p className="text-xs text-primary font-bold mt-1">
                      {member.permission_count} permissions
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 mt-5">
                  {member.roles.map((role) => (
                    <span
                      key={role.key}
                      className="group inline-flex items-center gap-2 pl-3 pr-2 py-1.5 rounded-xl text-xs font-bold border"
                      style={{
                        color: role.color,
                        borderColor: `${role.color}40`,
                        backgroundColor: `${role.color}15`,
                      }}
                    >
                      {role.label}
                      {role.guild_ids.length > 0 && (
                        <span className="text-[9px] uppercase opacity-70">
                          {role.guild_ids.length} server
                        </span>
                      )}
                      <button
                        onClick={() => revoke(member.user_id, role.key, role.label)}
                        disabled={busy}
                        className="opacity-40 hover:opacity-100 transition-opacity"
                        title="Remove role"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  ))}
                </div>

                {member.roles.some((r) => r.note) && (
                  <p className="text-xs text-slate-500 mt-4">
                    {member.roles.filter((r) => r.note).map((r) => `${r.label}: ${r.note}`).join(" · ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "roles" && (
        <>
          <div className="flex flex-col lg:flex-row gap-4">
            <label className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search roles..."
                className="w-full bg-white/[0.03] border border-white/5 rounded-2xl pl-11 pr-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            {["all", ...categories].map((category) => (
              <button
                key={category}
                onClick={() => setActiveCategory(category)}
                className={cn(
                  "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all",
                  activeCategory === category
                    ? "bg-primary text-white"
                    : "bg-white/[0.03] text-slate-400 hover:text-white hover:bg-white/[0.06]"
                )}
              >
                {category === "all" ? `All (${roles.length})` : category}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {visibleRoles.map((role) => (
              <div
                key={role.key}
                className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 hover:border-white/10 transition-all border-glow-card"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className="h-3 w-3 rounded-full shrink-0"
                        style={{ backgroundColor: role.color }}
                      />
                      <h4 className="font-black text-white">{role.label}</h4>
                      <span className="text-[9px] font-black uppercase tracking-widest text-slate-600 bg-white/[0.04] px-2 py-0.5 rounded-md">
                        {role.category}
                      </span>
                    </div>
                    <p className="text-sm text-slate-400 mt-2">{role.description}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                      Rank
                    </p>
                    <p className="text-lg font-black text-white">{role.rank}</p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 mt-4 text-[10px] font-black uppercase tracking-widest">
                  <span className="text-primary">{role.permission_count} permissions</span>
                  {role.dangerous_count > 0 && (
                    <span className="text-amber-400 flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      {role.dangerous_count} destructive
                    </span>
                  )}
                  {role.holders > 0 && (
                    <span className="text-emerald-400 flex items-center gap-1">
                      <Check className="h-3 w-3" />
                      {role.holders} holder{role.holders === 1 ? "" : "s"}
                    </span>
                  )}
                </div>

                <button
                  onClick={() => setExpanded(expanded === role.key ? null : role.key)}
                  className="mt-4 text-xs font-bold text-slate-500 hover:text-white transition-colors"
                >
                  {expanded === role.key ? "Hide permissions" : "Show permissions"}
                </button>

                {expanded === role.key && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {role.permissions.map((permission) => (
                      <code
                        key={permission}
                        className="text-[10px] font-mono px-2 py-1 rounded-lg bg-white/[0.04] text-slate-400"
                      >
                        {permission}
                      </code>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {visibleRoles.length === 0 && (
            <p className="text-center text-slate-500 py-12">No roles match your filter.</p>
          )}
        </>
      )}
    </section>
  );
}
