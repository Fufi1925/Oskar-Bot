import React from "react";
import { Ticket } from "lucide-react";
import { TicketPanels } from "@/components/dashboard/ticket-panels";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function TicketsPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Ticket className="h-6 w-6 text-primary" />
          Tickets
        </h2>
        <p className="text-slate-400 mt-1">
          Panels, Kategorien und wer die Tickets bearbeitet.
        </p>
      </div>

      <TicketPanels guildId={params.guildId} />
    </div>
  );
}
