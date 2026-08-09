import React from "react";
import { Users } from "lucide-react";
import { TeamlistPanel } from "@/components/dashboard/teamlist-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users className="h-6 w-6 text-primary" />
          Teamliste
        </h2>
        <p className="text-slate-400 mt-1">
          Wer im Team ist, nach Rollen geordnet &mdash; im Kanal sichtbar und
          immer aktuell.
        </p>
      </div>

      <TeamlistPanel guildId={params.guildId} />
    </div>
  );
}
