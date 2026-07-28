"use client";

import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Link2, Loader2, Search, Sliders } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";

export interface FeatureFlagDetail {
  key: string;
  label: string;
  category: string;
  description: string;
  effect: string;
  requires: string[];
  default: boolean;
  enabled: boolean;
  /** false when a dependency is switched off */
  active: boolean;
  rollout_percent: number;
}

export function FeatureFlagsPanel() {
  const [features, setFeatures] = useState<FeatureFlagDetail[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("all");
  // Where the slider is right now, before the request comes back.
  const [rolloutDraft, setRolloutDraft] = useState<Record<string, number>>({});

  const load = async () => {
    try {
      const data = await api.getAdminFeaturesDetail();
      setFeatures(data.features || []);
      setCategories(data.categories || []);
      setRolloutDraft({});
    } catch (err: any) {
      toast.error(err?.message || "Could not load feature flags.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const toggle = async (flag: FeatureFlagDetail, value: boolean) => {
    setPending(flag.key);
    // Optimistic update; reverted by the reload if the request fails.
    setFeatures((prev) =>
      prev.map((f) => (f.key === flag.key ? { ...f, enabled: value, active: value } : f))
    );
    try {
      await api.updateAdminFeatures({ [flag.key]: value });
      toast.success(`${flag.label} ${value ? "enabled" : "disabled"}`);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Update failed.");
      await load();
    } finally {
      setPending(null);
    }
  };

  const setRollout = async (flag: FeatureFlagDetail, percent: number) => {
    setPending(flag.key);
    try {
      await api.updateFeatureRollout(flag.key, percent);
      toast.success(`${flag.label}: rollout set to ${percent}%`);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Rollout update failed.");
    } finally {
      setPending(null);
    }
  };

  const rolloutsEnabled = features.find((f) => f.key === "feature_flag_rollouts")?.active ?? false;

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return features.filter((flag) => {
      if (activeCategory !== "all" && flag.category !== activeCategory) return false;
      if (!needle) return true;
      return (
        flag.label.toLowerCase().includes(needle) ||
        flag.key.toLowerCase().includes(needle) ||
        flag.description.toLowerCase().includes(needle)
      );
    });
  }, [features, query, activeCategory]);

  const enabledCount = features.filter((f) => f.active).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="glass border border-white/5 rounded-[2rem] p-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
              <Sliders className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h3 className="text-xl font-black text-white">Global Feature Flags</h3>
              <p className="text-sm text-slate-400 mt-1">
                {enabledCount} of {features.length} features active. Changes apply immediately — no restart needed.
              </p>
            </div>
          </div>

          <label className="relative w-full lg:w-72">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search features..."
              className="w-full bg-white/[0.03] border border-white/5 rounded-2xl pl-11 pr-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-2 mt-6">
          {["all", ...categories].map((category) => (
            <button
              key={category}
              onClick={() => setActiveCategory(category)}
              className={cn(
                "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all",
                activeCategory === category
                  ? "bg-primary text-white"
                  : "bg-white/[0.03] text-slate-400 hover:text-white hover:bg-white/[0.06]"
              )}
            >
              {category === "all" ? `All (${features.length})` : category}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {visible.map((flag) => {
          const blockedBy = flag.enabled && !flag.active ? flag.requires : [];
          return (
            <div
              key={flag.key}
              className={cn(
                "bg-[#10233f] border rounded-3xl p-6 transition-all",
                flag.active ? "border-primary/25" : "border-slate-800"
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-black text-white">{flag.label}</h4>
                    {flag.default !== flag.enabled && (
                      <span className="text-[9px] font-black uppercase tracking-widest text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-md">
                        Changed
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-400 mt-2">{flag.description}</p>
                  <p className="text-xs text-slate-500 mt-3 leading-relaxed">
                    <span className="font-black uppercase tracking-widest text-[9px] text-slate-600">
                      Effect
                    </span>
                    <br />
                    {flag.effect}
                  </p>

                  {flag.requires.length > 0 && (
                    <p className="text-[10px] uppercase tracking-widest text-slate-600 mt-3 flex items-center gap-1.5">
                      <Link2 className="h-3 w-3" />
                      Requires: {flag.requires.join(", ")}
                    </p>
                  )}

                  {blockedBy.length > 0 && (
                    <p className="text-[11px] text-amber-400 mt-3 flex items-center gap-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                      Inactive: dependency is switched off.
                    </p>
                  )}

                  <code className="block text-[10px] text-slate-600 mt-3 font-mono">{flag.key}</code>
                </div>

                <Switch
                  checked={flag.enabled}
                  disabled={pending === flag.key}
                  onCheckedChange={(value: boolean) => toggle(flag, value)}
                />
              </div>

              {rolloutsEnabled && flag.active && (
                <div className="mt-5 pt-5 border-t border-white/5">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">
                      Rollout
                    </span>
                    <span className="text-xs font-bold text-primary">
                      {rolloutDraft[flag.key] ?? flag.rollout_percent}%
                    </span>
                  </div>
                  {/* The number beside the slider read flag.rollout_percent
                      while the slider itself was uncontrolled
                      (defaultValue), so dragging moved the handle and left
                      the number on the old value until the request came
                      back. Worse, the change was only sent on mouse-up:
                      dragging with the keyboard set nothing at all. */}
                  <input
                    type="range"
                    min={0}
                    max={100}
                    step={10}
                    value={rolloutDraft[flag.key] ?? flag.rollout_percent}
                    disabled={pending === flag.key}
                    onChange={(e) =>
                      setRolloutDraft((d) => ({
                        ...d,
                        [flag.key]: Number(e.target.value),
                      }))
                    }
                    onMouseUp={(e) => setRollout(flag, Number((e.target as HTMLInputElement).value))}
                    onTouchEnd={(e) => setRollout(flag, Number((e.target as HTMLInputElement).value))}
                    onKeyUp={(e) => setRollout(flag, Number((e.target as HTMLInputElement).value))}
                    className="w-full accent-primary"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {visible.length === 0 && (
        <p className="text-center text-slate-500 py-12">No features match your filter.</p>
      )}
    </section>
  );
}
