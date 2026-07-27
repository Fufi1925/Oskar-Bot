import React from "react";
import { Gift } from "lucide-react";
import { GiveawaysPanel } from "@/components/dashboard/giveaways-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function GiveawaysPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Gift className="h-6 w-6 text-primary" />
          Gewinnspiele
        </h2>
        <p className="text-slate-400 mt-1">
          Starten, laufen lassen und auslosen — ohne das Dashboard zu verlassen.
        </p>
      </div>

      {/* The channel picker loads its own data, so no props needed here. */}
      <GiveawaysPanel guildId={params.guildId} />
    </div>
  );
}
