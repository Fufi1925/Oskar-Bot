import React, { Suspense } from "react";
import { ScrollText } from "lucide-react";
import { BotLogsPanel } from "@/components/dashboard/bot-logs-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <ScrollText className="h-6 w-6 text-primary" />
          Bot-Logs
        </h2>
        <p className="text-slate-400 mt-1">
          Alles, was der Bot selbst protokolliert &mdash; an einer Stelle statt
          verteilt auf sechs Seiten.
        </p>
      </div>

      {/* useSearchParams() braucht eine Suspense-Grenze, sonst faellt
          die ganze Seite beim Bauen auf Client-Rendering zurueck. */}
      <Suspense fallback={null}>
        <BotLogsPanel guildId={params.guildId} />
      </Suspense>
    </div>
  );
}
