"use client";

import React from "react";
import { ArrowDown, ArrowUp, Check, Eye, GripVertical, Loader2, Save, Search, Server, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Guild = { guild_id: string; name: string; icon: string | null; members: number; selected: boolean };

export function HomepageServersAdmin() {
  const [guilds, setGuilds] = React.useState<Guild[]>([]);
  const [selected, setSelected] = React.useState<string[]>([]);
  const [saved, setSaved] = React.useState<string[]>([]);
  const [query, setQuery] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getHomepageServersAdmin();
      setGuilds(data.guilds || []);
      setSelected(data.selected || []);
      setSaved(data.selected || []);
    } catch (error: any) {
      toast.error(error?.message || "Die Serverauswahl konnte nicht geladen werden.");
    } finally { setLoading(false); }
  }, []);
  React.useEffect(() => { load(); }, [load]);

  const byId = React.useMemo(() => new Map(guilds.map((guild) => [guild.guild_id, guild])), [guilds]);
  const available = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    return guilds.filter((guild) => !selected.includes(guild.guild_id) && (!needle || guild.name.toLowerCase().includes(needle) || guild.guild_id.includes(needle)));
  }, [guilds, selected, query]);
  const dirty = selected.join(",") !== saved.join(",");

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= selected.length) return;
    setSelected((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };
  const save = async () => {
    setSaving(true);
    try {
      const data = await api.saveHomepageServersAdmin(selected);
      setSaved(data.selected || selected);
      toast.success("Homepage-Server wurden gespeichert.");
    } catch (error: any) {
      toast.error(error?.message || "Die Auswahl konnte nicht gespeichert werden.");
    } finally { setSaving(false); }
  };

  if (loading) return <div className="grid min-h-72 place-items-center rounded-3xl border border-slate-800 bg-[#131318]"><Loader2 className="h-6 w-6 animate-spin text-blue-400" /></div>;

  return <div className="space-y-5">
    <section className="overflow-hidden rounded-3xl border border-blue-500/20 bg-gradient-to-br from-blue-500/[.09] via-[#131318] to-[#101015]">
      <div className="flex flex-col gap-5 p-6 sm:flex-row sm:items-center">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-blue-400/20 bg-blue-500/10"><Eye className="h-5 w-5 text-blue-400" /></span>
        <div className="min-w-0 flex-1"><p className="text-[10px] font-black uppercase tracking-[.2em] text-blue-400">Öffentliche Homepage</p><h2 className="mt-1 text-xl font-black text-white">Durchlaufende Server</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-slate-400">Wähle bis zu 20 Server und bestimme ihre Reihenfolge. Nur diese öffentlichen Angaben erscheinen: Name, Serverbild und Mitgliederzahl.</p></div>
        <button type="button" onClick={save} disabled={!dirty || saving} className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white transition hover:bg-blue-500 disabled:opacity-35">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}Speichern</button>
      </div>
      <div className="grid grid-cols-3 border-t border-slate-800 bg-black/10 text-center"><div className="p-4"><p className="text-xl font-black text-white">{selected.length}</p><p className="text-[9px] font-black uppercase tracking-wider text-slate-600">Ausgewählt</p></div><div className="border-x border-slate-800 p-4"><p className="text-xl font-black text-white">20</p><p className="text-[9px] font-black uppercase tracking-wider text-slate-600">Maximum</p></div><div className="p-4"><p className="text-xl font-black text-white">{guilds.length}</p><p className="text-[9px] font-black uppercase tracking-wider text-slate-600">Verfügbar</p></div></div>
    </section>

    <div className="grid gap-5 xl:grid-cols-[1fr_.9fr]">
      <section className="rounded-2xl border border-slate-800 bg-[#131318] p-4 sm:p-5"><div className="mb-4"><h3 className="text-sm font-black text-white">Ausgewählte Reihenfolge</h3><p className="mt-1 text-xs text-slate-500">Die erste Karte startet den Lauf.</p></div>{selected.length ? <div className="space-y-2">{selected.map((id, index) => { const guild = byId.get(id); if (!guild) return null; return <div key={id} className="flex items-center gap-3 rounded-xl border border-slate-800 bg-[#0d0d11] p-3"><GripVertical className="h-4 w-4 text-slate-700"/><span className="w-5 text-xs font-black tabular-nums text-slate-600">{index + 1}</span>{guild.icon ? <img src={guild.icon} alt="" className="h-10 w-10 rounded-xl object-cover"/> : <span className="grid h-10 w-10 place-items-center rounded-xl bg-slate-800"><Server className="h-4 w-4 text-slate-500"/></span>}<div className="min-w-0 flex-1"><p className="truncate text-sm font-bold text-white">{guild.name}</p><p className="text-[11px] text-slate-500">{guild.members.toLocaleString("de-DE")} Mitglieder</p></div><button onClick={()=>move(index,-1)} disabled={index===0} className="grid h-8 w-8 place-items-center rounded-lg border border-slate-800 text-slate-500 disabled:opacity-25"><ArrowUp className="h-3.5 w-3.5"/></button><button onClick={()=>move(index,1)} disabled={index===selected.length-1} className="grid h-8 w-8 place-items-center rounded-lg border border-slate-800 text-slate-500 disabled:opacity-25"><ArrowDown className="h-3.5 w-3.5"/></button><button onClick={()=>setSelected((current)=>current.filter((value)=>value!==id))} className="grid h-8 w-8 place-items-center rounded-lg border border-rose-500/20 bg-rose-500/10 text-rose-400"><X className="h-3.5 w-3.5"/></button></div>; })}</div> : <div className="rounded-2xl border border-dashed border-slate-800 px-5 py-12 text-center text-sm text-slate-600">Noch kein Server ausgewählt. Der öffentliche Lauf bleibt verborgen.</div>}</section>

      <section className="rounded-2xl border border-slate-800 bg-[#131318] p-4 sm:p-5"><h3 className="text-sm font-black text-white">Server hinzufügen</h3><div className="relative my-4"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600"/><input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Servername oder ID suchen …" className="w-full rounded-xl border border-slate-800 bg-[#0d0d11] py-2.5 pl-10 pr-3 text-sm text-white outline-none focus:border-blue-500/40"/></div><div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">{available.map((guild)=><button key={guild.guild_id} type="button" disabled={selected.length>=20} onClick={()=>setSelected((current)=>[...current,guild.guild_id])} className={cn("flex w-full items-center gap-3 rounded-xl border border-slate-800 bg-[#0d0d11] p-3 text-left transition hover:border-blue-500/25",selected.length>=20&&"opacity-40")}>{guild.icon ? <img src={guild.icon} alt="" className="h-9 w-9 rounded-lg object-cover"/> : <span className="grid h-9 w-9 place-items-center rounded-lg bg-slate-800"><Server className="h-4 w-4 text-slate-500"/></span>}<div className="min-w-0 flex-1"><p className="truncate text-sm font-bold text-white">{guild.name}</p><p className="text-[10px] text-slate-600">{guild.members.toLocaleString("de-DE")} Mitglieder · {guild.guild_id}</p></div><span className="grid h-8 w-8 place-items-center rounded-lg bg-blue-500/10 text-blue-400"><Check className="h-4 w-4"/></span></button>)}{available.length===0&&<p className="py-10 text-center text-sm text-slate-600">Keine weiteren Server gefunden.</p>}</div></section>
    </div>
  </div>;
}
