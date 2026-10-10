"use client";

import React, { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { Check, Loader2, Power } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { GUILD_MODULE_LABELS_DE, GUILD_MODULE_LABELS_EN, guildModuleFromPath } from "@/lib/guild-modules";

export function GuildModuleStatus({ guildId, children }: { guildId: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const { language } = useLanguage();
  const moduleKey = useMemo(() => guildModuleFromPath(pathname, guildId), [pathname, guildId]);
  const english = language === "en";
  const label = moduleKey ? (english ? GUILD_MODULE_LABELS_EN : GUILD_MODULE_LABELS_DE)[moduleKey] : "";
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [revision, setRevision] = useState(0);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!moduleKey) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(false);
    api.getGuildModuleState(guildId, moduleKey)
      .then((data) => {
        if (active) {
          setEnabled(data.enabled !== false);
          setLoadedPath(pathname);
          window.dispatchEvent(new CustomEvent("guild-module-state", {
            detail: { guildId, module: moduleKey, enabled: data.enabled !== false },
          }));
        }
      })
      .catch((error: any) => {
        if (active) {
          setLoadError(true);
          toast.error(error?.message || (english ? "The module status could not be loaded." : "Modulstatus konnte nicht geladen werden."));
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [guildId, moduleKey, pathname, english, revision]);

  useEffect(() => {
    const onState = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (String(detail?.guildId) === guildId && detail?.module === moduleKey) setEnabled(Boolean(detail.enabled));
    };
    window.addEventListener("guild-module-state", onState);
    return () => window.removeEventListener("guild-module-state", onState);
  }, [guildId, moduleKey]);

  const toggle = async () => {
    if (!moduleKey) return;
    if (loadError) {
      setRevision(value => value + 1);
      return;
    }
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

  if (!moduleKey) return <>{children}</>;

  if (loading || loadedPath !== pathname && !loadError) {
    return (
      <div className="flex min-h-[92px] items-center justify-center rounded-2xl border border-white/[.07] cloudtix-workspace-card bg-[#111216]">
        <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
      </div>
    );
  }

  if (loadError) {
    return <section className="flex items-center justify-between gap-4 rounded-2xl border border-white/10 cloudtix-workspace-card bg-[#202124] px-5 py-5">
      <p className="text-sm text-slate-400">{english ? "Module status unavailable." : "Modulstatus nicht verfügbar."}</p>
      <button type="button" onClick={toggle} className="rounded-xl border border-white/10 px-4 py-2 text-sm text-white">{english ? "Retry" : "Erneut laden"}</button>
    </section>;
  }

  return (
    <><div className="module-banner-position" style={{ paddingTop: enabled ? 0 : "clamp(3rem, 18vh, 10rem)" }}><section
      className={cn(
        "cloudtix-workspace-module-state mx-auto flex w-full flex-col gap-4 rounded-2xl border px-5 py-5 transition-all duration-500 sm:flex-row sm:items-center",
        enabled
          ? "border-emerald-400/25 bg-emerald-500/[.075]"
          : "max-w-3xl border-rose-400/25 bg-rose-500/[.075]"
      )}
      data-enabled={String(enabled)}
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
              ? english ? "The module is available. Its settings below determine how it runs." : "Das Modul ist freigegeben. Die Einstellungen darunter bestimmen, wie es ausgeführt wird."
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
    </section></div>
    {enabled && <div className="module-content-enter min-h-[400px]">{children}</div>}
    </>
  );
}
