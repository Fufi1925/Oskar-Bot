"use client";

import { useCallback } from "react";
import { DoorOpen } from "lucide-react";
import { api } from "@/lib/api";
import { Loading, usePanel } from "@/components/dashboard/save-bar";
import { WelcomeForm } from "@/components/dashboard/welcome-form";

export function LeaveForm({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getGreetExtras(guildId), [guildId]);
  const p = usePanel(load);
  if (p.loading) return <Loading />;
  if (!p.data) return <section className="rounded-2xl border border-white/10 cloudtix-workspace-card bg-[#202124] p-6 space-y-3"><DoorOpen className="h-5 w-5 text-slate-400" /><p className="text-sm text-slate-300">Abschiedseinstellungen konnten nicht geladen werden.</p><button onClick={p.reload} className="text-sm text-blue-300">Erneut laden</button></section>;
  const payload = (config: any) => ({
    leave_channel_id: config.channel_id || "", leave_message: config.welcome_message || "",
    leave_type: config.welcome_type || "simple", leave_embed_data: config.embed_data || {},
    leave_auto_delete_duration: config.auto_delete_duration || 0,
    leave_image_enabled: !!config.image_enabled, leave_image_url: config.image_url?.trim() || "",
  });
  return <WelcomeForm guildId={guildId} kind="leave" initialConfig={{
    guild_id: Number(guildId), channel_id: p.data.leave_channel_id || "",
    welcome_type: p.data.leave_type || "simple", welcome_message: p.data.leave_message || "**{user.display}** hat den Server verlassen.",
    embed_data: p.data.leave_embed_data || {}, auto_delete_duration: p.data.leave_auto_delete_duration || 0,
    image_enabled: p.data.leave_image_enabled, image_url: p.data.leave_image_url || "",
  }} onSaveConfig={async config => { await api.saveGreetExtras(guildId, payload(config)); }} onTestConfig={config => api.testLeave(guildId, payload(config))} />;
}
