import React from "react";
import { Ticket } from "lucide-react";
import { TicketPanels } from "@/components/dashboard/ticket-panels";
import { TicketAiPanel } from "@/components/dashboard/ticket-ai-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function TicketsPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <div className="rounded-2xl border border-white/[.07] bg-[#202124] p-5 sm:p-6">
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Ticket className="h-6 w-6 text-primary" />
          Tickets
        </h2>
        <p className="text-slate-400 mt-1">
          Panels, Kategorien und wer die Tickets bearbeitet.
        </p>
      </div>

      <TicketPanels guildId={params.guildId} />
      <TicketAiPanel guildId={params.guildId} />
    </div>
  );
}
