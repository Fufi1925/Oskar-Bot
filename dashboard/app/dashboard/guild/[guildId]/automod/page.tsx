import React from "react";
import { Shield } from "lucide-react";
import { AutomodPanel } from "@/components/dashboard/automod-panel";
import { AutomodStatus } from "@/components/dashboard/automod-status";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Shield className="h-6 w-6 text-primary" />
          Automod
        </h2>
        <p className="text-slate-400 mt-1">
          Spam, Caps, Links und Massenpings automatisch abfangen.
        </p>
      </div>

      {/* Reads back what the listeners actually see, so the tab can
          prove a saved change is live rather than just claiming it. */}
      <AutomodStatus guildId={params.guildId} />

      <AutomodPanel guildId={params.guildId} />
    </div>
  );
}
