/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║           © 2026 University Bot Devs — All Rights Reserved       ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

import React, { useState } from "react";
import { Save, RefreshCcw, Command, Info, Trash2, MessageCircle, Volume2, Shield, Bell, FileText, Lock, Gauge, UserCog, Brush } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

interface SettingsFormProps {
  initialPrefix: string;
  initialExtraSettings?: Record<string, boolean>;
  initialFeatureSettings?: Record<string, boolean>;
  guildId: string;
}

type FeatureKey =
  | "delete_command_messages"
  | "mention_prefix_response"
  | "same_voice_only"
  | "auto_cleanup_invites"
  | "compact_embeds"
  | "dm_mod_actions"
  | "log_dashboard_changes"
  | "require_reason_moderation"
  | "auto_slowmode_alerts"
  | "protect_admin_roles";

const featureMeta: Array<{ key: FeatureKey; title: string; desc: string; icon: any }> = [
  { key: "delete_command_messages", title: "Delete command messages", desc: "Automatically delete user command messages after execution.", icon: Trash2 },
  { key: "mention_prefix_response", title: "Mention prefix response", desc: "Reply with the configured prefix when somebody mentions the bot.", icon: MessageCircle },
  { key: "same_voice_only", title: "Same voice channel only", desc: "Music controls should only work for users in the same voice channel.", icon: Volume2 },
  { key: "auto_cleanup_invites", title: "Auto cleanup invite links", desc: "Prepare invite cleanup rules for moderation modules.", icon: Shield },
  { key: "compact_embeds", title: "Compact bot embeds", desc: "Use smaller dashboard/bot embed layouts where supported.", icon: Brush },
  { key: "dm_mod_actions", title: "DM moderation actions", desc: "Send a direct message when moderation actions are executed.", icon: Bell },
  { key: "log_dashboard_changes", title: "Log dashboard changes", desc: "Keep an audit trail for configuration changes made in the dashboard.", icon: FileText },
  { key: "require_reason_moderation", title: "Require moderation reason", desc: "Require staff to provide a reason for moderation actions.", icon: UserCog },
  { key: "auto_slowmode_alerts", title: "Auto slowmode alerts", desc: "Warn staff when channels may need slowmode during spam waves.", icon: Gauge },
  { key: "protect_admin_roles", title: "Protect admin roles", desc: "Mark administrator roles as protected for safety checks.", icon: Lock },
];

export function SettingsForm({ initialPrefix, initialExtraSettings, initialFeatureSettings, guildId }: SettingsFormProps) {
  const [prefix, setPrefix] = useState(initialPrefix);
  const [features, setFeatures] = useState<Record<FeatureKey, boolean>>(() => {
    const merged = { ...(initialFeatureSettings || {}), ...(initialExtraSettings || {}) } as Record<FeatureKey, boolean>;
    return {
      delete_command_messages: Boolean(merged.delete_command_messages),
      mention_prefix_response: merged.mention_prefix_response ?? true,
      same_voice_only: merged.same_voice_only ?? true,
      auto_cleanup_invites: Boolean(merged.auto_cleanup_invites),
      compact_embeds: Boolean(merged.compact_embeds),
      dm_mod_actions: Boolean(merged.dm_mod_actions),
      log_dashboard_changes: merged.log_dashboard_changes ?? true,
      require_reason_moderation: Boolean(merged.require_reason_moderation),
      auto_slowmode_alerts: Boolean(merged.auto_slowmode_alerts),
      protect_admin_roles: merged.protect_admin_roles ?? true,
    };
  });
  const [saving, setSaving] = useState(false);

  const setFeature = (key: FeatureKey, value: boolean) => setFeatures((prev) => ({ ...prev, [key]: value }));

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prefix || prefix.length > 10) {
      toast.error("Prefix must be between 1 and 10 characters.");
      return;
    }

    setSaving(true);
    const promise = Promise.all([
      api.updatePrefix(guildId, prefix),
      api.updateExtraSettings(guildId, {
        delete_command_messages: features.delete_command_messages,
        mention_prefix_response: features.mention_prefix_response,
        same_voice_only: features.same_voice_only,
      }),
      api.updateSettingsFeatures(guildId, features),
    ]);

    toast.promise(promise, {
      loading: "Updating settings...",
      success: "Settings updated successfully!",
      error: (err) => err.message || "Failed to update settings",
    });

    try { await promise; } finally { setSaving(false); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div className="lg:col-span-2 space-y-6">
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden shadow-xl shadow-black/20">
          <div className="p-8 space-y-8">
            <form onSubmit={handleSave} className="space-y-8">
              <div className="space-y-2">
                <label className="text-sm font-black uppercase text-slate-500 tracking-widest flex items-center gap-2">
                  <Command className="h-4 w-4" /> Command Prefix
                </label>
                <div className="relative group">
                  <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="e.g. !, ?, >>" maxLength={10} className="text-lg font-bold pr-20 py-7" />
                  <div className="absolute right-4 top-1/2 -translate-y-1/2 text-xs font-mono text-slate-600 group-focus-within:text-primary transition-colors">{prefix.length}/10</div>
                </div>
                <p className="text-xs text-slate-500 italic">This character triggers bot commands (e.g. {prefix || ">"}help)</p>
              </div>

              <div className="space-y-4">
                <h3 className="text-sm font-black uppercase text-slate-500 tracking-widest">10 Settings Functions</h3>
                <div className="grid grid-cols-1 gap-4">
                  {featureMeta.map((item) => (
                    <div key={item.key} className="flex items-center justify-between gap-4 bg-slate-900/40 border border-slate-800 rounded-2xl p-5">
                      <div className="flex items-start gap-4">
                        <div className="p-3 rounded-xl bg-primary/10 text-primary"><item.icon className="h-5 w-5" /></div>
                        <div><p className="font-bold text-white">{item.title}</p><p className="text-sm text-slate-500 mt-1">{item.desc}</p></div>
                      </div>
                      <Switch checked={features[item.key]} onCheckedChange={(checked) => setFeature(item.key, checked)} />
                    </div>
                  ))}
                </div>
              </div>

              <Button type="submit" disabled={saving || !prefix} className="w-full h-14 text-base font-bold gap-2 shadow-primary/20">
                {saving ? <RefreshCcw className="h-5 w-5 animate-spin" /> : <Save className="h-5 w-5" />}
                {saving ? "Saving Changes..." : "Save Configuration"}
              </Button>
            </form>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 opacity-[0.03] group-hover:scale-110 transition-transform"><Info className="h-32 w-32 text-white" /></div>
          <h3 className="text-sm font-black uppercase text-slate-500 tracking-widest mb-4 flex items-center gap-2"><Info className="h-4 w-4" />Information</h3>
          <div className="space-y-4 text-sm leading-relaxed text-slate-400">
            <p>The <span className="text-white font-bold italic">Prefix</span> is a unique identifier that tells the bot to process text as a command.</p>
            <p>This tab now includes 10 configurable server functions. Core options are wired into the bot, and the others are stored for dashboard/admin automation.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
