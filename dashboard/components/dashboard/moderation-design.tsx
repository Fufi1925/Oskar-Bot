import React from "react";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

export const moderationCard = "rounded-2xl border border-white/[.07] cloudtix-workspace-card bg-[#202124] p-4 sm:p-6";
export const moderationInput = "w-full rounded-xl border border-white/10 cloudtix-workspace-field bg-[#18191c] px-4 py-3 text-sm text-white outline-none transition focus:border-blue-400/40";

export function ModerationHeader({ icon: Icon, title, description, children }: {
  icon: React.ElementType; title: string; description: string; children?: React.ReactNode;
}) {
  return <header className="cloudtix-workspace-page-header space-y-5">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-white/15 bg-white/[.035] text-slate-300"><Icon className="h-5 w-5" /></span>
      <div className="min-w-0"><p className="cloudtix-workspace-eyebrow">Schutz und Moderation</p><h1 className="text-3xl font-semibold text-white">{title}</h1><p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-slate-400">{description}</p></div>
    </div>
    {children}
  </header>;
}

export function ModerationSection({ icon: Icon, title, subtitle, children, onReload, reloadDisabled }: any) {
  return <section className={cn(moderationCard, "space-y-5")}>
    <header className="flex items-start justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-400/10 text-blue-300"><Icon className="h-5 w-5" /></span>
        <div className="min-w-0"><h2 className="font-semibold text-white">{title}</h2>{subtitle && <p className="mt-1 text-sm leading-relaxed text-slate-400">{subtitle}</p>}</div>
      </div>
      {onReload && <button type="button" onClick={onReload} disabled={reloadDisabled} aria-label="Aktualisieren" title="Aktualisieren" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-white/10 text-slate-300 transition hover:bg-white/5 disabled:opacity-40"><RefreshCw className="h-4 w-4" /></button>}
    </header>
    {children}
  </section>;
}

export function ModerationTabs({ value, onChange, items, label }: {
  value: string; onChange: (value: string) => void; items: [string, string][]; label: string;
}) {
  return <nav aria-label={label} className="flex flex-wrap gap-2 rounded-2xl border border-white/[.07] cloudtix-workspace-card bg-[#202124] p-2">
    {items.map(([key, title]) => <button key={key} type="button" aria-pressed={value === key} onClick={() => onChange(key)} className={cn("min-h-11 rounded-xl px-4 py-2.5 text-sm transition-colors", value === key ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white")}>{title}</button>)}
  </nav>;
}

export function ModerationField({ label, hint, children }: any) {
  return <div className="space-y-2"><p className="text-sm font-medium text-slate-300">{label}</p>{children}{hint && <p className="text-xs leading-relaxed text-slate-500">{hint}</p>}</div>;
}
