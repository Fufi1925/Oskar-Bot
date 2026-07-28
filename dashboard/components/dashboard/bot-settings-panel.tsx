"use client";

import React, { useEffect, useState } from "react";
import { Info, Loader2, Lock, Save, Sliders } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";

interface SettingEntry {
  key: string;
  label: string;
  group: string;
  description: string;
  kind: "channel" | "text" | "bool" | "number";
  default: string;
  value: string;
  effective: string;
  env_var: string;
  env_override: boolean;
}

/**
 * Settings that used to be hardcoded in university_bot.py — the stats
 * channels, the join/leave log and a few branding values.
 */
export function BotSettingsPanel() {
  const [settings, setSettings] = useState<SettingEntry[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const data = await api.getBotSettings();
      setSettings(data.settings || []);
      setGroups(data.groups || []);
      setDraft(
        Object.fromEntries((data.settings || []).map((s: SettingEntry) => [s.key, s.value]))
      );
    } catch (err: any) {
      toast.error(err?.message || "Could not load the settings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.updateBotSettings(draft);
      toast.success("Settings saved.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  // Count the fields, not just "is anything different" -- the bar says
  // how many, and one number is the difference between "did I change
  // that?" and knowing.
  const dirtyCount = settings.filter(
    (s) => (draft[s.key] ?? "") !== s.value
  ).length;
  const dirty = dirtyCount > 0;

  // Refuses to leave the tab while something is unsaved. Above the
  // loading early-return: a hook cannot be conditional.
  const guard = useSaveGuard(dirtyCount, "botsettings-save-bar");

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
              <Sliders className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h3 className="text-xl font-black text-white">Bot Settings</h3>
              <p className="text-sm text-slate-400 mt-1">
                Values that were previously hardcoded in the source.
              </p>
            </div>
          </div>

          <button
            onClick={save}
            disabled={saving || !dirty}
            className="flex items-center gap-2 px-6 py-3 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40"
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving..." : dirty ? "Save changes" : "Saved"}
          </button>
        </div>
      </div>

      {groups.map((group) => (
        <div key={group} className="bg-[#10233f] border border-slate-800 rounded-3xl p-8">
          <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-600 mb-6">
            {group}
          </p>

          <div className="space-y-6">
            {settings
              .filter((s) => s.group === group)
              .map((setting) => (
                <div key={setting.key}>
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="text-sm font-bold text-white">{setting.label}</span>
                    {setting.env_override && (
                      <span
                        className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-amber-400/10 text-amber-400 border border-amber-400/20 flex items-center gap-1"
                        title={`Set through the ${setting.env_var} environment variable`}
                      >
                        <Lock className="h-2.5 w-2.5" />
                        env
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mb-3 leading-relaxed">
                    {setting.description}
                  </p>

                  {setting.kind === "bool" ? (
                    <label className="flex items-center gap-3 cursor-pointer w-fit">
                      <input
                        type="checkbox"
                        checked={(draft[setting.key] ?? "").toLowerCase() === "true"}
                        disabled={setting.env_override}
                        onChange={(e) =>
                          setDraft({ ...draft, [setting.key]: e.target.checked ? "true" : "false" })
                        }
                        className="accent-primary h-4 w-4"
                      />
                      <span className="text-sm text-slate-300">Enabled</span>
                    </label>
                  ) : (
                    <input
                      value={draft[setting.key] ?? ""}
                      disabled={setting.env_override}
                      onChange={(e) => setDraft({ ...draft, [setting.key]: e.target.value })}
                      placeholder={
                        setting.kind === "channel"
                          ? "Channel ID, e.g. 123456789012345678"
                          : setting.default || "Leave empty to disable"
                      }
                      inputMode={setting.kind === "number" ? "numeric" : "text"}
                      className={cn(
                        "w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary",
                        setting.env_override && "opacity-50 cursor-not-allowed"
                      )}
                    />
                  )}

                  {setting.env_override && (
                    <p className="text-[11px] text-amber-400/70 mt-2">
                      Currently{" "}
                      <code className="font-mono">{setting.effective || "(empty)"}</code> from{" "}
                      <code className="font-mono">{setting.env_var}</code>. Remove the variable to
                      edit it here.
                    </p>
                  )}
                </div>
              ))}
          </div>
        </div>
      ))}

      <StickySaveBar
        id="botsettings-save-bar"
        count={dirtyCount}
        busy={saving}
        shake={guard.shake}
        onDiscard={() =>
          setDraft(Object.fromEntries(settings.map((s) => [s.key, s.value])))
        }
        onSave={save}
      />

      <div className="flex gap-3 p-5 bg-white/[0.02] border border-white/5 rounded-3xl">
        <Info className="h-5 w-5 text-slate-500 shrink-0" />
        <p className="text-xs text-slate-400 leading-relaxed">
          Channel IDs: enable Developer Mode in Discord, then right-click a channel and pick
          &quot;Copy Channel ID&quot;. Discord rate limits channel renames to about twice per
          10 minutes, so keep the stats interval at 600 seconds or higher.
        </p>
      </div>
    </section>
  );
}
