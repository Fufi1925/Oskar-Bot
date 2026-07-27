import React from "react";
import { Terminal } from "lucide-react";
import { NoPrefixPanel } from "@/components/dashboard/noprefix-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function NoPrefixPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Terminal className="h-6 w-6 text-primary" />
          Ohne Prefix
        </h2>
        <p className="text-slate-400 mt-1">
          Wer Befehle tippen darf, ohne das Prefix davorzusetzen.
        </p>
      </div>

      <NoPrefixPanel guildId={params.guildId} />
    </div>
  );
}
