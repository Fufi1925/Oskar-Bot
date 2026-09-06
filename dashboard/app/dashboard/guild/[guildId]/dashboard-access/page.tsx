import React from "react";
import { KeyRound } from "lucide-react";
import { GuildAccessPanel } from "@/components/dashboard/guild-access-panel";

export const dynamic = "force-dynamic";

export default function DashboardAccessPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2 tracking-tight">
          <KeyRound className="h-6 w-6 text-primary" />
          Dashboard Access
        </h2>
        <p className="text-slate-400 mt-1 text-sm">
          Bestimme, welche Rollen und Mitglieder dieses Server-Dashboard öffnen dürfen.
        </p>
      </div>
      <GuildAccessPanel guildId={params.guildId} />
    </div>
  );
}
