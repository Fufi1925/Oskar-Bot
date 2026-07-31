"use client";

import React, { useEffect, useMemo, useState, useRef } from "react";
import {
  Shield, Users, Server, Activity, Database, Cpu, Globe, Lock, Settings,
  RefreshCw, Ban, UserX, Clock, VolumeX, Send, Megaphone, Wrench, AlertTriangle,
  Hash, Volume2, FolderPlus, Pencil, Trash2, Copy,
  Unlock, Timer, MessageSquareX, Bell, BellOff, SearchCheck, Bot, UserCog,
  Webhook, Link, ScrollText, BarChart4, ClipboardList, Terminal, Gem
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { AdminStats, AdminConfig } from "@/types/api";
import { toast } from "sonner";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";
import { Select } from "@/components/ui/select";
import { FeatureFlagsPanel } from "@/components/dashboard/feature-flags-panel";
import { SystemHealthPanel } from "@/components/dashboard/system-health-panel";
import { TeamPanel } from "@/components/dashboard/team-panel";
import { PremiumPanel, PremiumKeysPanel } from "@/components/dashboard/premium-panel";
import { OwnerAccessPanel } from "@/components/dashboard/owner-access-panel";
import { useSession } from "next-auth/react";
import { ReportsPanel } from "@/components/dashboard/reports-panel";
import { AuditPanel } from "@/components/dashboard/audit-panel";
import { ApprovalsPanel } from "@/components/dashboard/approvals-panel";
import { BotSettingsPanel } from "@/components/dashboard/bot-settings-panel";
import { BroadcastPanel } from "@/components/dashboard/broadcast-panel";
import { BackupsPanel } from "@/components/dashboard/backups-panel";
import { WarningsPanel } from "@/components/dashboard/warnings-panel";
import { CommandStatsPanel } from "@/components/dashboard/command-stats-panel";
import { DashboardUsersPanel } from "@/components/dashboard/dashboard-users-panel";
import { ServersPanel } from "@/components/dashboard/servers-panel";


type TabId = "members" | "channels" | "server" | "scans" | "broadcast" | "system" | "features" | "health" | "team" | "access" | "reports" | "audit" | "approvals" | "botsettings" | "backups" | "warnings" | "usage" | "dashusers" | "servers" | "premium";
type MemberAction = "ban" | "kick" | "mute" | "unmute";

type QuickAction = {
  action: string;
  label: string;
  desc: string;
  icon: any;
  tab: Exclude<TabId, "members" | "broadcast" | "system"> | "members";
  needs?: Array<"channel" | "name" | "amount" | "seconds">;
};

const tabs: Array<{ id: TabId; label: string; icon: any }> = [
  { id: "members", label: "Members", icon: Users },
  { id: "channels", label: "Channels", icon: Hash },
  { id: "server", label: "Server", icon: Server },
  { id: "scans", label: "Scans", icon: SearchCheck },
  { id: "broadcast", label: "Broadcast", icon: Megaphone },
  { id: "system", label: "System", icon: Wrench },
  { id: "features", label: "Features", icon: Settings },
  { id: "health", label: "Health", icon: Activity },
  { id: "team", label: "Team", icon: Users },
  { id: "dashusers", label: "Dashboard Users", icon: UserCog },
  { id: "servers", label: "Servers", icon: Globe },
  { id: "warnings", label: "Warnings", icon: AlertTriangle },
  { id: "usage", label: "Usage", icon: Terminal },
  { id: "reports", label: "Reports", icon: BarChart4 },
  { id: "audit", label: "Audit", icon: ScrollText },
  { id: "approvals", label: "Approvals", icon: ClipboardList },
  { id: "backups", label: "Backups", icon: Database },
  { id: "botsettings", label: "Bot Config", icon: Wrench },
  { id: "access", label: "Access", icon: Lock },
  { id: "premium", label: "Premium", icon: Gem },
];

const memberActions: Array<{ action: MemberAction; label: string; desc: string; icon: any }> = [
  { action: "mute", label: "Mute", desc: "Timeout a member for a selected duration.", icon: Clock },
  { action: "unmute", label: "Unmute", desc: "Remove a member timeout.", icon: VolumeX },
  { action: "kick", label: "Kick", desc: "Remove a member from the server.", icon: UserX },
  { action: "ban", label: "Ban", desc: "Ban a user from the server.", icon: Ban },
];

const quickActions: QuickAction[] = [
  { tab: "channels", action: "create_text_channel", label: "Create Text Channel", desc: "Create a text channel with the given name.", icon: Hash, needs: ["name"] },
  { tab: "channels", action: "create_voice_channel", label: "Create Voice Channel", desc: "Create a voice channel with the given name.", icon: Volume2, needs: ["name"] },
  { tab: "channels", action: "create_category", label: "Create Category", desc: "Create a category with the given name.", icon: FolderPlus, needs: ["name"] },
  { tab: "channels", action: "rename_channel", label: "Rename Channel", desc: "Rename the selected channel.", icon: Pencil, needs: ["channel", "name"] },
  { tab: "channels", action: "delete_channel", label: "Delete Channel", desc: "Delete the selected channel.", icon: Trash2, needs: ["channel"] },
  { tab: "channels", action: "clone_channel", label: "Clone Channel", desc: "Clone selected channel and permissions.", icon: Copy, needs: ["channel"] },
  { tab: "channels", action: "lock_channel", label: "Lock Channel", desc: "Disable @everyone sending messages.", icon: Lock, needs: ["channel"] },
  { tab: "channels", action: "unlock_channel", label: "Unlock Channel", desc: "Restore @everyone send messages.", icon: Unlock, needs: ["channel"] },
  { tab: "channels", action: "slowmode", label: "Set Slowmode", desc: "Set slowmode seconds in selected channel.", icon: Timer, needs: ["channel", "seconds"] },
  { tab: "channels", action: "purge", label: "Purge Messages", desc: "Delete recent messages in selected channel.", icon: MessageSquareX, needs: ["channel", "amount"] },

  { tab: "server", action: "server_name", label: "Rename Server", desc: "Change server name.", icon: Pencil, needs: ["name"] },
  { tab: "server", action: "verification_level_low", label: "Verification Low", desc: "Set verification level to low.", icon: Shield },
  { tab: "server", action: "verification_level_medium", label: "Verification Medium", desc: "Set verification level to medium.", icon: Shield },
  { tab: "server", action: "default_notifications_mentions", label: "Notifications Mentions", desc: "Default notifications: only mentions.", icon: BellOff },
  { tab: "server", action: "default_notifications_all", label: "Notifications All", desc: "Default notifications: all messages.", icon: Bell },

  { tab: "scans", action: "scan_admin_roles", label: "Scan Admin Roles", desc: "List roles with administrator.", icon: Shield },
  { tab: "scans", action: "scan_dangerous_roles", label: "Scan Dangerous Roles", desc: "List roles with risky permissions.", icon: AlertTriangle },
  { tab: "scans", action: "list_bots", label: "List Bots", desc: "List cached bots in the guild.", icon: Bot },
  { tab: "scans", action: "list_staff", label: "List Staff", desc: "List members with staff-like permissions.", icon: UserCog },
  { tab: "scans", action: "server_stats", label: "Server Stats", desc: "Show member/role/channel counts.", icon: Activity },
  { tab: "scans", action: "scan_public_channels", label: "Public Channels", desc: "List public text channels.", icon: Hash },
  { tab: "scans", action: "scan_webhooks", label: "Scan Webhooks", desc: "Find webhooks in text channels.", icon: Webhook },
  { tab: "scans", action: "scan_invites", label: "Scan Invites", desc: "List active invite codes.", icon: Link },
  { tab: "scans", action: "audit_summary", label: "Audit Summary", desc: "Show recent audit log entries.", icon: ScrollText },
];
/** Tabs that render on their own, without the input sidebar. */
const FULL_WIDTH_TABS = new Set<TabId>([
  "features", "health", "team", "access",
  "reports", "audit", "approvals", "botsettings", "backups", "warnings", "usage",
  "dashusers", "servers", "premium",
]);

function TextInput({ label, value, setValue, placeholder, type = "text" }: { label: string; value: string; setValue: (value: string) => void; placeholder?: string; type?: string }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">{label}</span>
      <input value={value} onChange={(e) => setValue(e.target.value)} type={type} placeholder={placeholder || label} className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" />
    </label>
  );
}

export function AdminContent() {
  const { data: session } = useSession();
  // Own access, used to hide tabs the user has no permission for.
  const [access, setAccess] = useState<{
    is_owner: boolean;
    permissions: string[];
    roles: Array<{ key: string; label: string }>;
  } | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [guilds, setGuilds] = useState<any[]>([]);
  const [channels, setChannels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState("");
  // What the server last confirmed, so an edit in progress is
  // recognisable and "Verwerfen" has something to go back to.
  const savedNotification = useRef("");
  const [activeTab, setActiveTab] = useState<TabId>("members");
  const [result, setResult] = useState("");

  const [guildId, setGuildId] = useState("");
  const [userId, setUserId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("10");
  const [seconds, setSeconds] = useState("5");
  const [duration, setDuration] = useState("60");
  const [reason, setReason] = useState("Dashboard admin action");
  const [memberAction, setMemberAction] = useState<MemberAction>("mute");

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [statsData, configData, guildData] = await Promise.all([api.getAdminStats(), api.getAdminConfig(), api.listGuilds()]);
      setStats(statsData);
      setConfig(configData);
      // Only adopt the server's text when the box is untouched. This
      // poll runs every 30 seconds, so typing a longer notice used to
      // have the text yanked out from under the cursor mid-sentence.
      setNotification((current) =>
        current === savedNotification.current
          ? configData.global_notification || ""
          : current
      );
      savedNotification.current = configData.global_notification || "";
      setGuilds(guildData || []);
      if (!guildId && guildData?.[0]?.id) setGuildId(String(guildData[0].id));
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

  // Open the tab named in the URL hash, e.g. /dashboard/admin#health.
  // The global search links here, and it keeps the tab on a page reload.
  useEffect(() => {
    const applyHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (hash && tabs.some((t) => t.id === hash)) {
        setActiveTab(hash as TabId);
      }
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  // Load own permissions so tabs the user cannot use are hidden.
  useEffect(() => {
    const userId = (session?.user as any)?.id;
    if (!userId) return;
    api
      .getOwnAccess(userId)
      .then(setAccess)
      .catch(() => setAccess(null));
  }, [session?.user]);

  useEffect(() => {
    if (!guildId) return;
    async function loadGuildMeta() {
      try {
        const channelData = await api.getChannels(guildId);
        setChannels(channelData || []);
      } catch (err) {
        setChannels([]);
      }
    }
    loadGuildMeta();
  }, [guildId]);

  const guildOptions = guilds.map((guild) => ({ value: String(guild.id), label: `${guild.name} (${guild.id})` }));
  const channelOptions = channels.map((channel) => ({ value: String(channel.id), label: `#${channel.name}` }));

  const statItems = [
    { name: "Gesamte Nutzer", value: stats?.total_users || "0", icon: Users, color: "text-blue-500" },
    { name: "Active Servers", value: stats?.active_servers || "0", icon: Server, color: "text-emerald-500" },
    { name: "API Latency", value: stats?.api_latency || "0ms", icon: Activity, color: "text-amber-500" },
    { name: "Database Size", value: stats?.db_size || "0 MB", icon: Database, color: "text-purple-500" },
  ];

  // Which permission each tab needs. Tabs without an entry are always shown.
  const TAB_PERMISSION: Partial<Record<TabId, string>> = {
    members: "members.view",
    channels: "channels.manage",
    server: "server.manage",
    scans: "security.scan",
    broadcast: "broadcast.send",
    system: "maintenance.toggle",
    features: "features.view",
    health: "health.view",
    team: "team.view",
    dashusers: "team.view",
    servers: "guild.view",
    warnings: "members.view",
    usage: "metrics.view",
    reports: "reports.view",
    audit: "audit.view",
    approvals: "approvals.view",
    backups: "health.view",
    botsettings: "maintenance.toggle",
  };

  const visibleTabs = useMemo(() => {
    // Before the permissions arrive, show everything: the API rejects
    // anything the user may not do anyway.
    if (!access) return tabs;
    if (access.is_owner) return tabs;

    return tabs.filter((tab) => {
      // Owner/admin management is only for owners and admins, never for
      // people who merely hold a team role.
      if (tab.id === "access") return false;
      const required = TAB_PERMISSION[tab.id];
      if (!required) return true;
      return access.permissions.includes(required);
    });
  }, [access]);

  // If the active tab disappeared, fall back to the first one available.
  useEffect(() => {
    if (visibleTabs.length && !visibleTabs.some((t) => t.id === activeTab)) {
      setActiveTab(visibleTabs[0].id);
    }
  }, [visibleTabs, activeTab]);

  const currentActions = useMemo(() => quickActions.filter((action) => action.tab === activeTab), [activeTab]);
  const currentNeeds = useMemo(() => new Set(currentActions.flatMap((action) => action.needs || [])), [currentActions]);

  const basePayload = () => ({ guild_id: guildId, user_id: userId.trim(), channel_id: channelId, name: name.trim(), amount: Number(amount) || 10, seconds: Number(seconds) || 5, duration_minutes: Number(duration) || 60, reason: reason.trim() });

  const requireGuild = () => {
    if (!guildId) {
      toast.error("Please select a server first.");
      return false;
    }
    return true;
  };

  const runMemberModeration = async () => {
    if (!requireGuild()) return;
    if (!/^\d{15,25}$/.test(userId.trim())) return toast.error("Please enter a valid User ID.");
    if (!reason.trim()) return toast.error("Please enter a reason.");
    setSaving(true);
    const promise = api.runAdminMemberAction({ ...basePayload(), action: memberAction });
    toast.promise(promise, { loading: `Running ${memberAction}...`, success: (data) => data.result, error: (err) => err.message || "Action failed." });
    try { const data = await promise; setResult(data.result); } finally { setSaving(false); }
  };

  const runQuickAction = async (action: QuickAction) => {
    if (!requireGuild()) return;
    if (action.needs?.includes("channel") && !channelId) return toast.error("Please select a channel.");
    if (action.needs?.includes("name") && !name.trim()) return toast.error("Please enter a name.");
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
      savedNotification.current = notification;
      toast.success("Dashboard-Hinweis gespeichert.");
    } catch { toast.error("Failed to update broadcast message"); } finally { setSaving(false); }
  };

  // The notice is the only free-text field on this page, and it sits at
  // the bottom of the System tab -- easy to type into and walk away
  // from. Refuse to leave while it differs from what was saved.
  const noticeDirty = notification === savedNotification.current ? 0 : 1;
  const noticeGuard = useSaveGuard(noticeDirty, "admin-notice-save-bar");

  if (loading) return <div className="flex items-center justify-center min-h-[400px]"><RefreshCw className="h-10 w-10 text-blue-500 animate-spin opacity-20" /></div>;

  return (
    <div className="space-y-10 animate-in fade-in duration-500">
      <div className="relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-3xl blur opacity-10 group-hover:opacity-20 transition duration-1000" />
        <div className="relative bg-[#0b1f3a] border border-white/10 rounded-3xl p-8 lg:p-12 flex flex-col lg:flex-row lg:items-center justify-between gap-8">
          <div className="flex items-center gap-6"><div className="h-16 w-16 rounded-2xl bg-blue-500/20 flex items-center justify-center border border-blue-500/30 shadow-2xl shadow-blue-500/20"><Shield className="h-8 w-8 text-blue-500" /></div><div><h1 className="text-4xl font-black text-white tracking-tight font-outfit">Admin Control Panel</h1><p className="text-slate-400 mt-2 font-medium">Select a server, then run moderation and management actions quickly.</p></div></div>
          <button onClick={() => fetchData(true)} className="flex items-center gap-3 bg-blue-500/5 px-6 py-3 rounded-2xl border border-blue-500/10 hover:bg-blue-500/10 transition-all active:scale-95"><RefreshCw className={cn("h-4 w-4 text-blue-500 transition-all", refreshing && "animate-spin")} /><span className="text-xs font-black uppercase tracking-widest text-blue-500">{refreshing ? "Refreshing..." : "Real-time Mode"}</span></button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">{statItems.map((stat) => <div key={stat.name} className="glass border border-white/5 rounded-3xl p-4 sm:p-6 hover:border-white/10 transition-all group"><div className="flex items-center justify-between mb-4"><div className={cn("p-3 rounded-xl bg-white/[0.03] group-hover:scale-110 transition-transform", stat.color)}><stat.icon className="h-6 w-6" /></div><span className="text-[10px] font-black uppercase tracking-widest text-emerald-500 bg-emerald-500/10 px-2 py-1 rounded-lg">Live</span></div><p className="text-slate-500 text-xs font-bold uppercase tracking-widest">{stat.name}</p><h3 className="text-2xl font-black text-white mt-1 font-outfit">{stat.value}</h3></div>)}</div>

      <div className="flex flex-wrap gap-3 p-2 bg-[#10233f]/70 border border-slate-800 rounded-3xl">{visibleTabs.map((tab) => { const active = activeTab === tab.id; return <button key={tab.id} onClick={() => { setActiveTab(tab.id); window.history.replaceState(null, "", `#${tab.id}`); }} className={cn("flex items-center gap-2 px-5 py-3 rounded-2xl text-sm font-black uppercase tracking-wider transition-all", active ? "bg-primary text-white shadow-lg shadow-primary/20" : "text-slate-400 hover:bg-slate-800/70 hover:text-white")}><tab.icon className="h-4 w-4" />{tab.label}</button>; })}</div>

      {/* Features and Health are full-width: they have no input sidebar. */}
      {activeTab === "features" && <FeatureFlagsPanel />}
      {activeTab === "health" && <SystemHealthPanel />}
      {activeTab === "team" && <TeamPanel />}
      {activeTab === "premium" && (
        <div className="space-y-6">
          <PremiumPanel />
          <PremiumKeysPanel />
        </div>
      )}
      {activeTab === "access" && <OwnerAccessPanel currentUserId={(session?.user as any)?.id} />}
      {activeTab === "usage" && <CommandStatsPanel />}
      {activeTab === "dashusers" && <DashboardUsersPanel currentUserId={(session?.user as any)?.id} />}
      {activeTab === "servers" && <ServersPanel currentUserId={(session?.user as any)?.id} />}
      {activeTab === "reports" && <ReportsPanel />}
      {activeTab === "audit" && <AuditPanel />}
      {activeTab === "approvals" && <ApprovalsPanel currentUserId={(session?.user as any)?.id} />}
      {activeTab === "backups" && <BackupsPanel guilds={guilds} />}
      {activeTab === "botsettings" && <BotSettingsPanel />}
      {activeTab === "warnings" && (
        <div className="space-y-6">
          <div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8">
            <div className="flex items-center gap-4 mb-6">
              <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
                <AlertTriangle className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h3 className="text-xl font-black text-white">Warnings</h3>
                <p className="text-sm text-slate-400 mt-1">Who was warned, by whom and why.</p>
              </div>
            </div>
            <div className="max-w-md">
              <span className="text-xs font-black uppercase tracking-widest text-slate-500">Server</span>
              <div className="mt-2">
                <Select value={guildId} onValueChange={setGuildId} options={guildOptions} placeholder="Select server" />
              </div>
            </div>
          </div>
          <WarningsPanel guildId={guildId} />
        </div>
      )}

      {!FULL_WIDTH_TABS.has(activeTab) && (
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
        <aside className="xl:col-span-1 glass border border-white/5 rounded-[2rem] p-6 space-y-4 h-fit">
          <h3 className="font-black text-white flex items-center gap-2"><SearchCheck className="h-5 w-5 text-primary" /> Inputs</h3>
          <div className="space-y-2"><span className="text-xs font-black uppercase tracking-widest text-slate-500">Server</span><Select value={guildId} onValueChange={setGuildId} options={guildOptions} placeholder="Select server" /></div>

          {activeTab === "members" && <TextInput label="User ID" value={userId} setValue={setUserId} placeholder="Only user ID needed" />}
          {currentNeeds.has("channel") && <div className="space-y-2"><span className="text-xs font-black uppercase tracking-widest text-slate-500">Channel</span><Select value={channelId} onValueChange={setChannelId} options={channelOptions} placeholder="Select channel" /></div>}
          {currentNeeds.has("name") && <TextInput label="Name" value={name} setValue={setName} />}
          {currentNeeds.has("amount") && <TextInput label="Amount" value={amount} setValue={setAmount} type="number" />}
          {currentNeeds.has("seconds") && <TextInput label="Seconds" value={seconds} setValue={setSeconds} type="number" />}
          {activeTab === "members" && <TextInput label="Timeout minutes" value={duration} setValue={setDuration} type="number" />}
          {(activeTab === "members" || ["channels", "server"].includes(activeTab)) && <label className="block space-y-2"><span className="text-xs font-black uppercase tracking-widest text-slate-500">Reason</span><textarea value={reason} onChange={(e) => setReason(e.target.value)} className="w-full h-24 bg-white/[0.03] border border-white/5 rounded-2xl p-4 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary" /></label>}
          {result && <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl text-emerald-300 text-sm leading-relaxed">{result}</div>}
        </aside>

        <main className="xl:col-span-3 space-y-6">
          {activeTab === "members" && <section className="space-y-5"><div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">{memberActions.map((card) => { const active = memberAction === card.action; return <button key={card.action} onClick={() => setMemberAction(card.action)} className={cn("text-left p-5 rounded-3xl border transition-all", active ? "bg-primary/10 border-primary/40" : "bg-white/[0.02] border-white/5 hover:border-white/10")}><card.icon className={cn("h-6 w-6 mb-3", active ? "text-primary" : "text-slate-500")} /><p className="font-black text-white">{card.label}</p><p className="text-xs text-slate-500 mt-1">{card.desc}</p></button>; })}</div><button onClick={runMemberModeration} disabled={saving} className="w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-50">Run {memberAction}</button></section>}

          {(activeTab === "members" || activeTab === "channels" || activeTab === "server" || activeTab === "scans") && <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">{currentActions.map((action) => <button key={action.action} onClick={() => runQuickAction(action)} disabled={saving} className="text-left bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 hover:border-primary/40 hover:bg-primary/5 transition-all disabled:opacity-50"><action.icon className="h-6 w-6 text-primary mb-4" /><h4 className="font-black text-white">{action.label}</h4><p className="text-sm text-slate-500 mt-2">{action.desc}</p>{action.needs?.length ? <p className="text-[10px] uppercase tracking-widest text-slate-600 mt-4">Needs: {action.needs.join(", ")}</p> : null}</button>)}</section>}

          {activeTab === "broadcast" && <BroadcastPanel guilds={guilds} />}

          {activeTab === "system" && <section className="grid grid-cols-1 lg:grid-cols-3 gap-8"><div className="lg:col-span-2 glass border border-white/5 rounded-[2rem] overflow-hidden"><div className="p-8 border-b border-white/5 flex items-center justify-between bg-white/[0.01]"><div className="flex items-center gap-4"><Activity className="h-5 w-5 text-blue-500" /><h3 className="text-lg font-bold text-white">System Nodes Status</h3></div><span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Auto-Polling Active</span></div><div className="p-8 space-y-6">{stats?.nodes.map((node) => { const Icon = node.icon === "Globe" ? Globe : node.icon === "Database" ? Database : node.icon === "Cpu" ? Cpu : Lock; const healthy = node.status === "Healthy"; return <div key={node.name} className="flex items-center justify-between p-4 bg-white/[0.02] rounded-2xl border border-white/5"><div className="flex items-center gap-4"><div className="h-10 w-10 rounded-xl bg-slate-800 flex items-center justify-center"><Icon className="h-5 w-5 text-slate-400" /></div><div><h4 className="text-sm font-bold text-white">{node.name}</h4><p className="text-[10px] font-black uppercase text-slate-500 tracking-widest">Load: {node.load}</p></div></div><span className={cn("text-[10px] font-bold uppercase px-3 py-1.5 rounded-full border", healthy ? "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" : "text-amber-500 bg-amber-500/10 border-amber-500/20")}>{node.status}</span></div>; })}</div></div><div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8"><Settings className="h-5 w-5 text-indigo-500 mb-4" /><h3 className="text-lg font-bold text-white mb-4">System Controls</h3><button onClick={handleToggleMaintenance} disabled={saving} className={cn("w-full flex items-center justify-between p-4 rounded-2xl border transition-all", config?.maintenance_mode ? "bg-blue-500/10 border-blue-500/30 text-blue-500" : "bg-white/[0.03] border-white/5 text-slate-300 hover:bg-white/[0.05]")}><span className="text-sm font-medium">{config?.maintenance_mode ? "Restricting Access" : "Standard Operations"}</span></button>
            {/* The dashboard's own banner. This used to sit under a tab
                called "Global Broadcast", which is what it is not: it
                never reaches Discord, only people who open the dashboard. */}
            <div className="mt-6 pt-6 border-t border-white/5 space-y-3">
              <h4 className="text-sm font-bold text-white">Dashboard-Hinweis</h4>
              <p className="text-[11px] text-slate-500 leading-relaxed">Wird oben im Dashboard angezeigt. Geht <b>nicht</b> an Discord — dafür ist der Broadcast-Tab da.</p>
              <textarea value={notification} onChange={(e) => setNotification(e.target.value)} className="w-full h-24 bg-white/[0.03] border border-white/5 rounded-2xl p-3 text-sm text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500/30" placeholder="Leer lassen, um den Hinweis zu entfernen" />
              <button onClick={handleBroadcast} disabled={saving || !noticeDirty} className="w-full py-3 bg-white/[0.05] border border-white/10 rounded-2xl font-black uppercase tracking-widest text-[11px] text-slate-300 hover:text-white disabled:opacity-50 transition-all">Hinweis speichern</button>
            </div></div></section>}
        </main>
      </div>
      )}

      {!FULL_WIDTH_TABS.has(activeTab) && (
        <div className="glass border border-white/5 rounded-3xl p-5 flex gap-3 text-sm text-slate-400"><AlertTriangle className="h-5 w-5 text-amber-500 shrink-0" />Select a server first. For kick, ban, mute and unmute you only need the user ID, timeout duration (for mute) and reason. Channels can be selected from dropdowns.</div>
      )}

      <StickySaveBar
        id="admin-notice-save-bar"
        count={noticeDirty}
        busy={saving}
        shake={noticeGuard.shake}
        onDiscard={() => setNotification(savedNotification.current)}
        onSave={handleBroadcast}
      />
    </div>
  );
}
