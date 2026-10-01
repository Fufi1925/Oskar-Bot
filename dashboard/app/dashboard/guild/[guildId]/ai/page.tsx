"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Check, Loader2, Send, ShieldCheck, Sparkles, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface Message { role: "user" | "assistant"; content: string; }
interface Plan { plan_id: string; reply: string; operations: any[]; }

const MODULE_NAMES: Record<string, string> = {
  antinuke: "Anti-Nuke", automod: "Automod", welcome: "Willkommen", leave: "Abschied",
  tickets: "Tickets", verification: "Verifizierung", leveling: "Leveling", giveaways: "Giveaways",
  autorole: "Auto-Rolle", reactionroles: "Reaktions-Rollen", logging: "Logging",
  autoreact: "Auto-Reaktion", autoresponder: "Autoresponder", counting: "Counting",
  music: "Musik", nightmode: "Nachtmodus", jail: "Jail", backup: "Backup",
};

function operationText(operation: any) {
  if (operation.type === "set_module") {
    return `${MODULE_NAMES[operation.module] || operation.module}: ${operation.enabled ? "aktivieren" : "deaktivieren"}`;
  }
  if (operation.type === "configure_welcome") {
    return `Willkommensnachricht einrichten und ${operation.enabled ? "aktivieren" : "deaktivieren"}`;
  }
  return "Dashboard-Einstellung ändern";
}

export default function DashboardAiPage({ params }: { params: { guildId: string } }) {
  const router = useRouter();
  const [accessChecked, setAccessChecked] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Beschreibe, was ich auf diesem Server im Dashboard einstellen soll. Ich erstelle zuerst einen Plan und ändere nichts ohne deine Bestätigung." },
  ]);
  const [input, setInput] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    api.getDashboardAiAccess(params.guildId)
      .then((data) => {
        if (!active) return;
        if (!data.allowed) router.replace(`/dashboard/guild/${params.guildId}`);
        else setAccessChecked(true);
      })
      .catch(() => router.replace(`/dashboard/guild/${params.guildId}`));
    return () => { active = false; };
  }, [params.guildId, router]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setInput("");
    setPlan(null);
    setBusy(true);
    try {
      const result = await api.planDashboardAi(params.guildId, text, next.slice(-7));
      setMessages((old) => [...old, { role: "assistant", content: result.reply }]);
      if (result.operations?.length) setPlan(result);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
    } catch (error: any) {
      toast.error(error?.message || "Die Dashboard-KI konnte keinen Plan erstellen.");
    } finally { setBusy(false); }
  };

  const apply = async () => {
    if (!plan || busy) return;
    setBusy(true);
    try {
      const result = await api.applyDashboardAi(params.guildId, plan.plan_id);
      for (const operation of result.applied || []) {
        const moduleKey = operation.type === "configure_welcome" ? "welcome" : operation.module;
        const enabled = Boolean(operation.enabled);
        if (moduleKey) window.dispatchEvent(new CustomEvent("guild-module-state", { detail: { guildId: params.guildId, module: moduleKey, enabled } }));
      }
      setMessages((old) => [...old, { role: "assistant", content: `${result.count} Änderung(en) wurden sicher angewendet.` }]);
      setPlan(null);
      toast.success("Dashboard-Einstellungen wurden angewendet.");
    } catch (error: any) {
      toast.error(error?.message || "Die Änderungen konnten nicht angewendet werden.");
    } finally { setBusy(false); }
  };

  if (!accessChecked) {
    return <div className="grid min-h-[420px] place-items-center"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>;
  }

  return (
    <div className="mx-auto max-w-5xl overflow-hidden rounded-3xl border border-white/[.08] bg-[#101116]">
      <header className="flex items-center gap-3 border-b border-white/[.07] px-5 py-4">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-violet-500/15 text-violet-300"><Sparkles className="h-5 w-5" /></span>
        <div><h1 className="font-black text-white">University Dashboard KI</h1><p className="text-xs text-slate-500">Nur Dashboard-Einstellungen dieses Servers · GroqCloud · Änderungen mit Bestätigung</p></div>
        <span className="ml-auto hidden items-center gap-1.5 text-[10px] font-bold uppercase text-emerald-400 sm:flex"><ShieldCheck className="h-4 w-4" /> Servergebunden</span>
      </header>

      <div className="min-h-[460px] space-y-5 p-5 sm:p-7">
        {messages.map((message, index) => (
          <div key={index} className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
            {message.role === "assistant" && <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-violet-500/15 text-violet-300"><Bot className="h-4 w-4" /></span>}
            <div className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-6 ${message.role === "user" ? "bg-blue-500 text-white" : "border border-white/[.07] bg-white/[.035] text-slate-200"}`}>{message.content}</div>
          </div>
        ))}
        {busy && !plan && <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Einstellungen werden sicher geplant …</div>}

        {plan && (
          <div className="ml-0 rounded-2xl border border-amber-400/25 bg-amber-400/[.055] p-5 sm:ml-11">
            <p className="text-sm font-black text-amber-200">Diese Änderungen erst nach Bestätigung anwenden:</p>
            <ul className="mt-3 space-y-2">{plan.operations.map((operation, index) => <li key={index} className="flex items-center gap-2 text-sm text-slate-300"><Check className="h-4 w-4 text-emerald-400" /> {operationText(operation)}</li>)}</ul>
            <div className="mt-5 flex flex-wrap gap-2">
              <button disabled={busy} onClick={apply} className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-500 px-4 text-sm font-bold text-white hover:bg-emerald-400 disabled:opacity-50">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Änderungen anwenden</button>
              <button disabled={busy} onClick={() => setPlan(null)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/10 px-4 text-sm font-bold text-slate-400 hover:bg-white/5"><X className="h-4 w-4" /> Verwerfen</button>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-white/[.07] p-4 sm:p-5">
        <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-black/20 p-2 focus-within:border-violet-400/40">
          <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }} maxLength={2000} rows={2} placeholder="Zum Beispiel: Schalte Anti-Nuke und Welcome ein und erstelle eine freundliche Begrüßung …" className="min-h-[52px] flex-1 resize-none bg-transparent px-3 py-2 text-sm text-white outline-none placeholder:text-slate-600" />
          <button onClick={send} disabled={busy || !input.trim()} className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-violet-500 text-white hover:bg-violet-400 disabled:opacity-40" aria-label="Nachricht senden"><Send className="h-4 w-4" /></button>
        </div>
        <p className="mt-2 text-center text-[10px] text-slate-600">Die KI sieht keine Nachrichten, privaten Nutzerdaten, Tokens oder Daten anderer Server.</p>
      </div>
    </div>
  );
}
