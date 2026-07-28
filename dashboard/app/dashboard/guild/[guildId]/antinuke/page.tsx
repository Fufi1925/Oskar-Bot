import React from "react";
import { ShieldAlert } from "lucide-react";
import { AntiNukePanel } from "@/components/dashboard/antinuke-panel";
import { NukeAlertPanel } from "@/components/dashboard/nuke-alert-panel";

export const dynamic = "force-dynamic";

export default function AntiNukePage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-black text-white flex items-center gap-2 tracking-tight">
          <ShieldAlert className="h-6 w-6 text-primary" />
          Anti-Nuke
        </h2>
        <p className="text-slate-400 mt-1 text-sm">
          Schutz davor, dass jemand mit Rechten den Server in Minuten
          leerräumt — Kanäle löschen, alle bannen, Rollen zerschießen.
        </p>
      </div>

      <AntiNukePanel guildId={params.guildId} />

      {/* Reporting: whether an attack was stopped, or only seen. */}
      <NukeAlertPanel guildId={params.guildId} />
    </div>
  );
}
