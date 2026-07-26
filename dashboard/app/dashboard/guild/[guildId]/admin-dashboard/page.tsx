"use client";

import React, { useEffect, useState } from "react";
import {
  Shield, Save, RefreshCcw, Lock, Radar, ScanLine, ServerCog, Trash2, Link,
  Webhook, Bot, MessageSquareWarning, FileClock, GitCompare, Layers, UserPlus,
  UserSearch, Wand2, Archive, Activity, Ticket, Mic2, RadioTower
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";

type FeatureKey =
  | "emergency_lockdown"
  | "anti_raid_watch"
  | "auto_role_audit"
  | "permission_scan"
  | "inactive_channel_scan"
  | "invite_security"
  | "webhook_monitoring"
  | "bot_role_guard"
  | "mass_mention_guard"
  | "dashboard_audit_log"
  | "channel_permission_diff"
  | "role_hierarchy_alerts"
  | "new_account_watch"
  | "suspicious_name_watch"
  | "automod_recommendations"
  | "backup_snapshot_reminders"
  | "staff_activity_insights"
  | "ticket_overload_alerts"
  | "voice_abuse_monitor"
  | "public_webhook_alerts";

const defaults: Record<FeatureKey, boolean> = {
  emergency_lockdown: false,
  anti_raid_watch: true,
  auto_role_audit: true,
  permission_scan: true,
  inactive_channel_scan: false,
  invite_security: true,
  webhook_monitoring: true,
  bot_role_guard: true,
  mass_mention_guard: true,
  dashboard_audit_log: true,
  channel_permission_diff: true,
  role_hierarchy_alerts: true,
  new_account_watch: true,
  suspicious_name_watch: false,
  automod_recommendations: true,
  backup_snapshot_reminders: true,
  staff_activity_insights: false,
  ticket_overload_alerts: true,
  voice_abuse_monitor: true,
  public_webhook_alerts: true,
};

const features: Array<{ key: FeatureKey; title: string; desc: string; icon: any; group: string }> = [
  { key: "emergency_lockdown", title: "Emergency Lockdown", desc: "Prepare a one-click lockdown state for dangerous situations.", icon: Lock, group: "Security" },
  { key: "anti_raid_watch", title: "Anti-Raid Watch", desc: "Track join spikes and suspicious member waves.", icon: Radar, group: "Security" },
  { key: "auto_role_audit", title: "Auto Role Audit", desc: "Check if managed roles are still below the bot role.", icon: ServerCog, group: "Audits" },
  { key: "permission_scan", title: "Permission Scan", desc: "Scan channels and roles for risky permissions.", icon: ScanLine, group: "Audits" },
  { key: "inactive_channel_scan", title: "Inactive Channel Scan", desc: "Find unused channels that can be cleaned up.", icon: Trash2, group: "Cleanup" },
  { key: "invite_security", title: "Invite Security", desc: "Monitor invite usage and suspicious invite patterns.", icon: Link, group: "Security" },
  { key: "webhook_monitoring", title: "Webhook Monitoring", desc: "Watch webhook creation/deletion for abuse.", icon: Webhook, group: "Security" },
  { key: "bot_role_guard", title: "Bot Role Guard", desc: "Warn when bot roles are moved into unsafe positions.", icon: Bot, group: "Security" },
  { key: "mass_mention_guard", title: "Mass Mention Guard", desc: "Highlight channels where mass mentions may be abused.", icon: MessageSquareWarning, group: "Security" },
  { key: "dashboard_audit_log", title: "Dashboard Audit Log", desc: "Log all important dashboard admin actions.", icon: FileClock, group: "Audits" },
  { key: "channel_permission_diff", title: "Channel Permission Diff", desc: "Detect dangerous channel overwrite changes.", icon: GitCompare, group: "Audits" },
  { key: "role_hierarchy_alerts", title: "Role Hierarchy Alerts", desc: "Warn when staff or bot roles are moved too low.", icon: Layers, group: "Security" },
  { key: "new_account_watch", title: "New Account Watch", desc: "Flag very new Discord accounts joining the server.", icon: UserPlus, group: "Members" },
  { key: "suspicious_name_watch", title: "Suspicious Name Watch", desc: "Detect invite spam, scam words, and impersonation patterns in names.", icon: UserSearch, group: "Members" },
  { key: "automod_recommendations", title: "Automod Recommendations", desc: "Suggest Automod rules based on recent moderation activity.", icon: Wand2, group: "Automation" },
  { key: "backup_snapshot_reminders", title: "Backup Snapshot Reminders", desc: "Remind admins to create configuration backups regularly.", icon: Archive, group: "Automation" },
  { key: "staff_activity_insights", title: "Staff Activity Insights", desc: "Show high-level staff moderation activity signals.", icon: Activity, group: "Insights" },
  { key: "ticket_overload_alerts", title: "Ticket Overload Alerts", desc: "Alert staff when support demand is unusually high.", icon: Ticket, group: "Support" },
  { key: "voice_abuse_monitor", title: "Voice Abuse Monitor", desc: "Detect suspicious voice channel movements and AFK abuse.", icon: Mic2, group: "Voice" },
  { key: "public_webhook_alerts", title: "Public Webhook Alerts", desc: "Warn when webhooks exist in public channels.", icon: RadioTower, group: "Security" },
];

export default function AdminDashboardPage({ params }: { params: { guildId: string } }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [values, setValues] = useState<Record<FeatureKey, boolean>>(defaults);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await api.getAdminDashboard(params.guildId);
        setValues((prev) => ({ ...prev, ...data }));
      } catch (err: any) {
        toast.error(err.message || "Admin Dashboard konnte nicht geladen werden.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [params.guildId]);

  const setFeature = (key: FeatureKey, checked: boolean) => setValues((prev) => ({ ...prev, [key]: checked }));

  const save = async () => {
    setSaving(true);
    const promise = api.updateAdminDashboard(params.guildId, values);
    toast.promise(promise, {
      loading: "Admin Dashboard wird gespeichert...",
      success: "Admin Dashboard wurde gespeichert.",
      error: "Admin Dashboard konnte nicht gespeichert werden.",
    });
    try { await promise; } finally { setSaving(false); }
  };

  if (loading) return <div className="min-h-[300px] flex items-center justify-center"><RefreshCcw className="h-8 w-8 animate-spin text-primary" /></div>;

  const enabledCount = features.filter((feature) => values[feature.key]).length;

  return (
    <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2"><Shield className="h-6 w-6 text-primary" />Admin Dashboard</h2>
          <p className="text-slate-400 mt-1">20 Premium Admin-Funktionen für Security, Audits, Support, Voice und Automatisierung.</p>
        </div>
        <div className="px-4 py-2 rounded-2xl bg-primary/10 border border-primary/20 text-primary text-sm font-black">
          {enabledCount}/20 aktiv
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {features.map((item) => (
          <div key={item.key} className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 flex items-center justify-between gap-5 shadow-xl hover:border-primary/30 transition-all">
            <div className="flex items-start gap-4 min-w-0">
              <div className="p-3 rounded-xl bg-primary/10 text-primary shrink-0"><item.icon className="h-5 w-5" /></div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-bold text-white">{item.title}</h3>
                  <span className="text-[9px] uppercase tracking-widest font-black text-slate-500 bg-slate-900/60 border border-slate-800 px-2 py-0.5 rounded-full">{item.group}</span>
                </div>
                <p className="text-sm text-slate-500 mt-1">{item.desc}</p>
              </div>
            </div>
            <Switch checked={values[item.key]} onCheckedChange={(checked) => setFeature(item.key, checked)} />
          </div>
        ))}
      </div>

      <Button onClick={save} disabled={saving} className="w-full h-14 text-base font-bold gap-2">
        {saving ? <RefreshCcw className="h-5 w-5 animate-spin" /> : <Save className="h-5 w-5" />}
        Speichern
      </Button>
    </div>
  );
}
