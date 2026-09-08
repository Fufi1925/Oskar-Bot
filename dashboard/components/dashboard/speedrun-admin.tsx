"use client";

/**
 * Speedrun-Zugänge verwalten.
 *
 * Der Speedrun-Reiter braucht Premium am Konto. Der frühere Beta-Code
 * ist weg -- es gibt nur noch ein Premium, und das gilt für beide Bots.
 * Freigeschaltet wird damit ein *Server*, nicht ein Konto. Hier steht,
 * welche Server das getan haben, wer es war und wann — und hier lässt
 * sich der Zugang wieder nehmen.
 *
 * Zwei Handgriffe, die absichtlich verschieden sind:
 *
 *   **Entziehen**  Der Eintrag wird zurückgesetzt. Mit Premium geht es
 *                  sofort wieder — für den Fall, dass ein Server den
 *                  Besitzer wechselt.
 *
 *   **Sperren**    Auch Premium hilft nicht mehr. Für den Fall, dass
 *                  jemand Unsinn treibt.
 *
 * Beides bricht einen laufenden Speedrun sofort ab. Wer jemandem den
 * Zugang nimmt, will nicht, dass der angefangene Umbau trotzdem noch
 * zehn Minuten weiterläuft.
 *
 * Die Rechteprüfung liegt nicht hier, sondern im Proxy (`/api/bot`) und
 * im Bot. Eine Oberfläche, die einen Knopf versteckt, ist keine Sperre.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import {
  Ban,
  CheckCircle2,
  Clock,
  Gauge,
  History,
  Loader2,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldOff,
  Unlock,
  Users,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD =
  "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

/** Wie ein Ereignis im Verlauf heißt und aussieht. */
const EVENTS: Record<string, { label: string; tone: string }> = {
  unlocked: { label: "freigeschaltet", tone: "text-emerald-400" },
  denied: { label: "abgelehnt", tone: "text-amber-400" },
  revoked: { label: "entzogen", tone: "text-amber-300" },
  banned: { label: "gesperrt", tone: "text-red-400" },
  unbanned: { label: "entsperrt", tone: "text-sky-400" },
  run_started: { label: "Lauf gestartet", tone: "text-slate-400" },
};

function when(seconds?: number | null) {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Stat({
  icon: Icon,
  value,
  label,
  tone,
}: {
  icon: React.ElementType;
  value: React.ReactNode;
  label: string;
  tone?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-[#0e0e12] p-4">
      <Icon className={cn("h-4 w-4 mb-2", tone || "text-slate-500")} />
      <p className="text-xl font-black text-white tabular-nums">{value}</p>
      <p className="text-[11px] text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}

export function SpeedrunAdmin() {
  const { data: session } = useSession();
  const actorId = session?.user?.id ?? "";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [guilds, setGuilds] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"alle" | "frei" | "gesperrt" | "botweg">("alle");
  const [view, setView] = useState<"server" | "verlauf">("server");
  const [busyId, setBusyId] = useState("");
  // Welcher Server gerade seinen Verlauf zeigt.
  const [openLog, setOpenLog] = useState("");

  const load = useCallback(async () => {
    // allSettled: fällt der Verlauf aus, soll die Liste trotzdem
    // stehen. Mit Promise.all verlöre man beide, sobald einer hakt.
    const [list, log] = await Promise.allSettled([
      api.speedrunAdminGuilds(),
      api.speedrunAdminHistory("", 150),
    ]);

    if (list.status === "fulfilled") {
      setGuilds(list.value?.guilds ?? []);
      setStats(list.value?.stats ?? null);
      setError("");
    } else {
      setError(list.reason?.message || "Die Liste ließ sich nicht laden.");
    }

    if (log.status === "fulfilled") setEvents(log.value?.events ?? []);

    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return guilds.filter((guild) => {
      if (filter === "frei" && guild.banned) return false;
      if (filter === "gesperrt" && !guild.banned) return false;
      if (filter === "botweg" && guild.bot_present) return false;
      if (!needle) return true;
      return String(guild.guild_id).includes(needle) ||
        String(guild.name || "").toLowerCase().includes(needle);
    });
  }, [guilds, query, filter]);

  const act = async (
    guildId: string,
    what: "revoke" | "ban" | "unban",
    reason = ""
  ) => {
    setBusyId(guildId + what);
    try {
      if (what === "revoke") {
        const answer = await api.speedrunAdminRevoke(guildId, actorId);
        toast.success(
          answer?.run_cancelled
            ? "Entzogen — ein laufender Speedrun wurde abgebrochen."
            : "Entzogen. Der Eintrag ist zurückgesetzt."
        );
      } else if (what === "ban") {
        const answer = await api.speedrunAdminBan(guildId, actorId, reason);
        toast.success(
          answer?.run_cancelled
            ? "Gesperrt — ein laufender Speedrun wurde abgebrochen."
            : "Gesperrt. Auch Premium hilft nicht mehr."
        );
      } else {
        await api.speedrunAdminUnban(guildId, actorId);
        toast.success("Entsperrt. Mit Premium geht es wieder.");
      }
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Das hat nicht geklappt.");
    } finally {
      setBusyId("");
    }
  };

  const confirmRevoke = (guild: any) => {
    const name = guild.name || guild.guild_id;
    if (
      confirm(
        `Zugang für „${name}“ entziehen?\n\n` +
  "Der Eintrag wird zurückgesetzt. Mit Premium geht es sofort wieder. " +
  "Ein laufender Speedrun wird sofort abgebrochen."
      )
    ) {
      act(guild.guild_id, "revoke");
    }
  };

  const confirmBan = (guild: any) => {
    const name = guild.name || guild.guild_id;
    const reason = prompt(
      `„${name}“ dauerhaft sperren?\n\n` +
  "Danach hilft auch Premium nicht mehr. Ein laufender Speedrun wird sofort " +
  "abgebrochen.\n\nBegründung (wird dem Server angezeigt):"
    );
    // Abbrechen im Dialog gibt null zurück -- ein leerer Text ist
    // dagegen eine bewusste Eingabe und geht durch.
    if (reason === null) return;
    act(guild.guild_id, "ban", reason.trim());
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const logFor = (guildId: string) =>
    events.filter((entry) => String(entry.guild_id) === String(guildId));

  return (
    <section className="space-y-5">
      <div className="overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-cyan-500/[0.10] via-[#131318] to-[#111116]">
        <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:p-6">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-cyan-500/20 bg-cyan-500/10"><Gauge className="h-5 w-5 text-cyan-300" /></span>
          <div className="min-w-0 flex-1"><h2 className="text-xl font-black tracking-tight text-white">Speedrun-Zentrale</h2><p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-400">Freigeschaltete Server überwachen, Zugänge zurücksetzen und Missbrauch dauerhaft sperren.</p></div>
          <button onClick={() => { setLoading(true); load(); }} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-800 bg-[#0b0b0f] px-4 py-2.5 text-xs font-bold text-slate-300 hover:border-slate-700 hover:text-white"><RefreshCw className="h-4 w-4" /> Aktualisieren</button>
        </div>
        {error && <div className="mx-5 mb-5 flex gap-2.5 rounded-xl border border-red-500/20 bg-red-500/[0.07] p-3.5 sm:mx-6"><XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" /><p className="text-xs leading-relaxed text-red-200/80">{error}</p></div>}
        {stats && <div className="grid grid-cols-2 border-t border-slate-800 sm:grid-cols-4">
          {[{ icon: Unlock, value: stats.unlocked, label: "Freigeschaltet", color: "text-emerald-400" }, { icon: ShieldOff, value: stats.banned, label: "Gesperrt", color: "text-red-400" }, { icon: Gauge, value: stats.runs, label: "Läufe gesamt", color: "text-cyan-400" }, { icon: Users, value: stats.total, label: "Server bekannt", color: "text-violet-400" }].map((item,index)=><div key={item.label} className={cn("flex items-center gap-3 border-slate-800 px-4 py-4",index>0&&"border-l",index===2&&"border-l-0 border-t sm:border-l sm:border-t-0")}><span className="grid h-9 w-9 place-items-center rounded-xl bg-black/20"><item.icon className={cn("h-4 w-4",item.color)}/></span><div><p className="text-lg font-black tabular-nums text-white">{item.value}</p><p className="text-[9px] font-bold uppercase tracking-wider text-slate-600">{item.label}</p></div></div>)}
        </div>}
      </div>

      <div className="grid grid-cols-2 gap-2 rounded-2xl border border-slate-800 bg-[#131318] p-2">
        <button onClick={()=>setView("server")} aria-current={view==="server"?"page":undefined} className={cn("flex items-center justify-center gap-2 rounded-xl border py-3 text-xs font-bold transition",view==="server"?"border-cyan-500/25 bg-cyan-500/10 text-cyan-300":"border-transparent text-slate-500 hover:bg-white/[0.03]")}><Users className="h-4 w-4"/>Serververwaltung</button>
        <button onClick={()=>setView("verlauf")} aria-current={view==="verlauf"?"page":undefined} className={cn("flex items-center justify-center gap-2 rounded-xl border py-3 text-xs font-bold transition",view==="verlauf"?"border-violet-500/25 bg-violet-500/10 text-violet-300":"border-transparent text-slate-500 hover:bg-white/[0.03]")}><History className="h-4 w-4"/>Ereignisverlauf</button>
      </div>

      {view === "server" && <>
        <div className="rounded-2xl border border-slate-800 bg-[#131318] p-3">
          <div className="relative"><Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600"/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Servername oder Server-ID suchen …" className="w-full rounded-xl border border-slate-800 bg-[#0b0b0f] py-2.5 pl-10 pr-4 text-sm text-white outline-none placeholder:text-slate-600 focus:border-cyan-500/30"/></div>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">{([['alle','Alle'],['frei','Freigeschaltet'],['gesperrt','Gesperrt'],['botweg','Bot entfernt']] as const).map(([id,label])=><button key={id} onClick={()=>setFilter(id)} className={cn("shrink-0 rounded-xl border px-3.5 py-2 text-xs font-bold",filter===id?"border-cyan-500/25 bg-cyan-500/10 text-cyan-300":"border-slate-800 bg-[#0b0b0f] text-slate-500 hover:text-slate-300")}>{label}</button>)}</div>
        </div>
        <div className="flex items-center justify-between px-1"><p className="text-xs font-bold text-slate-400">{shown.length} Server</p>{(query||filter!=="alle")&&<button onClick={()=>{setQuery("");setFilter("alle")}} className="text-xs font-bold text-cyan-400">Filter zurücksetzen</button>}</div>

        {shown.length===0?<div className="rounded-3xl border border-dashed border-slate-800 bg-[#111116] py-14 text-center"><Search className="mx-auto h-5 w-5 text-slate-700"/><p className="mt-3 text-sm font-bold text-slate-400">Kein Server gefunden</p><p className="mt-1 text-xs text-slate-600">Passe Suche oder Filter an.</p></div>:<div className="grid items-start gap-3 xl:grid-cols-2">{shown.map(guild=>{
          const open=openLog===guild.guild_id; const entries=open?logFor(guild.guild_id):[];
          return <article key={guild.guild_id} className={cn("overflow-hidden rounded-2xl border bg-[#131318]",guild.banned?"border-red-500/25":"border-slate-800")}>
            <div className="p-4"><div className="flex items-start gap-3"><span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl",guild.banned?"bg-red-500/10":"bg-cyan-500/10")}><Gauge className={cn("h-4 w-4",guild.banned?"text-red-400":"text-cyan-400")}/></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h3 className="truncate text-sm font-black text-white">{guild.name||"Unbekannter Server"}</h3><span className={cn("rounded-md border px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider",guild.banned?"border-red-500/20 bg-red-500/10 text-red-300":"border-emerald-500/20 bg-emerald-500/10 text-emerald-300")}>{guild.banned?"Gesperrt":"Frei"}</span>{!guild.bot_present&&<span className="rounded-md border border-slate-700 bg-slate-800/50 px-1.5 py-0.5 text-[9px] font-black uppercase text-slate-400">Bot entfernt</span>}</div><p className="mt-1 truncate font-mono text-[10px] text-slate-600">{guild.guild_id}</p></div></div>
            <div className="mt-4 grid grid-cols-3 overflow-hidden rounded-xl border border-slate-800 bg-[#0b0b0f]"><div className="p-2.5"><p className="text-sm font-black text-white">{guild.members||0}</p><p className="text-[9px] uppercase text-slate-600">Mitglieder</p></div><div className="border-l border-slate-800 p-2.5"><p className="text-sm font-black text-white">{guild.runs||0}</p><p className="text-[9px] uppercase text-slate-600">Läufe</p></div><div className="border-l border-slate-800 p-2.5"><p className="truncate text-[11px] font-bold text-white">{when(guild.last_run_at)}</p><p className="text-[9px] uppercase text-slate-600">Letzter Lauf</p></div></div>
            {guild.banned&&<div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/[0.07] p-3 text-[11px] leading-relaxed text-red-200/70">Gesperrt am {when(guild.banned_at)}{guild.banned_by?` von ${guild.banned_by}`:""}{guild.ban_reason?` — ${guild.ban_reason}`:""}</div>}
            <div className="mt-3 grid grid-cols-2 gap-2"><button onClick={()=>setOpenLog(open?"":guild.guild_id)} aria-expanded={open} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-800 bg-[#0b0b0f] py-2.5 text-xs font-bold text-slate-400 hover:text-white"><History className="h-3.5 w-3.5"/>Verlauf</button>{guild.banned?<button onClick={()=>act(guild.guild_id,"unban")} disabled={busyId===guild.guild_id+"unban"} className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-500/25 bg-sky-500/10 py-2.5 text-xs font-bold text-sky-300 disabled:opacity-40">{busyId===guild.guild_id+"unban"?<Loader2 className="h-3.5 w-3.5 animate-spin"/>:<RotateCcw className="h-3.5 w-3.5"/>}Entsperren</button>:<div className="grid grid-cols-2 gap-2"><button onClick={()=>confirmRevoke(guild)} disabled={busyId===guild.guild_id+"revoke"} title="Zugang zurücksetzen" className="grid place-items-center rounded-xl border border-amber-500/20 bg-amber-500/10 text-amber-300 disabled:opacity-40"><RotateCcw className="h-3.5 w-3.5"/></button><button onClick={()=>confirmBan(guild)} disabled={busyId===guild.guild_id+"ban"} title="Dauerhaft sperren" className="grid place-items-center rounded-xl border border-red-500/20 bg-red-500/10 text-red-300 disabled:opacity-40"><Ban className="h-3.5 w-3.5"/></button></div>}</div></div>
            {open&&<div className="space-y-2 border-t border-slate-800 bg-[#0b0b0f]/70 p-4">{entries.length===0?<p className="text-xs text-slate-600">Für diesen Server gibt es noch keinen Verlauf.</p>:entries.map(entry=>{const meta=EVENTS[entry.event]??{label:entry.event,tone:"text-slate-400"};return <div key={entry.id} className="flex flex-wrap items-baseline gap-2 text-[11px]"><span className="font-mono text-slate-600">{when(entry.at)}</span><span className={cn("font-bold",meta.tone)}>{meta.label}</span><span className="min-w-0 truncate text-slate-500">{entry.user_id?`Nutzer ${entry.user_id}`:entry.actor_id?`Admin ${entry.actor_id}`:""}{entry.detail?` · ${entry.detail}`:""}</span></div>})}</div>}
          </article>})}</div>}
      </>}

      {view === "verlauf" && <div className="rounded-3xl border border-slate-800 bg-[#131318] p-4 sm:p-5"><div className="mb-4 flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-violet-500/10"><History className="h-4 w-4 text-violet-400"/></span><div><h3 className="text-sm font-black text-white">Letzte Ereignisse</h3><p className="text-[11px] text-slate-500">Freischaltungen, Sperren, Entzüge und Fehlversuche</p></div></div>{events.length===0?<p className="py-10 text-center text-xs text-slate-500">Noch nichts passiert.</p>:<div className="max-h-[600px] space-y-1.5 overflow-y-auto">{events.slice(0,80).map(entry=>{const meta=EVENTS[entry.event]??{label:entry.event,tone:"text-slate-400"};const guild=guilds.find(item=>String(item.guild_id)===String(entry.guild_id));return <div key={entry.id} className="flex items-start gap-3 rounded-xl border border-transparent bg-[#0b0b0f] px-3 py-2.5 hover:border-slate-800"><Clock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-700"/><span className="shrink-0 font-mono text-[10px] text-slate-600">{when(entry.at)}</span><span className={cn("shrink-0 text-[11px] font-bold",meta.tone)}>{meta.label}</span><span className="min-w-0 truncate text-[11px] text-slate-500">{guild?.name||entry.guild_id}{entry.detail?` · ${entry.detail}`:""}</span></div>})}</div>}<p className="mt-4 border-t border-slate-800 pt-3 text-[10px] leading-relaxed text-slate-600"><CheckCircle2 className="mr-1 inline h-3 w-3"/>Auch abgelehnte Versuche werden protokolliert.</p></div>}
    </section>
  );
}
