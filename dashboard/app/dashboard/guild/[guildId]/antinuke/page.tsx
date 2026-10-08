import { ModerationHeader } from "@/components/dashboard/moderation-design";
import React from "react";
import { ShieldAlert } from "lucide-react";
import { AntiNukePanel } from "@/components/dashboard/antinuke-panel";
import { NukeAlertPanel } from "@/components/dashboard/nuke-alert-panel";

export const dynamic = "force-dynamic";

export default function AntiNukePage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-5 pb-8">
      <ModerationHeader icon={ShieldAlert} title="Anti-Nuke" description="Schutz davor, dass jemand mit Rechten den Server in Minuten leerräumt — Kanäle löschen, alle bannen, Rollen zerschießen." />

      <AntiNukePanel guildId={params.guildId} reports={<NukeAlertPanel guildId={params.guildId} />} />
    </div>
  );
}
