import Link from "next/link";
import { ChevronRight, Gem, LayoutDashboard, LifeBuoy, Server } from "lucide-react";
import { SUPPORT_INVITE } from "@/lib/legal";

const actions = [
  { label: "Dashboard", hint: "Zur persönlichen Übersicht", href: "/dashboard", icon: LayoutDashboard, color: "text-indigo-400" },
  { label: "Meine Server", hint: "Server auswählen und verwalten", href: "/dashboard/guilds", icon: Server, color: "text-cyan-400" },
  { label: "Premium", hint: "Status ansehen oder Key einlösen", href: "/dashboard/premium", icon: Gem, color: "text-amber-400" },
  { label: "Support", hint: "Hilfe auf unserem Discord-Server", href: SUPPORT_INVITE, icon: LifeBuoy, color: "text-emerald-400", external: true },
] as const;

export function AccountActions() {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]">
      <div className="border-b border-slate-800 px-5 py-4 sm:px-6">
        <h2 className="text-lg font-bold text-white">Schnellzugriff</h2>
        <p className="mt-1 text-sm text-slate-500">Die wichtigsten Bereiche für dein Konto.</p>
      </div>
      <div className="divide-y divide-slate-800">
        {actions.map(({ label, hint, href, icon: Icon, color, ...action }) => {
          const content = <><span className="grid h-10 w-10 place-items-center rounded-xl bg-white/[0.04]"><Icon className={`h-5 w-5 ${color}`} /></span><span className="min-w-0 flex-1"><span className="block font-semibold text-slate-100">{label}</span><span className="mt-0.5 block text-sm text-slate-500">{hint}</span></span><ChevronRight className="h-5 w-5 text-slate-600" /></>;
          const classes = "flex items-center gap-4 px-5 py-4 transition-colors hover:bg-white/[0.025] sm:px-6";
          return "external" in action && action.external ? <a key={label} href={href} target="_blank" rel="noopener noreferrer" className={classes}>{content}</a> : <Link key={label} href={href} className={classes}>{content}</Link>;
        })}
      </div>
    </section>
  );
}
