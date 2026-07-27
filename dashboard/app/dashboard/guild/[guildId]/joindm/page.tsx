import React from "react";
import { Mail } from "lucide-react";
import { JoinDMPanel } from "@/components/dashboard/joindm-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function JoinDMPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Mail className="h-6 w-6 text-primary" />
          Beitritts-DM
        </h2>
        <p className="text-slate-400 mt-1">
          Die private Nachricht, die neue Mitglieder bekommen.
        </p>
      </div>

      <JoinDMPanel guildId={params.guildId} />
    </div>
  );
}
