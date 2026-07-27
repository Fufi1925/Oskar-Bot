import React from "react";
import { BarChart4 } from "lucide-react";
import { LevelingPanel } from "@/components/dashboard/leveling-panel";

// The panel loads its own data; caching it here meant a save was followed
// by the page showing the values from before.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function LevelingPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <BarChart4 className="h-6 w-6 text-primary" />
          Level-System
        </h2>
        <p className="text-slate-400 mt-1">
          XP fürs Schreiben, Belohnungsrollen und die Bestenliste.
        </p>
      </div>

      <LevelingPanel guildId={params.guildId} />
    </div>
  );
}
