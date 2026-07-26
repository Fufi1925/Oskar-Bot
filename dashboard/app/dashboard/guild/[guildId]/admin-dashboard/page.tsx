"use client";

import React, { useEffect, useState } from "react";
import { Shield, Save, RefreshCcw, Lock, Radar, ScanLine, ServerCog, Trash2, Link, Webhook, Bot, MessageSquareWarning, FileClock } from "lucide-react";
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
  | "dashboard_audit_log";

const features: Array<{ key: FeatureKey; title: string; desc: string; icon: any }> = [
  { key: "emergency_lockdown", title: "Emergency Lockdown", desc: "Prepare a one-click lockdown state for dangerous situations.", icon: Lock },
  { key: "anti_raid_watch", title: "Anti-Raid Watch", desc: "Track join spikes and suspicious member waves.", icon: Radar },
  { key: "auto_role_audit", title: "Auto Role Audit", desc: "Check if managed roles are still below the bot role.", icon: ServerCog },
  { key: "permission_scan", title: "Permission Scan", desc: "Scan channels and roles for risky permissions.", icon: ScanLine },
  { key: "inactive_channel_scan", title: "Inactive Channel Scan", desc: "Find unused channels that can be cleaned up.", icon: Trash2 },
  { key: "invite_security", title: "Invite Security", desc: "Monitor invite usage and suspicious invite patterns.", icon: Link },
  { key: "webhook_monitoring", title: "Webhook Monitoring", desc: "Watch webhook creation/deletion for abuse.", icon: Webhook },
  { key: "bot_role_guard", title: "Bot Role Guard", desc: "Warn when bot roles are moved into unsafe positions.", icon: Bot },
  { key: "mass_mention_guard", title: "Mass Mention Guard", desc: "Highlight channels where mass mentions may be abused.", icon: MessageSquareWarning },
  { key: "dashboard_audit_log", title: "Dashboard Audit Log", desc: "Log all important dashboard admin actions.", icon: FileClock },
];

export default function AdminDashboardPage({ params }: { params: { guildId: string } }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [values, setValues] = useState<Record<FeatureKey, boolean>>({
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
  });

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

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2"><Shield className="h-6 w-6 text-primary" />Admin Dashboard</h2>
        <p className="text-slate-400 mt-1">10 Premium Admin-Funktionen für Server-Sicherheit, Audits und Automatisierung.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {features.map((item) => (
          <div key={item.key} className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 flex items-center justify-between gap-5 shadow-xl">
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-xl bg-primary/10 text-primary"><item.icon className="h-5 w-5" /></div>
              <div>
                <h3 className="font-bold text-white">{item.title}</h3>
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
