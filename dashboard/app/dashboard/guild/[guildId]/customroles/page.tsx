import React from "react";
import { Sparkles } from "lucide-react";
import { CustomRolesPanel } from "@/components/dashboard/voice-panels";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-primary" />
          Eigene Rollen
        </h2>
        <p className="text-slate-400 mt-1">
          Eigene Befehle, die eine Rolle geben oder wegnehmen.
        </p>
      </div>

      <CustomRolesPanel guildId={params.guildId} />
    </div>
  );
}
