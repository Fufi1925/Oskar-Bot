import React from "react";
import { Command } from "lucide-react";
import { api } from "@/lib/api";
import { CustomCommandsPanel } from "@/components/dashboard/custom-commands-panel";

export const dynamic = "force-dynamic";

export default async function CustomCommandsPage({ params }: { params: { guildId: string } }) {
  const config = await api.getPrefix(params.guildId).catch(() => ({ prefix: ">" }));
  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2 tracking-tight"><Command className="h-6 w-6 text-primary" />Custom Commands</h2>
        <p className="text-slate-400 mt-1 text-sm">Erstelle bis zu drei Befehle und bestimme selbst, ob Präfix, Slash oder Texterkennung verwendet wird.</p>
      </div>
      <CustomCommandsPanel guildId={params.guildId} prefix={config.prefix || ">"} />
    </div>
  );
}
