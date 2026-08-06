import React from "react";
import { Headphones } from "lucide-react";
import { SupportQueuePanel } from "@/components/dashboard/support-queue-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Headphones className="h-6 w-6 text-primary" />
          Support-Warteraum
        </h2>
        <p className="text-slate-400 mt-1">
          Ein Sprachkanal, in dem niemand allein wartet &mdash; der Bot begr&uuml;&szlig;t
          und spielt Musik, bis das Team da ist.
        </p>
      </div>

      <SupportQueuePanel guildId={params.guildId} />
    </div>
  );
}
