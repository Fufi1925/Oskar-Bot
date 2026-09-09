"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Crown, Loader2, RefreshCw, Search, Server } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Guild = {
  guild_id: string;
  name: string;
  icon: string | null;
  members: number;
  premium: boolean;
};

export function PremiumGuilds() {
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("Zeitüberschreitung beim Laden der Server.")), 12000);
      });
      const result = await Promise.race([api.getPremiumGuilds(), timeout]);
      setGuilds(result.guilds || []);
    } catch (err: any) {
      setError(err?.message || "Premium-Server konnten nicht geladen werden.");
    } finally {
      if (timer) clearTimeout(timer);
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return guilds.filter((guild) => !query || guild.name.toLowerCase().includes(query) || guild.guild_id.includes(query));
  }, [guilds, search]);

  const toggle = async (guild: Guild) => {
    const next = !guild.premium;
    if (!next && !confirm(`Server-Premium für „${guild.name}“ wirklich entziehen?`)) return;
    setBusy(guild.guild_id);
    try {
      await api.setGuildPremium(guild.guild_id, next);
      setGuilds((current) => current.map((item) => item.guild_id === guild.guild_id ? { ...item, premium: next } : item));
      toast.success(next ? `${guild.name} hat jetzt Server-Premium.` : `${guild.name} hat kein Server-Premium mehr.`);
    } catch (err: any) {
      toast.error(err?.message || "Premiumstatus konnte nicht geändert werden.");
    } finally {
      setBusy(null);
    }
  };

  const active = guilds.filter((guild) => guild.premium).length;

  return (
    <div className="space-y-4">
      <section className="rounded-3xl border border-amber-400/20 bg-[#111116] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-amber-400/10 text-amber-300"><Crown className="h-5 w-5" /></span>
            <div><h3 className="font-black text-white">Server-Premium</h3><p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500">Vergib oder entziehe Premium direkt für einzelne Discord-Server. Die Änderung gilt sofort für alle servergebundenen Premium-Funktionen.</p></div>
          </div>
          <button onClick={load} disabled={loading} className="inline-flex items-center gap-2 rounded-xl border border-slate-800 px-3 py-2 text-xs font-bold text-slate-400 hover:text-white disabled:opacity-40"><RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> Aktualisieren</button>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-amber-400/15 bg-amber-400/[0.04] p-4"><p className="text-[10px] font-black uppercase tracking-wider text-slate-500">Premium-Server</p><p className="mt-1 text-2xl font-black text-amber-300">{active}</p></div>
          <div className="rounded-2xl border border-slate-800 bg-black/20 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-slate-500">Server gesamt</p><p className="mt-1 text-2xl font-black text-white">{guilds.length}</p></div>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-800 bg-[#131318] p-4 sm:p-5">
        <div className="relative"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Servername oder Server-ID suchen" className="w-full rounded-xl border border-slate-800 bg-[#0e0e12] py-3 pl-10 pr-4 text-sm text-white outline-none focus:border-amber-400/40" /></div>
        {loading ? <div className="grid min-h-52 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-amber-300" /></div> : error ? (
          <div className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/[0.05] p-5 text-center"><p className="text-sm font-bold text-red-200">{error}</p><button onClick={load} className="mt-3 rounded-xl border border-red-400/20 px-3 py-2 text-xs font-bold text-red-200">Erneut versuchen</button></div>
        ) : <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {visible.map((guild) => <div key={guild.guild_id} className={cn("flex items-center gap-3 rounded-2xl border p-3", guild.premium ? "border-amber-400/25 bg-amber-400/[0.04]" : "border-slate-800 bg-[#0e0e12]")}>
            {guild.icon ? <img src={guild.icon} alt="" className="h-10 w-10 rounded-xl object-cover" /> : <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-slate-800 text-slate-500"><Server className="h-4 w-4" /></span>}
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-bold text-white">{guild.name}</p><p className="truncate text-[10px] text-slate-600">{guild.guild_id} · {guild.members.toLocaleString("de-DE")} Mitglieder</p><p className={cn("mt-1 text-[9px] font-black uppercase", guild.premium ? "text-amber-300" : "text-slate-600")}>{guild.premium ? "Server-Premium aktiv" : "Kein Server-Premium"}</p></div>
            <button type="button" onClick={() => toggle(guild)} disabled={busy === guild.guild_id} className={cn("relative h-7 w-12 shrink-0 rounded-full transition-colors disabled:opacity-40", guild.premium ? "bg-amber-400" : "bg-slate-700")} aria-label={`Premium für ${guild.name} ${guild.premium ? "entziehen" : "vergeben"}`}>
              {busy === guild.guild_id ? <Loader2 className="absolute left-4 top-1.5 h-4 w-4 animate-spin text-black" /> : <span className={cn("absolute left-0 top-1 h-5 w-5 rounded-full bg-white transition-transform", guild.premium ? "translate-x-6" : "translate-x-1")} />}
            </button>
          </div>)}
          {!visible.length && <p className="col-span-full py-10 text-center text-sm text-slate-500">Kein passender Server gefunden.</p>}
        </div>}
      </section>
    </div>
  );
}
