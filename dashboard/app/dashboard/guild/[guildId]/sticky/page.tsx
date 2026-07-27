import React from "react";
import { Pin } from "lucide-react";
import { StickyPanel } from "@/components/dashboard/extras-panels";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Pin className="h-6 w-6 text-primary" />
          Sticky-Nachricht
        </h2>
        <p className="text-slate-400 mt-1">Eine Nachricht, die immer unten bleibt.</p>
      </div>

      <StickyPanel guildId={params.guildId} />
    </div>
  );
}
