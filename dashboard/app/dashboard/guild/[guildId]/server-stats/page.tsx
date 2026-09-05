import React from "react";
import { BarChart4 } from "lucide-react";

import { ServerStatsPanel } from "@/components/dashboard/server-stats-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="mx-auto max-w-6xl space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="flex items-center gap-2 text-2xl font-bold text-white">
          <BarChart4 className="h-6 w-6 text-sky-400" />
          Server Stats
        </h2>
        <p className="mt-1 text-slate-400">
          Aktuelle Mitgliederzahlen als automatisch gepflegte Sprachkanäle anzeigen.
        </p>
      </div>
      <ServerStatsPanel guildId={params.guildId} />
    </div>
  );
}
