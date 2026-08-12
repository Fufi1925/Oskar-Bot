"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Bell, Brush, Check, Command, Gauge, Info, Loader2, Lock, Music, RotateCcw,
  Save, Search, Shield, Terminal,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";

interface SettingEntry {
  key: string;
  label: string;
  group: string;
  description: string;
  effect: string;
  kind: "bool" | "number" | "text" | "choice";
  default: any;
  value: any;
  choices: string[];
  min: number;
  max: number;
}

const GROUP_ICONS: Record<string, any> = {
  Commands: Terminal,
  Moderation: Shield,
  Appearance: Brush,
  Music: Music,
  "Privacy & Safety": Lock,
};

// Settings that hold a Discord snowflake get a channel or role picker.
const CHANNEL_FIELDS = new Set(["mod_log_channel"]);
const ROLE_FIELDS = new Set(["dj_role"]);

export function GuildSettingsForm({
  guildId,
  prefix: initialPrefix,
  channels,
  roles,
}: {
  guildId: string;
  prefix: string;
  channels: Array<{ id: string; name: string }>;
  roles: Array<{ id: string; name: string }>;
}) {
  const [settings, setSettings] = useState<SettingEntry[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [prefix, setPrefix] = useState(initialPrefix);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [activeGroup, setActiveGroup] = useState("all");

  const load = async () => {
    try {
      const data = await api.getGuildBehaviour(guildId);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  const dirty = useMemo(
    () =>
      prefix !== initialPrefix ||
      settings.some((s) => String(draft[s.key] ?? "") !== String(s.value ?? "")),
    [draft, settings, prefix, initialPrefix]
  );

  const save = async () => {
    setSaving(true);
    try {
      const jobs: Promise<any>[] = [api.updateGuildBehaviour(guildId, draft)];
      if (prefix !== initialPrefix) {
        if (!prefix.trim() || prefix.length > 10) {
          toast.error("The prefix must be 1-10 characters.");
          setSaving(false);
          return;
        }
        jobs.push(api.updatePrefix(guildId, prefix.trim()));
      }
      await Promise.all(jobs);
      toast.success("Settings saved.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  const resetGroup = (group: string) => {
    const next = { ...draft };
    settings.filter((s) => s.group === group).forEach((s) => (next[s.key] = s.default));
    setDraft(next);
    toast.info(`${group} reset to defaults — remember to save.`);
  };

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return settings.filter((s) => {
      if (activeGroup !== "all" && s.group !== activeGroup) return false;
      if (!needle) return true;
      return (
        s.label.toLowerCase().includes(needle) ||
        s.description.toLowerCase().includes(needle) ||
        s.key.includes(needle)
      );
    });
  }, [settings, query, activeGroup]);

  const changedCount = settings.filter(
    (s) => String(draft[s.key] ?? "") !== String(s.default ?? "")
  ).length;

  // Distinct from changedCount above: that one counts "differs from the
  // default", this one counts "not saved yet", which is what the save bar
  // has to report.
  const unsavedCount =
    settings.filter((s) => String(draft[s.key] ?? "") !== String(s.value ?? ""))
      .length + (prefix !== initialPrefix ? 1 : 0);

  // Refuses to leave the tab while something is unsaved. Must sit above
  // the loading early-return -- a hook cannot be conditional.
  const guard = useSaveGuard(unsavedCount, "settings-save-bar");

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const renderField = (setting: SettingEntry) => {
    const value = draft[setting.key];
    const update = (v: any) => setDraft({ ...draft, [setting.key]: v });

    if (setting.kind === "bool") {
      return <Switch checked={Boolean(value)} onCheckedChange={update} />;
    }

    if (setting.kind === "choice") {
      return (
        <select
          value={String(value ?? setting.default)}
          onChange={(e) => update(e.target.value)}
          className="appearance-none bg-[#0a0a0c] border border-white/10 rounded-xl px-3 py-2 pr-9 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2024%2024%22%20stroke%3D%22%2394a3b8%22%20stroke-width%3D%222%22%3E%3Cpath%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20d%3D%22M19%209l-7%207-7-7%22/%3E%3C/svg%3E')] bg-[length:1.1rem] bg-[right_0.6rem_center] bg-no-repeat cursor-pointer min-w-[130px]"
        >
          {setting.choices.map((choice) => (
            <option key={choice} value={choice}>
              {choice === "none" ? "Nothing" : choice}
            </option>
          ))}
        </select>
      );
    }

    if (setting.kind === "number") {
      return (
        <input
          type="number"
          min={setting.min}
          max={setting.max || undefined}
          value={String(value ?? setting.default)}
          onChange={(e) => update(Number(e.target.value))}
          className="w-24 bg-white/[0.03] border border-white/5 rounded-xl px-3 py-2 text-sm text-white text-right focus:outline-none focus:ring-1 focus:ring-primary"
        />
      );
    }

    if (CHANNEL_FIELDS.has(setting.key)) {
      return (
        <select
          value={String(value ?? "")}
          onChange={(e) => update(e.target.value)}
          className="appearance-none bg-[#0a0a0c] border border-white/10 rounded-xl px-3 py-2 pr-9 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2024%2024%22%20stroke%3D%22%2394a3b8%22%20stroke-width%3D%222%22%3E%3Cpath%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20d%3D%22M19%209l-7%207-7-7%22/%3E%3C/svg%3E')] bg-[length:1.1rem] bg-[right_0.6rem_center] bg-no-repeat cursor-pointer min-w-[180px]"
        >
          <option value="">Disabled</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              #{c.name}
            </option>
          ))}
        </select>
      );
    }

    if (ROLE_FIELDS.has(setting.key)) {
      return (
        <select
          value={String(value ?? "")}
          onChange={(e) => update(e.target.value)}
          className="appearance-none bg-[#0a0a0c] border border-white/10 rounded-xl px-3 py-2 pr-9 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2024%2024%22%20stroke%3D%22%2394a3b8%22%20stroke-width%3D%222%22%3E%3Cpath%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20d%3D%22M19%209l-7%207-7-7%22/%3E%3C/svg%3E')] bg-[length:1.1rem] bg-[right_0.6rem_center] bg-no-repeat cursor-pointer min-w-[180px]"
        >
          <option value="">Everyone</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      );
    }

    if (setting.key === "embed_color") {
      const hex = String(value || "").replace("#", "");
      const valid = /^[0-9a-fA-F]{6}$/.test(hex);
      return (
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={valid ? `#${hex}` : "#5865F2"}
            onChange={(e) => update(e.target.value.replace("#", ""))}
            className="h-9 w-10 rounded-lg bg-transparent border border-white/10 cursor-pointer"
          />
          <input
            value={hex}
            onChange={(e) => update(e.target.value.replace("#", ""))}
            placeholder="5865F2"
            className="w-28 bg-white/[0.03] border border-white/5 rounded-xl px-3 py-2 text-sm text-white font-mono focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      );
    }

    return (
      <input
        value={String(value ?? "")}
        onChange={(e) => update(e.target.value)}
        placeholder={setting.key === "disabled_commands" ? "ban, kick, play" : "Empty"}
        className="w-56 bg-white/[0.03] border border-white/5 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
      />
    );
  };

  return (
    <div className="space-y-6">
      {/* Header with prefix and save */}
      <div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8">
        <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-6">
          <div className="flex-1">
            <h2 className="text-xl font-black text-white">Server settings</h2>
            <p className="text-sm text-slate-400 mt-1">
              {settings.length} options · {changedCount} changed from default
            </p>

            <div className="mt-6 max-w-xs">
              <span className="text-xs font-black uppercase tracking-widest text-slate-500">
                Command prefix
              </span>
              <div className="flex items-center gap-3 mt-2">
                <input
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                  maxLength={10}
                  className="w-28 bg-white/[0.03] border border-white/5 rounded-xl px-4 py-2.5 text-lg text-white font-mono font-bold text-center focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <span className="text-xs text-slate-500">
                  e.g. <code className="text-slate-400">{prefix || ">"}help</code>
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={save}
            disabled={saving || !dirty}
            className="flex items-center gap-2 px-8 py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 shrink-0"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {saving ? "Saving..." : dirty ? "Save changes" : "Saved"}
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="flex flex-col lg:flex-row gap-4">
        <label className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search settings..."
            className="w-full bg-white/[0.03] border border-white/5 rounded-2xl pl-11 pr-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        {["all", ...groups].map((group) => {
          const Icon = GROUP_ICONS[group] || Command;
          return (
            <button
              key={group}
              onClick={() => setActiveGroup(group)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all",
                activeGroup === group
                  ? "bg-primary text-white"
                  : "bg-white/[0.03] text-slate-400 hover:text-white hover:bg-white/[0.06]"
              )}
            >
              {group !== "all" && <Icon className="h-3.5 w-3.5" />}
              {group === "all" ? `All (${settings.length})` : group}
            </button>
          );
        })}
      </div>

      {/* Settings grouped */}
      {(activeGroup === "all" ? groups : [activeGroup]).map((group) => {
        const items = visible.filter((s) => s.group === group);
        if (!items.length) return null;
        const Icon = GROUP_ICONS[group] || Command;

        return (
          <div key={group} className="bg-[#131318] border border-slate-800 rounded-3xl overflow-hidden border-glow-card is-clipped">
            <div className="px-8 py-5 border-b border-white/5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Icon className="h-5 w-5 text-primary" />
                <h3 className="font-black text-white">{group}</h3>
              </div>
              <button
                onClick={() => resetGroup(group)}
                className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-slate-600 hover:text-slate-300 transition-colors"
              >
                <RotateCcw className="h-3 w-3" />
                Defaults
              </button>
            </div>

            <div className="divide-y divide-white/5">
              {items.map((setting) => {
                const changed = String(draft[setting.key] ?? "") !== String(setting.default ?? "");
                return (
                  <div
                    key={setting.key}
                    className="px-8 py-5 flex items-start justify-between gap-6 hover:bg-white/[0.01] transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-white">{setting.label}</span>
                        {changed && (
                          <span className="text-[9px] font-black uppercase tracking-widest text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded">
                            changed
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{setting.description}</p>
                      <p className="text-[11px] text-slate-600 mt-1.5 leading-relaxed">
                        {setting.effect}
                      </p>
                    </div>

                    <div className="shrink-0 pt-0.5">{renderField(setting)}</div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {visible.length === 0 && (
        <p className="text-center text-slate-500 py-12">No settings match your search.</p>
      )}

      <div className="flex gap-3 p-5 bg-white/[0.02] border border-white/5 rounded-3xl">
        <Info className="h-5 w-5 text-slate-500 shrink-0" />
        <p className="text-xs text-slate-400 leading-relaxed">
          Every option here changes how the bot behaves on this server — the text under
          each one says exactly what it does. Changes apply immediately after saving,
          no restart needed.
        </p>
      </div>

      {/* The header save button scrolls out of sight on a long list, so an
          unsaved change would be easy to lose. This bar follows along and
          only appears when there is actually something to save. */}
      <StickySaveBar
        id="settings-save-bar"
        count={unsavedCount}
        busy={saving}
        shake={guard.shake}
        onDiscard={() => {
          setDraft(Object.fromEntries(settings.map((s) => [s.key, s.value])));
          setPrefix(initialPrefix);
        }}
        onSave={save}
      />
    </div>
  );
}
