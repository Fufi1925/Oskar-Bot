"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Clock, Crown, Loader2, Server, ShoppingCart, User } from "lucide-react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const PLANS = [
  { days: 30, label: "30 Tage" },
  { days: 90, label: "90 Tage" },
  { days: 365, label: "365 Tage" },
];
const fmt = (value?: number | null) => value ? new Date(value * 1000).toLocaleString("de-DE") : "–";

export function PremiumPanel() {
  const { data: session } = useSession();
  const userId = session?.user?.id || "";
  const [status, setStatus] = useState<any>(null);
  const [servers, setServers] = useState<any[]>([]);
  const [plan, setPlan] = useState(30);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const [mine, choices] = await Promise.all([api.getMyPremium(userId), api.premiumCodeServers()]);
      setStatus(mine.premium);
      setServers(choices.servers || []);
    } catch (error: any) { toast.error(error?.message || "Premium konnte nicht geladen werden."); }
    finally { setLoading(false); }
  }, [userId]);
  useEffect(() => { load(); }, [load]);

  const used = status?.slots || [];
  const available = useMemo(() => servers.filter(server => !used.some((slot: any) => String(slot.guild_id) === server.id)), [servers, used]);

  const requestPurchase = async () => {
    setBusy(true);
    try { const result = await api.requestPremiumPurchase(plan); toast.success(result.already ? "Deine Kaufanfrage wartet bereits auf Bearbeitung." : "Kaufanfrage wurde an das Team gesendet."); }
    catch (error: any) { toast.error(error?.message || "Kaufanfrage fehlgeschlagen."); }
    finally { setBusy(false); }
  };
  const assign = async () => {
    if (!selected) return toast.error("Bitte einen Server auswählen.");
    if (!confirm("Dieser Premium-Platz bleibt bis zum Ablauf fest an den Server gebunden. Wirklich einlösen?")) return;
    setBusy(true);
    try { await api.assignPremiumSlot(selected); toast.success("Server-Premium wurde fest zugewiesen."); setSelected(""); await load(); }
    catch (error: any) { toast.error(error?.message || "Premium-Platz konnte nicht eingelöst werden."); }
    finally { setBusy(false); }
  };

  if (loading) return <div className="grid min-h-60 place-items-center"><Loader2 className="h-7 w-7 animate-spin text-amber-400" /></div>;
  return <div className="space-y-5">
    <section className="rounded-3xl border border-amber-400/20 bg-gradient-to-br from-amber-500/[0.1] to-[#0e0e12] p-5 sm:p-6">
      <div className="flex items-center gap-3"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-amber-400/15"><User className="h-5 w-5 text-amber-300" /></span><div className="min-w-0"><p className="text-xs font-bold uppercase tracking-wider text-amber-300">Discord-Konto</p><h2 className="truncate text-xl font-black text-white">{session?.user?.name || userId}</h2><p className="text-xs text-slate-500">{userId}</p></div></div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-white/5 bg-black/20 p-4"><p className="text-[10px] uppercase text-slate-500">Kontostatus</p><p className={cn("mt-1 font-black", status?.premium ? "text-emerald-300" : "text-slate-400")}>{status?.premium ? "Premium aktiv" : "Kein Premium"}</p></div><div className="rounded-xl border border-white/5 bg-black/20 p-4"><p className="text-[10px] uppercase text-slate-500">Laufzeit</p><p className="mt-1 font-black text-white">{fmt(status?.expires_at)}</p></div><div className="rounded-xl border border-white/5 bg-black/20 p-4"><p className="text-[10px] uppercase text-slate-500">Serverplätze</p><p className="mt-1 font-black text-white">{used.length} / 3 belegt</p></div></div>
    </section>

    <section className="rounded-2xl border border-slate-800 bg-[#131318] p-5"><div className="flex items-center gap-3"><ShoppingCart className="text-amber-400"/><div><h3 className="font-black text-white">Premium kaufen</h3><p className="text-xs text-slate-400">Wähle ein Paket. Das Team prüft und bestätigt deine Kaufanfrage.</p></div></div><div className="mt-4 grid gap-2 sm:grid-cols-3">{PLANS.map(item=><button key={item.days} onClick={()=>setPlan(item.days)} className={cn("rounded-xl border p-4 text-left",plan===item.days?"border-amber-400/40 bg-amber-400/10":"border-slate-800")}><Clock className="h-4 w-4 text-amber-400"/><p className="mt-2 font-black text-white">{item.label}</p><p className="text-[11px] text-slate-500">3 feste Premium-Server</p></button>)}</div><button disabled={busy} onClick={requestPurchase} className="mt-4 w-full rounded-xl bg-amber-400 py-3 text-sm font-black text-black disabled:opacity-40">Kaufanfrage senden</button></section>

    <section className="rounded-2xl border border-violet-500/20 bg-[#131318] p-5"><div className="flex items-center gap-3"><Crown className="text-violet-300"/><div><h3 className="font-black text-white">Deine drei Premium-Server</h3><p className="text-xs text-slate-400">Premium gilt ausschließlich auf den hier fest zugewiesenen Servern. Andere Dashboard-Nutzer dürfen dort alle freigegebenen Einstellungen verwalten.</p></div></div><div className="mt-4 grid gap-3 sm:grid-cols-3">{[1,2,3].map(slot=>{const value=used.find((item:any)=>item.slot_no===slot);const guild=servers.find(s=>s.id===String(value?.guild_id));return <div key={slot} className={cn("rounded-xl border p-4",value?"border-violet-500/25 bg-violet-500/[0.06]":"border-dashed border-slate-700")}><p className="text-[10px] font-black uppercase text-slate-500">Platz {slot}</p>{value?<><p className="mt-2 truncate font-bold text-white">{guild?.name || value.guild_id}</p><p className="mt-1 flex items-center gap-1 text-[11px] text-emerald-300"><Check className="h-3 w-3"/>Fest zugewiesen</p></>:<p className="mt-2 text-sm text-slate-500">Noch frei</p>}</div>})}</div>
      {status?.premium && used.length < 3 && <div className="mt-4 flex flex-col gap-2 sm:flex-row"><select value={selected} onChange={e=>setSelected(e.target.value)} className="min-w-0 flex-1 rounded-xl border border-slate-700 bg-[#09090c] px-4 py-3 text-sm text-white"><option value="">Server auswählen …</option>{available.map(server=><option key={server.id} value={server.id}>{server.name}</option>)}</select><button disabled={busy||!selected} onClick={assign} className="rounded-xl bg-violet-500 px-5 py-3 text-sm font-black text-white disabled:opacity-40"><Server className="mr-2 inline h-4 w-4"/>Premium fest einlösen</button></div>}
    </section>
  </div>;
}
