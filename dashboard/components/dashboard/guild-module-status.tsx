"use client";

import React, { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { Check, Loader2, Power } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { GUILD_MODULE_LABELS_DE, GUILD_MODULE_LABELS_EN, guildModuleFromPath } from "@/lib/guild-modules";

export function GuildModuleStatus({ guildId }: { guildId: string }) {
  const pathname = usePathname();
  const { language } = useLanguage();
  const moduleKey = useMemo(() => guildModuleFromPath(pathname, guildId), [pathname, guildId]);
  const english = language === "en";
  const label = moduleKey ? (english ? GUILD_MODULE_LABELS_EN : GUILD_MODULE_LABELS_DE)[moduleKey] : "";
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    if (!moduleKey) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api.getGuildModuleState(guildId, moduleKey)
      .then((data) => { if (active) setEnabled(data.enabled !== false); })
      .catch((error: any) => {
        if (active) toast.error(error?.message || (english ? "The module status could not be loaded." : "Modulstatus konnte nicht geladen werden."));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [guildId, moduleKey, english]);

  const toggle = async () => {
    if (!moduleKey) return;
    const next = !enabled;
    setSaving(true);
    try {
      const data = await api.setGuildModuleState(guildId, moduleKey, next);
      setEnabled(data.enabled);
      window.dispatchEvent(new CustomEvent("guild-module-state", {
        detail: { guildId, module: moduleKey, enabled: data.enabled },
      }));
      toast.success(english
        ? `${label} was ${data.enabled ? "enabled" : "disabled"}.`
        : `${label} wurde ${data.enabled ? "aktiviert" : "deaktiviert"}.`);
    } catch (error: any) {
      toast.error(error?.message || (english ? "The module status could not be saved." : "Modulstatus konnte nicht gespeichert werden."));
    } finally {
      setSaving(false);
    }
  };

  if (!moduleKey) return null;

  if (loading) {
    return (
      <div className="flex min-h-[92px] items-center justify-center rounded-2xl border border-white/[.07] bg-[#111216]">
        <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
      </div>
    );
  }

  return (
    <section
      className={cn(
        "flex flex-col gap-4 rounded-2xl border px-5 py-5 sm:flex-row sm:items-center",
        enabled
          ? "border-emerald-400/25 bg-emerald-500/[.075]"
          : "border-rose-400/25 bg-rose-500/[.075]"
      )}
      aria-live="polite"
    >
      <div className="flex min-w-0 flex-1 items-center gap-4">
        <span className={cn(
          "grid h-12 w-12 shrink-0 place-items-center rounded-xl",
          enabled ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
        )}>
          {enabled ? <Check className="h-5 w-5" /> : <Power className="h-5 w-5" />}
        </span>
        <div className="min-w-0">
          <p className={cn("text-base font-bold", enabled ? "text-emerald-300" : "text-rose-300")}>
            {label} {enabled ? (english ? "enabled" : "aktiviert") : (english ? "disabled" : "deaktiviert")}
          </p>
          <p className={cn("mt-0.5 text-sm", enabled ? "text-emerald-400/65" : "text-rose-400/65")}>
            {enabled
              ? english ? "The function is active on this server." : "Die Funktion ist auf diesem Server aktiv."
              : english ? "The function will not run on this server." : "Die Funktion wird auf diesem Server nicht ausgeführt."}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={toggle}
        disabled={saving}
        className={cn(
          "h-12 shrink-0 rounded-xl px-6 text-sm font-bold transition disabled:cursor-wait disabled:opacity-60",
          enabled
            ? "border border-emerald-400/30 bg-emerald-500/[.08] text-emerald-300 hover:bg-emerald-500/15"
            : "bg-rose-500 text-white hover:bg-rose-400"
        )}
      >
        {saving
          ? english ? "Saving …" : "Speichern …"
          : enabled
            ? english ? "Disable" : "Deaktivieren"
            : english ? "Enable" : "Aktivieren"}
      </button>
    </section>
  );
}
