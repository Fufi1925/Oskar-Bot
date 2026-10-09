"use client";

import { useEffect, useState } from "react";
import { BrainCircuit, Ticket } from "lucide-react";
import { api } from "@/lib/api";
import { useWebsiteLocale } from "@/lib/i18n/locale";
import { TicketPanels } from "./ticket-panels";
import { TicketAiPanel } from "./ticket-ai-panel";

export function TicketHub({ guildId }: { guildId: string }) {
  const locale = useWebsiteLocale();
  const t = (de: string, en: string) => locale === "en-GB" ? en : de;
  const [tab, setTab] = useState("panels"), [available, setAvailable] = useState(false);
  useEffect(() => {
    let alive = true;
    api.getTicketAiAvailability(guildId).then(value => { if (alive) setAvailable(value.available); }).catch(() => {});
    const hash = () => setTab(window.location.hash === "#ticket-ai" ? "ai" : "panels");
    hash(); window.addEventListener("hashchange", hash);
    return () => { alive = false; window.removeEventListener("hashchange", hash); };
  }, [guildId]);
  return <div className="space-y-5">
    {available && <nav aria-label={t("Ticketbereich", "Ticket workspace")} className="flex gap-2 rounded-2xl border border-white/[.07] bg-[#202124] p-2">
      {[{ id: "panels", label: t("Ticket-Panels", "Ticket panels"), icon: Ticket }, { id: "ai", label: t("Ticket-KI", "Ticket AI"), icon: BrainCircuit }].map(item => <button key={item.id} aria-current={tab === item.id ? "page" : undefined} onClick={() => { setTab(item.id); window.history.replaceState(null, "", item.id === "ai" ? "#ticket-ai" : window.location.pathname); }} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium ${tab === item.id ? "bg-indigo-400/15 text-indigo-200" : "text-slate-400 hover:bg-white/5"}`}><item.icon className="h-4 w-4" />{item.label}</button>)}
    </nav>}
    {/* Keep editor state when switching between panels and their assistant. */}
    <div hidden={available && tab === "ai"}><TicketPanels guildId={guildId} /></div>
    {available && <div hidden={tab !== "ai"}><TicketAiPanel guildId={guildId} /></div>}
  </div>;
}
