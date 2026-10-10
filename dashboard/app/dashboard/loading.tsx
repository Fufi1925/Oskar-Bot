import { Loader2 } from "lucide-react";

export default function DashboardLoading() {
  return <div role="status" className="flex min-h-[60vh] flex-col items-center justify-center gap-5 text-center"><span className="grid h-14 w-14 place-items-center rounded-2xl border border-white/15 bg-[#111111]"><Loader2 size={23} className="animate-spin text-slate-300" /></span><div><p className="text-lg font-semibold text-white">Dein Workspace wird geladen.</p><p className="mt-2 text-xs text-slate-500">Einen Moment – deine Übersicht ist gleich bereit.</p></div></div>;
}
