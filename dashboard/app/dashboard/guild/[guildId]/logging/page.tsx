import React from "react";
import { BellRing } from "lucide-react";
import { LoggingPanel } from "@/components/dashboard/logging-panel";

export const dynamic = "force-dynamic";

export default function LoggingPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-black text-white flex items-center gap-2 tracking-tight">
          <BellRing className="h-6 w-6 text-primary" />
          Protokollierung
        </h2>
        <p className="text-slate-400 mt-1 text-sm">
          Wer hat was gelöscht, wer ist gegangen, wer hat eine Rolle bekommen —
          der Bot schreibt es in einen Kanal deiner Wahl.
        </p>
      </div>

      <LoggingPanel guildId={params.guildId} />
    </div>
  );
}
