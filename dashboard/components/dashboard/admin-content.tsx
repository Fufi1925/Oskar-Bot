/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║           © 2026 University Bot Devs — All Rights Reserved       ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

import React, { useState, useEffect } from "react";
import {
  Shield, Users, Server, Activity, Database, Cpu, Globe, Lock, Settings,
  RefreshCw, Ban, UserX, Clock, VolumeX, Send, Megaphone, Wrench, Search,
  AlertTriangle, CheckCircle2
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { AdminStats, AdminConfig } from "@/types/api";
import { toast } from "sonner";

const tabs = [
  { id: "members", label: "Member Actions", icon: Users },
  { id: "broadcast", label: "Broadcast", icon: Megaphone },
  { id: "system", label: "System", icon: Wrench },
] as const;

type TabId = typeof tabs[number]["id"];

type MemberAction = "ban" | "kick" | "mute" | "unmute";

export function AdminContent() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState("");
  const [activeTab, setActiveTab] = useState<TabId>("members");

  const [guildId, setGuildId] = useState("");
  const [userId, setUserId] = useState("");
  const [memberAction, setMemberAction] = useState<MemberAction>("mute");
  const [duration, setDuration] = useState("60");
  const [reason, setReason] = useState("Dashboard moderation action");

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [statsData, configData] = await Promise.all([
        api.getAdminStats(),
        api.getAdminConfig(),
      ]);
      setStats(statsData);
      setConfig(configData);
      setNotification(configData.global_notification || "");
    } catch (err) {
      console.error("Failed to fetch admin data:", err);
      toast.error("Failed to load real-time data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(true), 30000);
    return () => clearInterval(interval);
  }, []);

  const handleToggleMaintenance = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const newStatus = !config.maintenance_mode;
      await api.updateAdminConfig({ maintenance_mode: newStatus });
      setConfig({ ...config, maintenance_mode: newStatus });
      toast.success(`Maintenance mode ${newStatus ? "enabled" : "disabled"}`);
    } catch {
      toast.error("Failed to update maintenance mode");
    } finally {
      setSaving(false);
    }
  };

  const handleBroadcast = async () => {
    setSaving(true);
    try {
      await api.updateAdminConfig({ global_notification: notification });
      if (config) setConfig({ ...config, global_notification: notification });
      toast.success("Broadcast message updated");
    } catch {
      toast.error("Failed to update broadcast message");
    } finally {
      setSaving(false);
    }
  };

  const runMemberAction = async () => {
    if (!/^\d{15,25}$/.test(guildId.trim())) return toast.error("Please enter a valid Guild ID.");
    if (!/^\d{15,25}$/.test(userId.trim())) return toast.error("Please enter a valid User ID.");
    if (!reason.trim()) return toast.error("Please enter a reason.");

    setSaving(true);
    const promise = api.runAdminMemberAction({
      guild_id: guildId.trim(),
      user_id: userId.trim(),
      action: memberAction,
      duration_minutes: Number(duration) || 60,
      reason: reason.trim(),
    });

    toast.promise(promise, {
      loading: `Running ${memberAction}...`,
      success: (data) => data.result || "Action completed.",
      error: (err) => err.message || "Action failed.",
    });

    try {
      await promise;
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw className="h-10 w-10 text-blue-500 animate-spin opacity-20" />
      </div>
    );
  }

  const statItems = [
    { name: "Gesamte Nutzer", value: stats?.total_users || "0", icon: Users, color: "text-blue-500" },
    { name: "Active Servers", value: stats?.active_servers || "0", icon: Server, color: "text-emerald-500" },
    { name: "API Latency", value: stats?.api_latency || "0ms", icon: Activity, color: "text-amber-500" },
    { name: "Database Size", value: stats?.db_size || "0 MB", icon: Database, color: "text-purple-500" },
  ];

  const actionCards: Array<{ action: MemberAction; label: string; desc: string; icon: any }> = [
    { action: "mute", label: "Mute", desc: "Timeout a member for a selected duration.", icon: Clock },
    { action: "unmute", label: "Unmute", desc: "Remove a member timeout.", icon: VolumeX },
    { action: "kick", label: "Kick", desc: "Remove a member from the server.", icon: UserX },
    { action: "ban", label: "Ban", desc: "Ban a user from the server.", icon: Ban },
  ];

  return (
    <div className="space-y-10 animate-in fade-in duration-500">
      <div className="relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-3xl blur opacity-10 group-hover:opacity-20 transition duration-1000" />
        <div className="relative bg-[#0b1f3a] border border-white/10 rounded-3xl p-8 lg:p-12 flex flex-col lg:flex-row lg:items-center justify-between gap-8">
          <div className="flex items-center gap-6">
            <div className="h-16 w-16 rounded-2xl bg-blue-500/20 flex items-center justify-center border border-blue-500/30 shadow-2xl shadow-blue-500/20">
              <Shield className="h-8 w-8 text-blue-500" />
            </div>
            <div>
              <h1 className="text-4xl font-black text-white tracking-tight font-outfit">Admin Control Panel</h1>
              <p className="text-slate-400 mt-2 font-medium">Simple admin tools for moderation, broadcasts and system control.</p>
            </div>
          </div>
          <button onClick={() => fetchData(true)} className="flex items-center gap-3 bg-blue-500/5 px-6 py-3 rounded-2xl border border-blue-500/10 hover:bg-blue-500/10 transition-all active:scale-95">
            <RefreshCw className={cn("h-4 w-4 text-blue-500 transition-all", refreshing && "animate-spin")} />
            <span className="text-xs font-black uppercase tracking-widest text-blue-500">{refreshing ? "Refreshing..." : "Real-time Mode"}</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statItems.map((stat) => (
          <div key={stat.name} className="glass border border-white/5 rounded-3xl p-6 hover:border-white/10 transition-all group">
            <div className="flex items-center justify-between mb-4">
              <div className={cn("p-3 rounded-xl bg-white/[0.03] group-hover:scale-110 transition-transform", stat.color)}><stat.icon className="h-6 w-6" /></div>
              <span className="text-[10px] font-black uppercase tracking-widest text-emerald-500 bg-emerald-500/10 px-2 py-1 rounded-lg">Live</span>
            </div>
            <p className="text-slate-500 text-xs font-bold uppercase tracking-widest">{stat.name}</p>
            <h3 className="text-2xl font-black text-white mt-1 font-outfit">{stat.value}</h3>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-3 p-2 bg-[#10233f]/70 border border-slate-800 rounded-3xl">
        {tabs.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={cn("flex items-center gap-2 px-5 py-3 rounded-2xl text-sm font-black uppercase tracking-wider transition-all", active ? "bg-primary text-white shadow-lg shadow-primary/20" : "text-slate-400 hover:bg-slate-800/70 hover:text-white")}>
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab === "members" && (
        <section className="grid grid-cols-1 xl:grid-cols-3 gap-8">
          <div className="xl:col-span-2 glass border border-white/5 rounded-[2.5rem] overflow-hidden">
            <div className="p-8 border-b border-white/5 flex items-center gap-4 bg-white/[0.01]">
              <Users className="h-5 w-5 text-blue-500" />
              <div>
                <h3 className="text-lg font-bold text-white">Member Moderation</h3>
                <p className="text-sm text-slate-500">Ban, kick, mute or unmute a member by Guild ID and User ID.</p>
              </div>
            </div>
            <div className="p-8 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-500">Guild ID</span>
                  <input value={guildId} onChange={(e) => setGuildId(e.target.value)} placeholder="Discord Server ID" className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-500">User ID</span>
                  <input value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="Discord User ID" className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" />
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {actionCards.map((card) => {
                  const active = memberAction === card.action;
                  return (
                    <button key={card.action} onClick={() => setMemberAction(card.action)} className={cn("text-left p-5 rounded-3xl border transition-all", active ? "bg-primary/10 border-primary/40" : "bg-white/[0.02] border-white/5 hover:border-white/10")}>
                      <card.icon className={cn("h-6 w-6 mb-3", active ? "text-primary" : "text-slate-500")} />
                      <p className="font-black text-white">{card.label}</p>
                      <p className="text-xs text-slate-500 mt-1">{card.desc}</p>
                    </button>
                  );
                })}
              </div>

              {memberAction === "mute" && (
                <label className="space-y-2 block">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-500">Duration in minutes</span>
                  <input value={duration} onChange={(e) => setDuration(e.target.value)} type="number" min={1} max={40320} className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" />
                </label>
              )}

              <label className="space-y-2 block">
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">Reason</span>
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} className="w-full h-28 bg-white/[0.03] border border-white/5 rounded-2xl p-4 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" />
              </label>

              <button onClick={runMemberAction} disabled={saving} className="w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50">
                {saving ? "Processing..." : `Run ${memberAction}`}
              </button>
            </div>
          </div>

          <div className="glass border border-white/5 rounded-[2.5rem] p-8 space-y-5">
            <div className="flex items-center gap-3"><AlertTriangle className="h-5 w-5 text-amber-500" /><h3 className="font-bold text-white">Important</h3></div>
            <p className="text-sm text-slate-400 leading-relaxed">The bot can only moderate members below its highest role. For ban/kick/mute, make sure the bot has the correct Discord permissions.</p>
            <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm flex gap-3"><CheckCircle2 className="h-5 w-5 shrink-0" />Actions are executed immediately after clicking the button.</div>
          </div>
        </section>
      )}

      {activeTab === "broadcast" && (
        <section className="glass border border-white/5 rounded-[2.5rem] overflow-hidden max-w-3xl">
          <div className="p-8 border-b border-white/5 flex items-center gap-4 bg-white/[0.01]"><Megaphone className="h-5 w-5 text-blue-500" /><h3 className="text-lg font-bold text-white">Global Broadcast</h3></div>
          <div className="p-8 space-y-5">
            <textarea value={notification} onChange={(e) => setNotification(e.target.value)} className="w-full h-40 bg-white/[0.03] border border-white/5 rounded-2xl p-4 text-sm text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500/30 transition-all placeholder:text-slate-600" placeholder="Message to display across all dashboards..." />
            <button onClick={handleBroadcast} disabled={saving} className="w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50">
              <Send className="h-4 w-4 inline mr-2" />{saving ? "Processing..." : "Broadcast Message"}
            </button>
          </div>
        </section>
      )}

      {activeTab === "system" && (
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 glass border border-white/5 rounded-[2.5rem] overflow-hidden">
            <div className="p-8 border-b border-white/5 flex items-center justify-between bg-white/[0.01]">
              <div className="flex items-center gap-4"><Activity className="h-5 w-5 text-blue-500" /><h3 className="text-lg font-bold text-white">System Nodes Status</h3></div>
              <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Auto-Polling Active</span>
            </div>
            <div className="p-8 space-y-6">
              {stats?.nodes.map((node) => {
                const Icon = node.icon === "Globe" ? Globe : node.icon === "Database" ? Database : node.icon === "Cpu" ? Cpu : Lock;
                const isHealthy = node.status === "Healthy";
                return (
                  <div key={node.name} className="flex items-center justify-between p-4 bg-white/[0.02] rounded-2xl border border-white/5 group hover:bg-white/[0.04] transition-all">
                    <div className="flex items-center gap-4"><div className="h-10 w-10 rounded-xl bg-slate-800 flex items-center justify-center"><Icon className="h-5 w-5 text-slate-400" /></div><div><h4 className="text-sm font-bold text-white">{node.name}</h4><p className="text-[10px] font-black uppercase text-slate-500 tracking-widest">Load: {node.load}</p></div></div>
                    <div className={cn("flex items-center gap-2 px-3 py-1.5 rounded-full border", isHealthy ? "bg-emerald-500/10 border-emerald-500/20" : "bg-amber-500/10 border-amber-500/20")}><div className={cn("h-1.5 w-1.5 rounded-full", isHealthy ? "bg-emerald-500" : "bg-amber-500")} /><span className={cn("text-[10px] font-bold uppercase", isHealthy ? "text-emerald-500" : "text-amber-500")}>{node.status}</span></div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="glass border border-white/5 rounded-[2.5rem] overflow-hidden flex flex-col">
            <div className="p-8 border-b border-white/5 flex items-center gap-4 bg-white/[0.01]"><Settings className="h-5 w-5 text-indigo-500" /><h3 className="text-lg font-bold text-white">System Controls</h3></div>
            <div className="p-8 flex-1 space-y-6">
              <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 pl-1">Maintenance Mode</label>
              <button onClick={handleToggleMaintenance} disabled={saving} className={cn("w-full flex items-center justify-between p-4 rounded-2xl border transition-all", config?.maintenance_mode ? "bg-blue-500/10 border-blue-500/30 text-blue-500" : "bg-white/[0.03] border-white/5 text-slate-300 hover:bg-white/[0.05]")}> 
                <span className="text-sm font-medium">{config?.maintenance_mode ? "Restricting Access" : "Standard Operations"}</span>
                <div className={cn("h-6 w-11 rounded-full relative transition-colors duration-300", config?.maintenance_mode ? "bg-blue-500" : "bg-slate-700")}><div className={cn("absolute top-1 h-4 w-4 bg-white rounded-full transition-all duration-300 shadow-sm", config?.maintenance_mode ? "left-6" : "left-1")} /></div>
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
