import React from "react";
import { ShieldAlert } from "lucide-react";
import { EmergencyPanel } from "@/components/dashboard/emergency-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function EmergencyPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <ShieldAlert className="h-6 w-6 text-primary" />
          Emergency
        </h2>
        <p className="text-slate-400 mt-1">
          Strip dangerous permissions from every role while the server is under attack.
        </p>
      </div>
      <EmergencyPanel guildId={params.guildId} />
    </div>
  );
}
