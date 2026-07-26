/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║           © 2026 University Bot Devs — All Rights Reserved       ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

import React, { useState, useEffect } from "react";
import {
  Shield, Users, Server, Activity, Database, Cpu, Globe, Lock, Settings, RefreshCw,
  Save, AlertTriangle, KeyRound, Ban, Crown, ScrollText, UserX, Gem, Gauge,
  HardDrive, SearchCheck, Trash2, Flame, RadioTower, Music, Wifi, Bug, Cookie,
  BarChart3, Timer, Terminal, Puzzle, RotateCcw, DoorOpen, DoorClosed, Siren,
  UploadCloud, GitBranch, FlaskConical, LayoutTemplate, Megaphone, UserCog,
  ShieldCheck, Wand2, Ticket, Mic2, LineChart, Webhook, Layers, FileDown,
  History, ClipboardList, UserCheck, UsersRound, Rocket, TrainTrack, Power
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { AdminStats, AdminConfig } from "@/types/api";
import { toast } from "sonner";

const adminFeatureDefaults = {
  global_emergency_lockdown: false,
  maintenance_banner: true,
  force_dashboard_reauth: false,
  global_command_freeze: false,
  owner_only_mode: false,
  cross_guild_audit_log: true,
  global_blacklist_sync: true,
  premium_access_control: true,
  api_rate_limit_boost: true,
  database_backup_scheduler: true,
  database_integrity_scan: true,
  orphan_data_cleanup: false,
  cache_warmup: true,
  shard_health_monitor: true,
  lavalink_health_monitor: true,
  music_node_failover: true,
  discord_api_status_watch: true,
  oauth_error_tracker: true,
  session_cookie_monitor: true,
  dashboard_performance_metrics: true,
  slow_query_detector: false,
  command_error_analytics: true,
  module_load_guard: true,
  cog_auto_recovery: true,
  guild_join_guard: true,
  guild_leave_audit: true,
  suspicious_owner_action_alerts: true,
  mass_config_push: false,
  feature_flag_rollouts: true,
  beta_module_access: false,
  premium_template_manager: false,
  global_announcement_scheduler: true,
  staff_permission_review: true,
  security_score_calculation: true,
  automod_rule_recommendations: true,
  ticket_load_balancer: true,
  voice_session_analytics: false,
  invite_growth_analytics: true,
  member_retention_insights: true,
  webhook_risk_scanner: true,
  role_risk_scanner: true,
  channel_risk_scanner: true,
  export_admin_reports: true,
  incident_timeline_builder: true,
  global_notification_history: true,
  admin_action_approval_queue: false,
  two_person_rule: false,
  deployment_health_gate: true,
  railway_log_watch: true,
  auto_restart_on_deadlock: true,
} as const;

type AdminFeatureKey = keyof typeof adminFeatureDefaults;

const adminFeatureMeta: Array<{ key: AdminFeatureKey; title: string; desc: string; group: string; icon: any }> = [
  { key: "global_emergency_lockdown", title: "Global Emergency Lockdown", desc: "Freeze risky actions across all connected guilds.", group: "Security", icon: Siren },
  { key: "maintenance_banner", title: "Maintenance Banner", desc: "Show a dashboard-wide maintenance notice.", group: "Global", icon: AlertTriangle },
  { key: "force_dashboard_reauth", title: "Force Dashboard Reauth", desc: "Require all dashboard users to authorize again.", group: "Auth", icon: KeyRound },
  { key: "global_command_freeze", title: "Global Command Freeze", desc: "Temporarily pause selected public bot commands.", group: "Commands", icon: Ban },
  { key: "owner_only_mode", title: "Owner Only Mode", desc: "Restrict sensitive features to bot owners.", group: "Access", icon: Crown },
  { key: "cross_guild_audit_log", title: "Cross-Guild Audit Log", desc: "Collect important security events across guilds.", group: "Audits", icon: ScrollText },
  { key: "global_blacklist_sync", title: "Global Blacklist Sync", desc: "Synchronize blacklist data between modules.", group: "Security", icon: UserX },
  { key: "premium_access_control", title: "Premium Access Control", desc: "Central switch for premium-only dashboard modules.", group: "Premium", icon: Gem },
  { key: "api_rate_limit_boost", title: "API Rate Limit Boost", desc: "Use higher internal limits for trusted admin operations.", group: "API", icon: Gauge },
  { key: "database_backup_scheduler", title: "Database Backup Scheduler", desc: "Schedule regular SQLite configuration backups.", group: "Database", icon: HardDrive },
  { key: "database_integrity_scan", title: "Database Integrity Scan", desc: "Scan database files for corruption or missing tables.", group: "Database", icon: SearchCheck },
  { key: "orphan_data_cleanup", title: "Orphan Data Cleanup", desc: "Clean old records for guilds that no longer use the bot.", group: "Cleanup", icon: Trash2 },
  { key: "cache_warmup", title: "Cache Warmup", desc: "Preload important dashboard data after startup.", group: "Performance", icon: Flame },
  { key: "shard_health_monitor", title: "Shard Health Monitor", desc: "Watch shard latency and boot state.", group: "Runtime", icon: RadioTower },
  { key: "lavalink_health_monitor", title: "Lavalink Health Monitor", desc: "Track music node availability and latency.", group: "Music", icon: Music },
  { key: "music_node_failover", title: "Music Node Failover", desc: "Prepare automatic switching when a music node fails.", group: "Music", icon: Wifi },
  { key: "discord_api_status_watch", title: "Discord API Status Watch", desc: "Monitor Discord API problems and rate-limit pressure.", group: "Runtime", icon: Globe },
  { key: "oauth_error_tracker", title: "OAuth Error Tracker", desc: "Track Discord login callback and session errors.", group: "Auth", icon: Bug },
  { key: "session_cookie_monitor", title: "Session Cookie Monitor", desc: "Detect broken NextAuth cookies or proxy header issues.", group: "Auth", icon: Cookie },
  { key: "dashboard_performance_metrics", title: "Dashboard Performance Metrics", desc: "Collect high-level dashboard load and API timing data.", group: "Performance", icon: BarChart3 },
  { key: "slow_query_detector", title: "Slow Query Detector", desc: "Flag slow database/API requests for optimization.", group: "Database", icon: Timer },
  { key: "command_error_analytics", title: "Command Error Analytics", desc: "Aggregate command failures for debugging.", group: "Commands", icon: Terminal },
  { key: "module_load_guard", title: "Module Load Guard", desc: "Warn if a cog/module fails to load at startup.", group: "Runtime", icon: Puzzle },
  { key: "cog_auto_recovery", title: "Cog Auto Recovery", desc: "Prepare automatic reload attempts for failed modules.", group: "Runtime", icon: RotateCcw },
  { key: "guild_join_guard", title: "Guild Join Guard", desc: "Analyze newly joined guilds for risk indicators.", group: "Guilds", icon: DoorOpen },
  { key: "guild_leave_audit", title: "Guild Leave Audit", desc: "Record when the bot leaves or is removed from guilds.", group: "Guilds", icon: DoorClosed },
  { key: "suspicious_owner_action_alerts", title: "Suspicious Owner Action Alerts", desc: "Notify owners when sensitive global actions are triggered.", group: "Security", icon: Shield },
  { key: "mass_config_push", title: "Mass Config Push", desc: "Allow prepared settings to be pushed to many guilds.", group: "Automation", icon: UploadCloud },
  { key: "feature_flag_rollouts", title: "Feature Flag Rollouts", desc: "Enable staged rollout of dashboard features.", group: "Automation", icon: GitBranch },
  { key: "beta_module_access", title: "Beta Module Access", desc: "Allow selected guilds to test beta modules.", group: "Beta", icon: FlaskConical },
  { key: "premium_template_manager", title: "Premium Template Manager", desc: "Manage premium server templates from the dashboard.", group: "Premium", icon: LayoutTemplate },
  { key: "global_announcement_scheduler", title: "Global Announcement Scheduler", desc: "Prepare scheduled announcements across dashboards.", group: "Global", icon: Megaphone },
  { key: "staff_permission_review", title: "Staff Permission Review", desc: "Analyze staff roles and dangerous permissions.", group: "Security", icon: UserCog },
  { key: "security_score_calculation", title: "Security Score Calculation", desc: "Calculate a server security score from enabled modules.", group: "Insights", icon: ShieldCheck },
  { key: "automod_rule_recommendations", title: "Automod Rule Recommendations", desc: "Suggest Automod improvements from server activity.", group: "Automation", icon: Wand2 },
  { key: "ticket_load_balancer", title: "Ticket Load Balancer", desc: "Prepare assignment balancing for busy support teams.", group: "Support", icon: Ticket },
  { key: "voice_session_analytics", title: "Voice Session Analytics", desc: "Collect voice channel usage and session insights.", group: "Voice", icon: Mic2 },
  { key: "invite_growth_analytics", title: "Invite Growth Analytics", desc: "Track invite growth patterns and campaign effects.", group: "Insights", icon: LineChart },
  { key: "member_retention_insights", title: "Member Retention Insights", desc: "Understand member join/leave retention trends.", group: "Insights", icon: UsersRound },
  { key: "webhook_risk_scanner", title: "Webhook Risk Scanner", desc: "Find risky webhooks and public webhook exposure.", group: "Security", icon: Webhook },
  { key: "role_risk_scanner", title: "Role Risk Scanner", desc: "Find roles with dangerous or unnecessary permissions.", group: "Security", icon: Layers },
  { key: "channel_risk_scanner", title: "Channel Risk Scanner", desc: "Find channels with unsafe overwrites.", group: "Security", icon: Server },
  { key: "export_admin_reports", title: "Export Admin Reports", desc: "Prepare CSV/JSON export for admin insights.", group: "Reports", icon: FileDown },
  { key: "incident_timeline_builder", title: "Incident Timeline Builder", desc: "Build timelines from moderation and audit events.", group: "Reports", icon: History },
  { key: "global_notification_history", title: "Global Notification History", desc: "Store previous global dashboard broadcasts.", group: "Global", icon: ClipboardList },
  { key: "admin_action_approval_queue", title: "Admin Action Approval Queue", desc: "Queue dangerous admin actions for approval.", group: "Access", icon: UserCheck },
  { key: "two_person_rule", title: "Two-Person Rule", desc: "Require two admins for highly sensitive actions.", group: "Access", icon: Users },
  { key: "deployment_health_gate", title: "Deployment Health Gate", desc: "Block unsafe changes when deployment health is degraded.", group: "Runtime", icon: Rocket },
  { key: "railway_log_watch", title: "Railway Log Watch", desc: "Track Railway log patterns and crash loops.", group: "Runtime", icon: TrainTrack },
  { key: "auto_restart_on_deadlock", title: "Auto Restart on Deadlock", desc: "Prepare automatic recovery for stuck services.", group: "Runtime", icon: Power },
];

export function AdminContent() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [adminFeatures, setAdminFeatures] = useState<Record<AdminFeatureKey, boolean>>(adminFeatureDefaults);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState("");

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [statsData, configData, featuresData] = await Promise.all([
        api.getAdminStats(),
        api.getAdminConfig(),
        api.getAdminFeatures(),
      ]);
      setStats(statsData);
      setConfig(configData);
      setAdminFeatures((prev) => ({ ...prev, ...featuresData }));
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
    } catch (err) {
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
    } catch (err) {
      toast.error("Failed to update broadcast message");
    } finally {
      setSaving(false);
    }
  };

  const toggleAdminFeature = (key: AdminFeatureKey, checked: boolean) => {
    setAdminFeatures((prev) => ({ ...prev, [key]: checked }));
  };

  const saveAdminFeatures = async () => {
    setSaving(true);
    const promise = api.updateAdminFeatures(adminFeatures);
    toast.promise(promise, {
      loading: "Saving admin functions...",
      success: "Admin functions saved.",
      error: "Failed to save admin functions.",
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

  const enabledCount = adminFeatureMeta.filter((feature) => adminFeatures[feature.key]).length;

  return (
    <div className="space-y-10 animate-in fade-in duration-500">
      <div className="relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-3xl blur opacity-10 group-hover:opacity-20 transition duration-1000"></div>
        <div className="relative bg-[#0b1f3a] border border-white/10 rounded-3xl p-8 lg:p-12 flex flex-col lg:flex-row lg:items-center justify-between gap-8">
          <div className="flex items-center gap-6">
            <div className="h-16 w-16 rounded-2xl bg-blue-500/20 flex items-center justify-center border border-blue-500/30 shadow-2xl shadow-blue-500/20">
              <Shield className="h-8 w-8 text-blue-500" />
            </div>
            <div>
              <h1 className="text-4xl font-black text-white tracking-tight font-outfit">Admin Control Panel</h1>
              <p className="text-slate-400 mt-2 font-medium">Restricted access for University Bot administrators only.</p>
            </div>
          </div>
          <button onClick={() => fetchData(true)} className="flex items-center gap-3 bg-blue-500/5 px-6 py-3 rounded-2xl border border-blue-500/10 hover:bg-blue-500/10 transition-all active:scale-95 group/refresh">
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
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
                  <div className="flex items-center gap-4">
                    <div className="h-10 w-10 rounded-xl bg-slate-800 flex items-center justify-center group-hover:bg-slate-700 transition-colors"><Icon className="h-5 w-5 text-slate-400" /></div>
                    <div><h4 className="text-sm font-bold text-white">{node.name}</h4><p className="text-[10px] font-black uppercase text-slate-500 tracking-widest">Load: {node.load}</p></div>
                  </div>
                  <div className={cn("flex items-center gap-2 px-3 py-1.5 rounded-full border", isHealthy ? "bg-emerald-500/10 border-emerald-500/20" : "bg-amber-500/10 border-amber-500/20")}>
                    <div className={cn("h-1.5 w-1.5 rounded-full", isHealthy ? "bg-emerald-500" : "bg-amber-500")} />
                    <span className={cn("text-[10px] font-bold uppercase", isHealthy ? "text-emerald-500" : "text-amber-500")}>{node.status}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="glass border border-white/5 rounded-[2.5rem] overflow-hidden flex flex-col">
          <div className="p-8 border-b border-white/5 flex items-center gap-4 bg-white/[0.01]"><Settings className="h-5 w-5 text-indigo-500" /><h3 className="text-lg font-bold text-white">Global Settings</h3></div>
          <div className="p-8 flex-1 space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 pl-1">Maintenance Mode</label>
              <button onClick={handleToggleMaintenance} disabled={saving} className={cn("w-full flex items-center justify-between p-4 rounded-2xl border transition-all", config?.maintenance_mode ? "bg-blue-500/10 border-blue-500/30 text-blue-500" : "bg-white/[0.03] border-white/5 text-slate-300 hover:bg-white/[0.05]")}> 
                <span className="text-sm font-medium">{config?.maintenance_mode ? "Restricting Access" : "Standard Operations"}</span>
                <div className={cn("h-6 w-11 rounded-full relative transition-colors duration-300", config?.maintenance_mode ? "bg-blue-500" : "bg-slate-700")}><div className={cn("absolute top-1 h-4 w-4 bg-white rounded-full transition-all duration-300 shadow-sm", config?.maintenance_mode ? "left-6" : "left-1")} /></div>
              </button>
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 pl-1">Global Notification</label>
              <textarea value={notification} onChange={(e) => setNotification(e.target.value)} className="w-full h-32 bg-white/[0.03] border border-white/5 rounded-2xl p-4 text-xs font-medium text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500/30 transition-all placeholder:text-slate-600" placeholder="Message to display across all dashboards..." />
            </div>
            <button onClick={handleBroadcast} disabled={saving} className="w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50">{saving ? "Processing..." : "Broadcast Message"}</button>
          </div>
        </div>
      </div>

      <section className="glass border border-white/5 rounded-[2.5rem] overflow-hidden">
        <div className="p-8 border-b border-white/5 flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-white/[0.01]">
          <div className="flex items-center gap-4"><ShieldCheck className="h-5 w-5 text-blue-500" /><div><h3 className="text-lg font-bold text-white">Global Admin Functions</h3><p className="text-slate-500 text-sm">50 admin feature switches for global security, automation, reports and runtime control.</p></div></div>
          <div className="flex items-center gap-3">
            <span className="text-xs font-black uppercase tracking-widest text-primary bg-primary/10 border border-primary/20 px-4 py-2 rounded-2xl">{enabledCount}/50 Enabled</span>
            <button onClick={saveAdminFeatures} disabled={saving} className="flex items-center gap-2 px-5 py-2.5 rounded-2xl bg-primary text-white text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-50"><Save className="h-4 w-4" />Save</button>
          </div>
        </div>
        <div className="p-8 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
          {adminFeatureMeta.map((feature) => (
            <div key={feature.key} className="bg-white/[0.02] border border-white/5 hover:border-primary/30 rounded-3xl p-5 transition-all group">
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-4 min-w-0">
                  <div className="p-3 rounded-2xl bg-primary/10 text-primary shrink-0 group-hover:scale-110 transition-transform"><feature.icon className="h-5 w-5" /></div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap"><h4 className="text-sm font-black text-white">{feature.title}</h4><span className="text-[9px] uppercase tracking-widest font-black text-slate-500 bg-slate-900/60 border border-slate-800 px-2 py-0.5 rounded-full">{feature.group}</span></div>
                    <p className="text-xs text-slate-500 mt-2 leading-relaxed">{feature.desc}</p>
                  </div>
                </div>
                <button onClick={() => toggleAdminFeature(feature.key, !adminFeatures[feature.key])} className={cn("h-6 w-11 rounded-full relative transition-colors shrink-0", adminFeatures[feature.key] ? "bg-primary" : "bg-slate-700")}>
                  <span className={cn("absolute top-1 h-4 w-4 bg-white rounded-full transition-all duration-300 shadow-sm", adminFeatures[feature.key] ? "left-6" : "left-1")} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
