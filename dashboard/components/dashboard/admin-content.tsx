/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║           © 2026 University Bot Devs — All Rights Reserved       ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Shield, Users, Server, Activity, Database, Cpu, Globe, Lock, Settings,
  RefreshCw, Ban, UserX, Clock, VolumeX, Send, Megaphone, Wrench, AlertTriangle,
  CheckCircle2, UserRoundCog, UserPlus, UserMinus, Info, Eraser, Crown, Palette,
  Eye, AtSign, Hash, Volume2, FolderPlus, Pencil, Trash2, Copy, Unlock, Timer,
  MessageSquareX, Bell, BellOff, SearchCheck, Bot, UserCog, Webhook, Link, ScrollText
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { AdminStats, AdminConfig } from "@/types/api";
import { toast } from "sonner";

type TabId = "members" | "roles" | "channels" | "server" | "scans" | "broadcast" | "system";
type MemberAction = "ban" | "kick" | "mute" | "unmute";

type QuickAction = {
  action: string;
  label: string;
  desc: string;
  icon: any;
  tab: Exclude<TabId, "members" | "broadcast" | "system"> | "members";
  fields?: Array<"user_id" | "role_id" | "channel_id" | "name" | "color" | "nickname" | "amount" | "seconds">;
};

const tabs: Array<{ id: TabId; label: string; icon: any }> = [
  { id: "members", label: "Members", icon: Users },
  { id: "roles", label: "Roles", icon: Crown },
  { id: "channels", label: "Channels", icon: Hash },
  { id: "server", label: "Server", icon: Server },
  { id: "scans", label: "Scans", icon: SearchCheck },
  { id: "broadcast", label: "Broadcast", icon: Megaphone },
  { id: "system", label: "System", icon: Wrench },
];

const memberActions: Array<{ action: MemberAction; label: string; desc: string; icon: any }> = [
  { action: "mute", label: "Mute", desc: "Timeout a member for a selected duration.", icon: Clock },
  { action: "unmute", label: "Unmute", desc: "Remove a member timeout.", icon: VolumeX },
  { action: "kick", label: "Kick", desc: "Remove a member from the server.", icon: UserX },
  { action: "ban", label: "Ban", desc: "Ban a user from the server.", icon: Ban },
];

const quickActions: QuickAction[] = [
  // Member extras
  { tab: "members", action: "nickname", label: "Set Nickname", desc: "Change a member nickname.", icon: UserRoundCog, fields: ["user_id", "nickname"] },
  { tab: "members", action: "clear_nickname", label: "Clear Nickname", desc: "Reset a member nickname.", icon: Eraser, fields: ["user_id"] },
  { tab: "members", action: "add_role", label: "Add Role", desc: "Add a role to a member.", icon: UserPlus, fields: ["user_id", "role_id"] },
  { tab: "members", action: "remove_role", label: "Remove Role", desc: "Remove a role from a member.", icon: UserMinus, fields: ["user_id", "role_id"] },
  { tab: "members", action: "member_info", label: "Member Info", desc: "Show cached member info.", icon: Info, fields: ["user_id"] },

  // Roles
  { tab: "roles", action: "create_role", label: "Create Role", desc: "Create a new role with color.", icon: Crown, fields: ["name", "color"] },
  { tab: "roles", action: "delete_role", label: "Delete Role", desc: "Delete a role by ID.", icon: Trash2, fields: ["role_id"] },
  { tab: "roles", action: "rename_role", label: "Rename Role", desc: "Rename a selected role.", icon: Pencil, fields: ["role_id", "name"] },
  { tab: "roles", action: "color_role", label: "Change Role Color", desc: "Set a role color using hex.", icon: Palette, fields: ["role_id", "color"] },
  { tab: "roles", action: "toggle_role_hoist", label: "Toggle Role Hoist", desc: "Show/hide role separately.", icon: Eye, fields: ["role_id"] },
  { tab: "roles", action: "toggle_role_mentionable", label: "Toggle Mentionable", desc: "Allow/disallow role mentions.", icon: AtSign, fields: ["role_id"] },

  // Channels
  { tab: "channels", action: "create_text_channel", label: "Create Text Channel", desc: "Create a new text channel.", icon: Hash, fields: ["name"] },
  { tab: "channels", action: "create_voice_channel", label: "Create Voice Channel", desc: "Create a new voice channel.", icon: Volume2, fields: ["name"] },
  { tab: "channels", action: "create_category", label: "Create Category", desc: "Create a new category.", icon: FolderPlus, fields: ["name"] },
  { tab: "channels", action: "rename_channel", label: "Rename Channel", desc: "Rename a channel by ID.", icon: Pencil, fields: ["channel_id", "name"] },
  { tab: "channels", action: "delete_channel", label: "Delete Channel", desc: "Delete a channel by ID.", icon: Trash2, fields: ["channel_id"] },
  { tab: "channels", action: "clone_channel", label: "Clone Channel", desc: "Clone a channel and permissions.", icon: Copy, fields: ["channel_id"] },
  { tab: "channels", action: "lock_channel", label: "Lock Channel", desc: "Disable @everyone sending messages.", icon: Lock, fields: ["channel_id"] },
  { tab: "channels", action: "unlock_channel", label: "Unlock Channel", desc: "Restore @everyone send messages.", icon: Unlock, fields: ["channel_id"] },
  { tab: "channels", action: "slowmode", label: "Set Slowmode", desc: "Set slowmode seconds.", icon: Timer, fields: ["channel_id", "seconds"] },
  { tab: "channels", action: "purge", label: "Purge Messages", desc: "Delete up to 100 recent messages.", icon: MessageSquareX, fields: ["channel_id", "amount"] },

  // Server
  { tab: "server", action: "server_name", label: "Rename Server", desc: "Change server name.", icon: Pencil, fields: ["name"] },
  { tab: "server", action: "verification_level_low", label: "Verification Low", desc: "Set verification level to low.", icon: Shield },
  { tab: "server", action: "verification_level_medium", label: "Verification Medium", desc: "Set verification level to medium.", icon: Shield },
  { tab: "server", action: "default_notifications_mentions", label: "Notifications Mentions", desc: "Default notifications: only mentions.", icon: BellOff },
  { tab: "server", action: "default_notifications_all", label: "Notifications All", desc: "Default notifications: all messages.", icon: Bell },

  // Scans
  { tab: "scans", action: "scan_admin_roles", label: "Scan Admin Roles", desc: "List roles with administrator.", icon: Crown },
  { tab: "scans", action: "scan_dangerous_roles", label: "Scan Dangerous Roles", desc: "List roles with risky permissions.", icon: AlertTriangle },
  { tab: "scans", action: "list_bots", label: "List Bots", desc: "List cached bots in the guild.", icon: Bot },
  { tab: "scans", action: "list_staff", label: "List Staff", desc: "List members with staff-like permissions.", icon: UserCog },
  { tab: "scans", action: "server_stats", label: "Server Stats", desc: "Show member/role/channel counts.", icon: Activity },
  { tab: "scans", action: "scan_public_channels", label: "Public Channels", desc: "List public text channels.", icon: Hash },
  { tab: "scans", action: "scan_webhooks", label: "Scan Webhooks", desc: "Find webhooks in text channels.", icon: Webhook },
  { tab: "scans", action: "scan_invites", label: "Scan Invites", desc: "List active invite codes.", icon: Link },
  { tab: "scans", action: "audit_summary", label: "Audit Summary", desc: "Show recent audit log entries.", icon: ScrollText },
];

export function AdminContent() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState("");
  const [activeTab, setActiveTab] = useState<TabId>("members");
  const [result, setResult] = useState("");

  const [guildId, setGuildId] = useState("");
  const [userId, setUserId] = useState("");
  const [roleId, setRoleId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [name, setName] = useState("");
  const [color, setColor] = useState("3b82f6");
  const [nickname, setNickname] = useState("");
  const [amount, setAmount] = useState("10");
  const [seconds, setSeconds] = useState("5");
  const [duration, setDuration] = useState("60");
  const [reason, setReason] = useState("Dashboard admin action");
  const [memberAction, setMemberAction] = useState<MemberAction>("mute");

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [statsData, configData] = await Promise.all([api.getAdminStats(), api.getAdminConfig()]);
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

  const statItems = [
    { name: "Gesamte Nutzer", value: stats?.total_users || "0", icon: Users, color: "text-blue-500" },
    { name: "Active Servers", value: stats?.active_servers || "0", icon: Server, color: "text-emerald-500" },
    { name: "API Latency", value: stats?.api_latency || "0ms", icon: Activity, color: "text-amber-500" },
    { name: "Database Size", value: stats?.db_size || "0 MB", icon: Database, color: "text-purple-500" },
  ];

  const currentActions = useMemo(() => quickActions.filter((action) => action.tab === activeTab), [activeTab]);

  const basePayload = () => ({
    guild_id: guildId.trim(), user_id: userId.trim(), role_id: roleId.trim(), channel_id: channelId.trim(),
    name: name.trim(), color: color.trim(), nickname: nickname.trim(), amount: Number(amount) || 10,
    seconds: Number(seconds) || 5, duration_minutes: Number(duration) || 60, reason: reason.trim(),
  });

  const validateGuild = () => /^\d{15,25}$/.test(guildId.trim());

  const runMemberModeration = async () => {
    if (!validateGuild()) return toast.error("Please enter a valid Guild ID.");
    if (!/^\d{15,25}$/.test(userId.trim())) return toast.error("Please enter a valid User ID.");
    setSaving(true);
    const promise = api.runAdminMemberAction({ ...basePayload(), action: memberAction });
    toast.promise(promise, { loading: `Running ${memberAction}...`, success: (data) => data.result, error: (err) => err.message || "Action failed." });
    try { const data = await promise; setResult(data.result); } finally { setSaving(false); }
  };

  const runQuickAction = async (action: QuickAction) => {
    if (!validateGuild()) return toast.error("Please enter a valid Guild ID.");
    setSaving(true);
    const promise = api.runAdminQuickAction({ ...basePayload(), action: action.action });
    toast.promise(promise, { loading: `Running ${action.label}...`, success: (data) => data.result, error: (err) => err.message || "Action failed." });
    try { const data = await promise; setResult(data.result); } finally { setSaving(false); }
  };

  const handleToggleMaintenance = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const newStatus = !config.maintenance_mode;
      await api.updateAdminConfig({ maintenance_mode: newStatus });
      setConfig({ ...config, maintenance_mode: newStatus });
      toast.success(`Maintenance mode ${newStatus ? "enabled" : "disabled"}`);
    } catch { toast.error("Failed to update maintenance mode"); } finally { setSaving(false); }
  };

  const handleBroadcast = async () => {
    setSaving(true);
    try {
      await api.updateAdminConfig({ global_notification: notification });
      if (config) setConfig({ ...config, global_notification: notification });
      toast.success("Broadcast message updated");
    } catch { toast.error("Failed to update broadcast message"); } finally { setSaving(false); }
  };

  if (loading) return <div className="flex items-center justify-center min-h-[400px]"><RefreshCw className="h-10 w-10 text-blue-500 animate-spin opacity-20" /></div>;

  const fieldValue = {
    user_id: [userId, setUserId, "User ID"], role_id: [roleId, setRoleId, "Role ID"], channel_id: [channelId, setChannelId, "Channel ID"],
    name: [name, setName, "Name"], color: [color, setColor, "Hex color"], nickname: [nickname, setNickname, "Nickname"],
    amount: [amount, setAmount, "Amount"], seconds: [seconds, setSeconds, "Seconds"],
  } as const;

  return (
    <div className="space-y-10 animate-in fade-in duration-500">
      <div className="relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-3xl blur opacity-10 group-hover:opacity-20 transition duration-1000" />
        <div className="relative bg-[#0b1f3a] border border-white/10 rounded-3xl p-8 lg:p-12 flex flex-col lg:flex-row lg:items-center justify-between gap-8">
          <div className="flex items-center gap-6">
            <div className="h-16 w-16 rounded-2xl bg-blue-500/20 flex items-center justify-center border border-blue-500/30 shadow-2xl shadow-blue-500/20"><Shield className="h-8 w-8 text-blue-500" /></div>
            <div><h1 className="text-4xl font-black text-white tracking-tight font-outfit">Admin Control Panel</h1><p className="text-slate-400 mt-2 font-medium">Action-based tools for moderation, roles, channels, server settings and scans.</p></div>
          </div>
          <button onClick={() => fetchData(true)} className="flex items-center gap-3 bg-blue-500/5 px-6 py-3 rounded-2xl border border-blue-500/10 hover:bg-blue-500/10 transition-all active:scale-95"><RefreshCw className={cn("h-4 w-4 text-blue-500 transition-all", refreshing && "animate-spin")} /><span className="text-xs font-black uppercase tracking-widest text-blue-500">{refreshing ? "Refreshing..." : "Real-time Mode"}</span></button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statItems.map((stat) => <div key={stat.name} className="glass border border-white/5 rounded-3xl p-6 hover:border-white/10 transition-all group"><div className="flex items-center justify-between mb-4"><div className={cn("p-3 rounded-xl bg-white/[0.03] group-hover:scale-110 transition-transform", stat.color)}><stat.icon className="h-6 w-6" /></div><span className="text-[10px] font-black uppercase tracking-widest text-emerald-500 bg-emerald-500/10 px-2 py-1 rounded-lg">Live</span></div><p className="text-slate-500 text-xs font-bold uppercase tracking-widest">{stat.name}</p><h3 className="text-2xl font-black text-white mt-1 font-outfit">{stat.value}</h3></div>)}
      </div>

      <div className="flex flex-wrap gap-3 p-2 bg-[#10233f]/70 border border-slate-800 rounded-3xl">
        {tabs.map((tab) => {
          const active = activeTab === tab.id;
          return <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={cn("flex items-center gap-2 px-5 py-3 rounded-2xl text-sm font-black uppercase tracking-wider transition-all", active ? "bg-primary text-white shadow-lg shadow-primary/20" : "text-slate-400 hover:bg-slate-800/70 hover:text-white")}><tab.icon className="h-4 w-4" />{tab.label}</button>;
        })}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
        <aside className="xl:col-span-1 glass border border-white/5 rounded-[2rem] p-6 space-y-4 h-fit">
          <h3 className="font-black text-white flex items-center gap-2"><SearchCheck className="h-5 w-5 text-primary" /> Action Inputs</h3>
          <label className="block space-y-2"><span className="text-xs font-black uppercase tracking-widest text-slate-500">Guild ID</span><input value={guildId} onChange={(e) => setGuildId(e.target.value)} placeholder="Discord Server ID" className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" /></label>
          {activeTab !== "broadcast" && activeTab !== "system" && (
            <>
              {(["user_id", "role_id", "channel_id", "name", "color", "nickname", "amount", "seconds"] as const).map((field) => {
                const needed = activeTab === "members" || currentActions.some((a) => a.fields?.includes(field));
                if (!needed) return null;
                const [value, setter, placeholder] = fieldValue[field];
                return <label key={field} className="block space-y-2"><span className="text-xs font-black uppercase tracking-widest text-slate-500">{placeholder}</span><input value={value} onChange={(e) => setter(e.target.value)} placeholder={placeholder} className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" /></label>;
              })}
              {activeTab === "members" && <label className="block space-y-2"><span className="text-xs font-black uppercase tracking-widest text-slate-500">Mute duration minutes</span><input value={duration} onChange={(e) => setDuration(e.target.value)} type="number" className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" /></label>}
              <label className="block space-y-2"><span className="text-xs font-black uppercase tracking-widest text-slate-500">Reason</span><textarea value={reason} onChange={(e) => setReason(e.target.value)} className="w-full h-24 bg-white/[0.03] border border-white/5 rounded-2xl p-4 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" /></label>
            </>
          )}
          {result && <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl text-emerald-300 text-sm leading-relaxed">{result}</div>}
        </aside>

        <main className="xl:col-span-3 space-y-6">
          {activeTab === "members" && <section className="space-y-5"><div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">{memberActions.map((card) => { const active = memberAction === card.action; return <button key={card.action} onClick={() => setMemberAction(card.action)} className={cn("text-left p-5 rounded-3xl border transition-all", active ? "bg-primary/10 border-primary/40" : "bg-white/[0.02] border-white/5 hover:border-white/10")}><card.icon className={cn("h-6 w-6 mb-3", active ? "text-primary" : "text-slate-500")} /><p className="font-black text-white">{card.label}</p><p className="text-xs text-slate-500 mt-1">{card.desc}</p></button>; })}</div><button onClick={runMemberModeration} disabled={saving} className="w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-50">Run {memberAction}</button></section>}

          {(activeTab === "members" || activeTab === "roles" || activeTab === "channels" || activeTab === "server" || activeTab === "scans") && (
            <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {currentActions.map((action) => <button key={action.action} onClick={() => runQuickAction(action)} disabled={saving} className="text-left bg-[#10233f] border border-slate-800 rounded-3xl p-6 hover:border-primary/40 hover:bg-primary/5 transition-all disabled:opacity-50"><action.icon className="h-6 w-6 text-primary mb-4" /><h4 className="font-black text-white">{action.label}</h4><p className="text-sm text-slate-500 mt-2">{action.desc}</p>{action.fields?.length ? <p className="text-[10px] uppercase tracking-widest text-slate-600 mt-4">Needs: {action.fields.join(", ")}</p> : null}</button>)}
            </section>
          )}

          {activeTab === "broadcast" && <section className="glass border border-white/5 rounded-[2rem] overflow-hidden max-w-3xl"><div className="p-8 border-b border-white/5 flex items-center gap-4 bg-white/[0.01]"><Megaphone className="h-5 w-5 text-blue-500" /><h3 className="text-lg font-bold text-white">Global Broadcast</h3></div><div className="p-8 space-y-5"><textarea value={notification} onChange={(e) => setNotification(e.target.value)} className="w-full h-40 bg-white/[0.03] border border-white/5 rounded-2xl p-4 text-sm text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500/30" placeholder="Message to display across all dashboards..." /><button onClick={handleBroadcast} disabled={saving} className="w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-50"><Send className="h-4 w-4 inline mr-2" />Broadcast Message</button></div></section>}

          {activeTab === "system" && <section className="grid grid-cols-1 lg:grid-cols-3 gap-8"><div className="lg:col-span-2 glass border border-white/5 rounded-[2rem] overflow-hidden"><div className="p-8 border-b border-white/5 flex items-center justify-between bg-white/[0.01]"><div className="flex items-center gap-4"><Activity className="h-5 w-5 text-blue-500" /><h3 className="text-lg font-bold text-white">System Nodes Status</h3></div><span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Auto-Polling Active</span></div><div className="p-8 space-y-6">{stats?.nodes.map((node) => { const Icon = node.icon === "Globe" ? Globe : node.icon === "Database" ? Database : node.icon === "Cpu" ? Cpu : Lock; const healthy = node.status === "Healthy"; return <div key={node.name} className="flex items-center justify-between p-4 bg-white/[0.02] rounded-2xl border border-white/5"><div className="flex items-center gap-4"><div className="h-10 w-10 rounded-xl bg-slate-800 flex items-center justify-center"><Icon className="h-5 w-5 text-slate-400" /></div><div><h4 className="text-sm font-bold text-white">{node.name}</h4><p className="text-[10px] font-black uppercase text-slate-500 tracking-widest">Load: {node.load}</p></div></div><span className={cn("text-[10px] font-bold uppercase px-3 py-1.5 rounded-full border", healthy ? "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" : "text-amber-500 bg-amber-500/10 border-amber-500/20")}>{node.status}</span></div>; })}</div></div><div className="glass border border-white/5 rounded-[2rem] p-8"><Settings className="h-5 w-5 text-indigo-500 mb-4" /><h3 className="text-lg font-bold text-white mb-4">System Controls</h3><button onClick={handleToggleMaintenance} disabled={saving} className={cn("w-full flex items-center justify-between p-4 rounded-2xl border transition-all", config?.maintenance_mode ? "bg-blue-500/10 border-blue-500/30 text-blue-500" : "bg-white/[0.03] border-white/5 text-slate-300 hover:bg-white/[0.05]")}><span className="text-sm font-medium">{config?.maintenance_mode ? "Restricting Access" : "Standard Operations"}</span></button></div></section>}
        </main>
      </div>

      <div className="glass border border-white/5 rounded-3xl p-5 flex gap-3 text-sm text-slate-400"><AlertTriangle className="h-5 w-5 text-amber-500 shrink-0" />Actions execute immediately. The bot can only affect members/roles/channels below its own highest role and only when it has the required Discord permissions.</div>
    </div>
  );
}
