import React from "react";
import { TicketHub } from "@/components/dashboard/ticket-hub";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function TicketsPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-5 pb-20 sm:pb-0">
      <TicketHub guildId={params.guildId} />
    </div>
  );
}
