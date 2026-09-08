"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn, useSession } from "next-auth/react";
import {
  ArrowLeft, ArrowRight, CalendarDays, Check, CheckCircle2, ChevronDown,
  Eye, FileImage, Filter, Gift, Lightbulb, Loader2, MessageCircle, Plus,
  Search, Send, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, TrendingUp,
  Upload, UserRound,
} from "lucide-react";
import { SiteNav } from "@/components/site-nav";
import { api } from "@/lib/api";

const STATUS: Record<string, { label: string; badge: string; dot: string }> = {
  open: { label: "Offen", badge: "border-blue-500/25 bg-blue-500/10 text-blue-300", dot: "bg-blue-400" },
  planned: { label: "Geplant", badge: "border-violet-500/25 bg-violet-500/10 text-violet-300", dot: "bg-violet-400" },
  working: { label: "In Bearbeitung", badge: "border-amber-500/25 bg-amber-500/10 text-amber-300", dot: "bg-amber-400" },
  implemented: { label: "Umgesetzt", badge: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300", dot: "bg-emerald-400" },
  rejected: { label: "Abgelehnt", badge: "border-red-500/25 bg-red-500/10 text-red-300", dot: "bg-red-400" },
  needs_info: { label: "Infos benötigt", badge: "border-orange-500/25 bg-orange-500/10 text-orange-300", dot: "bg-orange-400" },
};
const CARD = "rounded-2xl border border-white/[0.08] bg-[#111117] shadow-[0_20px_60px_rgba(0,0,0,.18)]";

function formatDate(value: number) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value * 1000));
}
function StatusBadge({ status }: { status: string }) {
  const item = STATUS[status] || STATUS.open;
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold ${item.badge}`}><span className={`h-1.5 w-1.5 rounded-full ${item.dot}`} />{item.label}</span>;
}
function Avatar({ src, name, size = "h-8 w-8" }: { src?: string; name?: string; size?: string }) {
  return src ? <img src={src} alt="" className={`${size} rounded-full object-cover ring-1 ring-white/10`} /> : <span className={`${size} grid shrink-0 place-items-center rounded-full bg-indigo-500/15 text-xs font-black text-indigo-300 ring-1 ring-indigo-500/20`}>{(name || "U").slice(0, 1).toUpperCase()}</span>;
}
function LoginButton({ text = "Mit Discord anmelden" }: { text?: string }) {
  return <button onClick={() => signIn("discord", { callbackUrl: "/auth/success?next=%2Fideas" })} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 text-sm font-bold text-white transition hover:bg-indigo-500"><ShieldCheck className="h-4 w-4" />{text}</button>;
}

function IdeasShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#08080c] text-white">
      <SiteNav />
      <div className="fixed left-0 right-0 top-16 z-30 border-b border-white/[0.06] bg-[#09090e]/90 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-1 overflow-x-auto px-4 sm:px-6">
          <Link href="/ideas" className="inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-slate-300 hover:bg-white/5 hover:text-white"><Lightbulb className="h-4 w-4 text-indigo-400" />Ideen entdecken</Link>
          <Link href="/ideas/me" className="shrink-0 rounded-lg px-3 py-2 text-sm font-semibold text-slate-400 hover:bg-white/5 hover:text-white">Meine Ideen</Link>
          <Link href="/ideas/me?tab=rewards" className="shrink-0 rounded-lg px-3 py-2 text-sm font-semibold text-slate-400 hover:bg-white/5 hover:text-white">Belohnungen</Link>
          <Link href="/ideas/new" className="ml-auto inline-flex shrink-0 items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white hover:bg-indigo-500"><Plus className="h-4 w-4" />Idee einreichen</Link>
        </div>
      </div>
      <main className="mx-auto max-w-7xl px-4 pb-24 pt-36 sm:px-6">{children}</main>
      <style jsx global>{`.idea-input{width:100%;border:1px solid rgba(255,255,255,.1);background:rgba(0,0,0,.18);border-radius:.75rem;padding:.8rem 1rem;color:#fff;outline:none}.idea-input:focus{border-color:#6366f1}.idea-input::placeholder{color:#475569}.idea-input:disabled{color:#94a3b8}`}</style>
    </div>
  );
}

function IdeaCard({ idea }: { idea: any }) {
  return (
    <Link href={`/ideas/${idea.id}`} className={`${CARD} group block overflow-hidden transition duration-200 hover:-translate-y-0.5 hover:border-indigo-500/30 hover:bg-[#14141b]`}>
      <div className="p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3"><StatusBadge status={idea.status} /><span className="text-[10px] font-medium text-slate-600">{idea.id}</span></div>
        <h2 className="mt-4 text-lg font-bold text-white transition group-hover:text-indigo-200">{idea.title}</h2>
        <p className="mt-2 line-clamp-3 min-h-[66px] text-sm leading-[22px] text-slate-400">{idea.description}</p>
        <div className="mt-5 flex items-center justify-between border-t border-white/[0.06] pt-4">
          <div className="flex min-w-0 items-center gap-2"><Avatar src={idea.avatar} name={idea.user_name} /><span className="max-w-28 truncate text-xs font-semibold text-slate-300">{idea.user_name}</span></div>
          <div className="flex items-center gap-3 text-[11px] text-slate-500"><span className="text-emerald-400">▲ {idea.upvotes || 0}</span><span className="text-red-400">▼ {idea.downvotes || 0}</span><span><MessageCircle className="mr-1 inline h-3 w-3" />{idea.comment_count || 0}</span><span><Eye className="mr-1 inline h-3 w-3" />{idea.views || 0}</span></div>
        </div>
      </div>
    </Link>
  );
}

export function IdeasList() {
  const [ideas, setIdeas] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sort, setSort] = useState("new");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ sort });
        if (query.trim()) params.set("q", query.trim());
        if (statusFilter) params.set("status", statusFilter);
        const result = await api.listIdeas(params.toString());
        setIdeas(result.ideas || []);
      } finally { setLoading(false); }
    }, 220);
    return () => window.clearTimeout(timer);
  }, [query, statusFilter, sort]);

  const counts = useMemo(() => ({
    total: ideas.length,
    implemented: ideas.filter((idea) => idea.status === "implemented").length,
    active: ideas.filter((idea) => ["planned", "working"].includes(idea.status)).length,
  }), [ideas]);

  return (
    <IdeasShell>
      <section className="relative overflow-hidden rounded-3xl border border-indigo-500/15 bg-[#101018] px-6 py-10 sm:px-10 sm:py-12">
        <div className="pointer-events-none absolute -right-28 -top-28 h-80 w-80 rounded-full bg-indigo-600/15 blur-3xl" />
        <div className="relative grid items-end gap-8 lg:grid-cols-[1fr_auto]">
          <div><span className="inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1.5 text-xs font-bold text-indigo-300"><Sparkles className="h-3.5 w-3.5" />Deine Idee zählt</span><h1 className="mt-5 max-w-3xl text-3xl font-black tracking-tight text-white sm:text-5xl">Gemeinsam bauen wir den besseren University Bot.</h1><p className="mt-4 max-w-2xl text-sm leading-7 text-slate-400 sm:text-base">Entdecke Vorschläge aus der Community, stimme ab und hilf uns zu entscheiden, was als Nächstes kommt.</p></div>
          <Link href="/ideas/new" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-6 text-sm font-bold text-white shadow-lg shadow-indigo-950/40 hover:bg-indigo-500">Idee einreichen <ArrowRight className="h-4 w-4" /></Link>
        </div>
        <div className="relative mt-8 grid grid-cols-3 gap-2 sm:max-w-xl sm:gap-3">{[[counts.total, "Ideen"],[counts.active, "In Arbeit"],[counts.implemented, "Umgesetzt"]].map(([value,label])=><div key={label} className="rounded-xl border border-white/[0.07] bg-black/15 px-3 py-3 sm:px-4"><p className="text-xl font-black text-white">{value}</p><p className="mt-0.5 text-[11px] text-slate-500">{label}</p></div>)}</div>
      </section>

      <div className="mt-7 grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
        <aside className="hidden h-fit lg:sticky lg:top-36 lg:block">
          <div className={`${CARD} p-4`}><div className="flex items-center gap-2 text-sm font-bold text-white"><Filter className="h-4 w-4 text-indigo-400" />Status</div><div className="mt-3 space-y-1">{[["","Alle Ideen"],...Object.entries(STATUS).map(([key,value])=>[key,value.label])].map(([key,label]:any)=><button key={key} onClick={()=>setStatusFilter(key)} className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm transition ${statusFilter===key?"bg-indigo-500/15 font-bold text-indigo-200":"text-slate-400 hover:bg-white/5 hover:text-white"}`}><span>{label}</span>{statusFilter===key&&<Check className="h-3.5 w-3.5"/>}</button>)}</div></div>
          <div className="mt-3 rounded-2xl border border-emerald-500/15 bg-emerald-500/[0.06] p-4"><Gift className="h-5 w-5 text-emerald-400" /><p className="mt-3 text-sm font-bold text-white">Gute Ideen lohnen sich</p><p className="mt-1 text-xs leading-5 text-slate-400">Ausgewählte Vorschläge erhalten drei Tage Premium für einen Server.</p></div>
        </aside>
        <section>
          <div className="mb-3 flex gap-2 overflow-x-auto pb-1 lg:hidden">{[["","Alle"],...Object.entries(STATUS).map(([key,value])=>[key,value.label])].map(([key,label]:any)=><button key={key} onClick={()=>setStatusFilter(key)} className={`shrink-0 rounded-full border px-3 py-2 text-xs font-bold ${statusFilter===key?"border-indigo-500 bg-indigo-600 text-white":"border-white/10 bg-[#111117] text-slate-400"}`}>{label}</button>)}</div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1"><Search className="absolute left-4 top-3.5 h-4 w-4 text-slate-500"/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Titel oder Beschreibung durchsuchen …" className="h-11 w-full rounded-xl border border-white/10 bg-[#111117] pl-11 pr-4 text-sm text-white outline-none focus:border-indigo-500" /></div>
            <div className="flex rounded-xl border border-white/10 bg-[#111117] p-1"><button onClick={()=>setSort("new")} className={`flex-1 rounded-lg px-4 py-2 text-xs font-bold ${sort==="new"?"bg-indigo-600 text-white":"text-slate-400"}`}>Neueste</button><button onClick={()=>setSort("popular")} className={`flex-1 rounded-lg px-4 py-2 text-xs font-bold ${sort==="popular"?"bg-indigo-600 text-white":"text-slate-400"}`}><TrendingUp className="mr-1 inline h-3.5 w-3.5"/>Beliebteste</button></div>
          </div>
          {loading ? <Loading /> : ideas.length ? <div className="mt-4 grid gap-4 xl:grid-cols-2">{ideas.map((idea)=><IdeaCard key={idea.id} idea={idea}/>)}</div> : <Empty icon={<Lightbulb className="h-7 w-7"/>} title="Keine Ideen gefunden" text="Passe Suche oder Filter an – oder reiche die erste passende Idee ein."><Link href="/ideas/new" className="mt-5 inline-flex rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white">Idee einreichen</Link></Empty>}
        </section>
      </div>
    </IdeasShell>
  );
}

export function NewIdea() {
  const { status } = useSession();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [images, setImages] = useState<string[]>([""]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const upload = async (files: FileList | null) => {
    if (!files) return;
    const selected = Array.from(files).slice(0, 3);
    if (selected.reduce((sum, file) => sum + file.size, 0) > 8 * 1024 * 1024) return setError("Die Bilder dürfen zusammen höchstens 8 MB groß sein.");
    const values = await Promise.all(selected.map((file) => new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(); reader.readAsDataURL(file); })));
    setImages(values); setError("");
  };
  const submit = async () => {
    setBusy(true); setError("");
    try { const result = await api.submitIdea({ title, description, images: images.filter(Boolean) }); router.push(`/ideas/${result.idea.id}`); }
    catch (err: any) { setError(err?.message || "Idee konnte nicht eingereicht werden."); }
    finally { setBusy(false); }
  };
  if (status !== "authenticated") return <IdeasShell><Empty icon={<ShieldCheck className="h-7 w-7"/>} title="Discord-Login erforderlich" text="Zum Einreichen benötigen wir nur dein Discord-Konto als Autor der Idee."><LoginButton text="Mit Discord anmelden & fortfahren" /></Empty></IdeasShell>;
  return (
    <IdeasShell>
      <Link href="/ideas" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />Zurück zu allen Ideen</Link>
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section className={`${CARD} overflow-hidden`}><div className="border-b border-white/[0.07] p-6 sm:p-8"><span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400"><Lightbulb className="h-5 w-5" /></span><h1 className="mt-4 text-2xl font-black text-white sm:text-3xl">Neue Idee einreichen</h1><p className="mt-2 text-sm leading-6 text-slate-400">Erkläre klar, welches Problem du lösen möchtest und wie deine Lösung aussieht.</p></div>
          <div className="space-y-6 p-6 sm:p-8"><Field label="Titel" hint={`${title.length}/100`}><input value={title} maxLength={100} onChange={(e)=>setTitle(e.target.value)} placeholder="Zum Beispiel: Eigene Ticket-Kategorien exportieren" className="idea-input" /></Field><Field label="Beschreibung" hint={`${description.length}/2000`}><textarea value={description} maxLength={2000} onChange={(e)=>setDescription(e.target.value)} rows={9} placeholder="Was fehlt aktuell? Wie soll es funktionieren? Wem hilft die Änderung?" className="idea-input resize-none" /></Field><Field label="Referenzbilder" hint="Optional · 3 Bilder · 8 MB"><label className="flex cursor-pointer flex-col items-center rounded-xl border border-dashed border-white/15 bg-black/15 px-4 py-6 text-center transition hover:border-indigo-500/40 hover:bg-indigo-500/5"><Upload className="h-6 w-6 text-indigo-400"/><span className="mt-2 text-sm font-bold text-white">Bilder hochladen</span><span className="mt-1 text-xs text-slate-500">PNG, JPG, WebP oder GIF</span><input type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif" onChange={(e)=>void upload(e.target.files)} className="hidden"/></label><div className="my-3 flex items-center gap-3 text-[10px] uppercase tracking-widest text-slate-600"><span className="h-px flex-1 bg-white/[0.06]"/>oder Bildlink<span className="h-px flex-1 bg-white/[0.06]"/></div><div className="space-y-2">{images.map((value,index)=><div key={index} className="relative"><FileImage className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-500"/><input value={value.startsWith("data:")?"Bild erfolgreich hochgeladen":value} disabled={value.startsWith("data:")} onChange={(e)=>setImages((current)=>current.map((item,i)=>i===index?e.target.value:item))} placeholder="https://…/referenz.png" className="idea-input pl-10"/></div>)}{images.length<3&&<button onClick={()=>setImages((current)=>[...current,""])} className="text-xs font-bold text-indigo-400">+ Weiteren Bildlink hinzufügen</button>}</div></Field>{error&&<div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>}<button disabled={busy} onClick={submit} className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 font-bold text-white shadow-lg shadow-indigo-950/30 hover:bg-indigo-500 disabled:opacity-50">{busy?<Loader2 className="h-4 w-4 animate-spin"/>:<Send className="h-4 w-4"/>}{busy?"Wird eingereicht …":"Idee einreichen"}</button></div>
        </section>
        <aside className="h-fit space-y-3 lg:sticky lg:top-36"><Tip number="01" title="Ein Problem pro Idee" text="Mehrere unabhängige Wünsche lassen sich schwer bewerten und umsetzen."/><Tip number="02" title="Konkrete Beispiele" text="Beschreibe, was heute passiert und was stattdessen passieren sollte."/><Tip number="03" title="Keine privaten Daten" text="Screenshots dürfen keine Tokens, E-Mails oder sensiblen Discord-Daten zeigen."/><div className="rounded-2xl border border-emerald-500/15 bg-emerald-500/[0.06] p-5"><Gift className="h-5 w-5 text-emerald-400"/><p className="mt-3 text-sm font-bold text-white">3 Tage Premium möglich</p><p className="mt-1 text-xs leading-5 text-slate-400">Besonders hilfreiche angenommene Ideen können vom Team belohnt werden.</p></div></aside>
      </div>
    </IdeasShell>
  );
}

export function IdeaDetail({ id }: { id: string }) {
  const { status } = useSession();
  const [idea, setIdea] = useState<any>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { const result = await api.getIdea(id); setIdea(result.idea); }, [id]);
  useEffect(() => { void load(); }, [load]);
  if (!idea) return <IdeasShell><Loading /></IdeasShell>;
  const vote = async (value: number) => {
    if (status !== "authenticated") return void signIn("discord", { callbackUrl: `/auth/success?next=${encodeURIComponent(`/ideas/${id}`)}` });
    const result = await api.voteIdea(id, idea.my_vote === value ? 0 : value); setIdea(result.idea);
  };
  const sendComment = async () => {
    if (!comment.trim()) return; setBusy(true);
    try { const result = await api.commentIdea(id, comment); setIdea(result.idea); setComment(""); } finally { setBusy(false); }
  };
  return (
    <IdeasShell>
      <Link href="/ideas" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4"/>Alle Ideen</Link>
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <article>
          <div className="flex flex-wrap items-center gap-2"><StatusBadge status={idea.status}/><span className="text-xs text-slate-600">{idea.id}</span></div>
          <h1 className="mt-5 text-3xl font-black tracking-tight text-white sm:text-5xl">{idea.title}</h1>
          <div className="mt-5 flex flex-wrap items-center gap-4 text-xs text-slate-500"><span className="flex items-center gap-2"><Avatar src={idea.avatar} name={idea.user_name}/><b className="text-slate-300">{idea.user_name}</b></span><span><CalendarDays className="mr-1.5 inline h-3.5 w-3.5"/>{formatDate(idea.created_at)}</span><span><Eye className="mr-1.5 inline h-3.5 w-3.5"/>{idea.views||0} Aufrufe</span></div>
          {idea.admin_note&&<div className="mt-7 rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.08] p-5"><div className="flex items-center gap-2 text-sm font-bold text-indigo-300"><ShieldCheck className="h-4 w-4"/>Antwort vom University-Team</div><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">{idea.admin_note}</p></div>}
          <div className={`${CARD} mt-6 p-6 sm:p-8`}><p className="whitespace-pre-wrap text-[15px] leading-8 text-slate-300">{idea.description}</p>{idea.images?.length>0&&<div className="mt-6 grid gap-3 sm:grid-cols-2">{idea.images.map((image:string)=><a key={image} href={image} target="_blank" rel="noreferrer"><img src={image} alt="Referenzbild" className="max-h-96 w-full rounded-xl border border-white/10 object-cover"/></a>)}</div>}</div>
          <div className="mt-4 flex items-center gap-2"><button onClick={()=>void vote(1)} className={`min-h-10 rounded-xl border px-4 text-sm font-bold transition ${idea.my_vote===1?"border-emerald-500/40 bg-emerald-500/15 text-emerald-300":"border-white/10 bg-white/[.03] text-slate-400 hover:text-white"}`}><ThumbsUp className="mr-2 inline h-4 w-4"/>{idea.upvotes||0}</button><button onClick={()=>void vote(-1)} className={`min-h-10 rounded-xl border px-4 text-sm font-bold transition ${idea.my_vote===-1?"border-red-500/40 bg-red-500/15 text-red-300":"border-white/10 bg-white/[.03] text-slate-400 hover:text-white"}`}><ThumbsDown className="mr-2 inline h-4 w-4"/>{idea.downvotes||0}</button></div>
          <section className="mt-10 border-t border-white/[0.08] pt-8"><div className="flex items-center justify-between"><h2 className="text-xl font-black text-white">Diskussion</h2><span className="rounded-full bg-white/5 px-2.5 py-1 text-xs text-slate-400">{idea.comments?.length||0}</span></div>{status==="authenticated"?<div className={`${CARD} mt-5 flex gap-3 p-3`}><textarea value={comment} onChange={(e)=>setComment(e.target.value)} rows={3} placeholder="Sachlich kommentieren oder eine Rückfrage stellen …" className="min-w-0 flex-1 resize-none bg-transparent p-2 text-sm text-white outline-none placeholder:text-slate-600"/><button disabled={busy||!comment.trim()} onClick={()=>void sendComment()} className="self-end rounded-xl bg-indigo-600 p-3 text-white disabled:opacity-40"><Send className="h-4 w-4"/></button></div>:<div className="mt-5 rounded-2xl border border-white/10 bg-white/[.025] p-5"><p className="mb-4 text-sm text-slate-400">Melde dich an, um an der Diskussion teilzunehmen.</p><LoginButton text="Zum Kommentieren anmelden"/></div>}<div className="mt-5 space-y-3">{idea.comments?.length?idea.comments.map((entry:any)=><div key={entry.id} className={`${CARD} p-5`}><div className="flex items-center gap-2"><Avatar src={entry.avatar} name={entry.user_name}/><div><p className="text-sm font-bold text-white">{entry.user_name}</p><p className="text-[10px] text-slate-600">{formatDate(entry.created_at)}</p></div></div><p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-slate-300">{entry.body}</p></div>):<p className="py-10 text-center text-sm text-slate-600">Noch keine Kommentare. Starte die Diskussion.</p>}</div></section>
        </article>
        <aside className="h-fit space-y-3 lg:sticky lg:top-36"><div className={`${CARD} p-5`}><p className="text-xs font-bold uppercase tracking-wider text-slate-500">Aktueller Status</p><div className="mt-3"><StatusBadge status={idea.status}/></div><div className="mt-5 space-y-3 border-t border-white/[0.07] pt-4 text-xs text-slate-500"><div className="flex justify-between"><span>Upvotes</span><b className="text-emerald-400">{idea.upvotes||0}</b></div><div className="flex justify-between"><span>Downvotes</span><b className="text-red-400">{idea.downvotes||0}</b></div><div className="flex justify-between"><span>Kommentare</span><b className="text-slate-300">{idea.comments?.length||0}</b></div></div></div><div className="rounded-2xl border border-indigo-500/15 bg-indigo-500/[.06] p-5"><Lightbulb className="h-5 w-5 text-indigo-400"/><p className="mt-3 text-sm font-bold text-white">Du hast auch eine Idee?</p><p className="mt-1 text-xs leading-5 text-slate-400">Beschreibe sie konkret und lass die Community abstimmen.</p><Link href="/ideas/new" className="mt-4 inline-flex text-xs font-bold text-indigo-300">Idee einreichen <ArrowRight className="ml-1 h-3.5 w-3.5"/></Link></div></aside>
      </div>
    </IdeasShell>
  );
}

export function MyIdeas() {
  const { status } = useSession();
  const search = useSearchParams();
  const [tab, setTab] = useState(search.get("tab") === "rewards" ? "rewards" : "ideas");
  const [data, setData] = useState<any>({ ideas: [], rewards: [] });
  const [servers, setServers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { if (status === "authenticated") Promise.all([api.myIdeas(), api.ideaRewardServers()]).then(([mine, guilds]) => { setData(mine); setServers(guilds.servers || []); }).finally(()=>setLoading(false)); }, [status]);
  if (status !== "authenticated") return <IdeasShell><Empty icon={<UserRound className="h-7 w-7"/>} title="Dein persönlicher Ideenbereich" text="Melde dich an, um deine Vorschläge und offenen Premium-Belohnungen zu sehen."><LoginButton /></Empty></IdeasShell>;
  return (
    <IdeasShell>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-sm font-bold text-indigo-400">Dein Bereich</p><h1 className="mt-1 text-3xl font-black text-white sm:text-4xl">Meine Ideen & Belohnungen</h1><p className="mt-2 text-sm text-slate-400">Verfolge Entscheidungen und löse deine Prämien ein.</p></div><Link href="/ideas/new" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 text-sm font-bold text-white"><Plus className="h-4 w-4"/>Neue Idee</Link></div>
      <div className="mt-7 inline-flex rounded-xl border border-white/10 bg-[#111117] p-1"><button onClick={()=>setTab("ideas")} className={`rounded-lg px-4 py-2 text-sm font-bold ${tab==="ideas"?"bg-indigo-600 text-white":"text-slate-400"}`}>Meine Ideen <span className="ml-1 opacity-70">{data.ideas.length}</span></button><button onClick={()=>setTab("rewards")} className={`rounded-lg px-4 py-2 text-sm font-bold ${tab==="rewards"?"bg-indigo-600 text-white":"text-slate-400"}`}><Gift className="mr-1.5 inline h-4 w-4"/>Belohnungen <span className="ml-1 opacity-70">{data.rewards.length}</span></button></div>
      {loading?<Loading/>:tab==="ideas"?(data.ideas.length?<div className="mt-5 grid gap-3 md:grid-cols-2">{data.ideas.map((idea:any)=><Link href={`/ideas/${idea.id}`} key={idea.id} className={`${CARD} group p-5 hover:border-indigo-500/30`}><div className="flex items-start justify-between gap-3"><StatusBadge status={idea.status}/><span className="text-[10px] text-slate-600">{idea.id}</span></div><h2 className="mt-4 font-bold text-white group-hover:text-indigo-200">{idea.title}</h2><p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-400">{idea.description}</p><span className="mt-4 inline-flex items-center text-xs font-bold text-indigo-400">Details ansehen <ArrowRight className="ml-1 h-3.5 w-3.5"/></span></Link>)}</div>:<Empty icon={<Lightbulb className="h-7 w-7"/>} title="Noch keine Ideen" text="Dein erster Vorschlag ist nur wenige Minuten entfernt."><Link href="/ideas/new" className="mt-5 inline-flex rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white">Erste Idee einreichen</Link></Empty>):(data.rewards.length?<div className="mt-5 grid gap-4 lg:grid-cols-2">{data.rewards.map((reward:any)=><RewardCard key={reward.idea_id} reward={reward} servers={servers}/>)}</div>:<Empty icon={<Gift className="h-7 w-7"/>} title="Noch keine Belohnungen" text="Wird eine deiner Ideen ausgezeichnet, erscheint hier dein Premium-Gutschein."/>)}
    </IdeasShell>
  );
}

function RewardCard({ reward, servers }: { reward: any; servers: any[] }) {
  const [guild, setGuild] = useState(servers[0]?.id || "");
  const [claimed, setClaimed] = useState(Boolean(reward.claimed_at));
  const [open, setOpen] = useState(false);
  const selected = servers.find((server) => server.id === guild);
  return <div className={`${CARD} relative overflow-hidden p-6`}><div className="pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full bg-emerald-500/10 blur-2xl"/><div className="relative flex items-start gap-4"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-400"><Gift className="h-6 w-6"/></span><div><span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400">Community-Belohnung</span><h3 className="mt-1 text-xl font-black text-white">3 Tage Premium</h3><p className="mt-1 text-sm text-slate-400">für „{reward.title}“</p></div></div>{claimed?<div className="relative mt-6 flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm font-bold text-emerald-300"><CheckCircle2 className="h-5 w-5"/>Bereits eingelöst</div>:<div className="relative mt-6"><p className="mb-2 text-xs font-bold text-slate-400">Server auswählen</p><div className="relative"><button onClick={()=>setOpen(!open)} className="flex min-h-11 w-full items-center justify-between rounded-xl border border-white/10 bg-black/20 px-4 text-sm text-white"><span>{selected?.name||"Server auswählen"}</span><ChevronDown className={`h-4 w-4 text-slate-500 transition ${open?"rotate-180":""}`}/></button>{open&&<div className="absolute left-0 right-0 top-12 z-10 max-h-52 overflow-y-auto rounded-xl border border-white/10 bg-[#17171e] p-2 shadow-2xl">{servers.length?servers.map((server)=><button key={server.id} onClick={()=>{setGuild(server.id);setOpen(false)}} className={`flex min-h-10 w-full items-center justify-between rounded-lg px-3 text-left text-sm ${guild===server.id?"bg-indigo-500/15 text-indigo-200":"text-slate-300 hover:bg-white/5"}`}><span className="truncate">{server.name}</span>{guild===server.id&&<Check className="h-4 w-4"/>}</button>):<p className="p-3 text-center text-xs text-slate-500">Kein verwalteter Server mit University Bot.</p>}</div>}</div><button disabled={!guild} onClick={async()=>{await api.claimIdeaReward(reward.idea_id,guild);setClaimed(true)}} className="mt-3 min-h-11 w-full rounded-xl bg-emerald-600 text-sm font-bold text-white hover:bg-emerald-500 disabled:opacity-40">Für diesen Server einlösen</button></div>}</div>;
}
function Tip({ number, title, text }: { number: string; title: string; text: string }) { return <div className={`${CARD} p-5`}><span className="text-xs font-black text-indigo-400">{number}</span><h3 className="mt-2 text-sm font-bold text-white">{title}</h3><p className="mt-1 text-xs leading-5 text-slate-400">{text}</p></div>; }
function Field({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) { return <label className="block"><span className="mb-2 flex items-center justify-between gap-3 text-sm font-bold text-slate-300"><span>{label}</span><span className="text-xs font-normal text-slate-600">{hint}</span></span>{children}</label>; }
function Loading() { return <div className="grid min-h-72 place-items-center"><div className="text-center"><Loader2 className="mx-auto h-6 w-6 animate-spin text-indigo-400"/><p className="mt-3 text-sm text-slate-500">Wird geladen …</p></div></div>; }
function Empty({ icon, title, text, children }: { icon: React.ReactNode; title: string; text: string; children?: React.ReactNode }) { return <div className={`${CARD} mt-6 py-20 text-center`}><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-indigo-500/10 text-indigo-400">{icon}</span><h2 className="mt-4 text-lg font-bold text-white">{title}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">{text}</p>{children&&<div className="mt-5">{children}</div>}</div>; }
