import React from "react";
import { Palette } from "lucide-react";
import { DesignPanel } from "@/components/dashboard/design-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Palette className="h-6 w-6 text-amber-400" />
          Design
        </h2>
        <p className="text-slate-400 mt-1">
          Wie der Bot auf diesem Server hei&szlig;t und aussieht &mdash; mit
          Live-Vorschau.
        </p>
      </div>

      <DesignPanel guildId={params.guildId} />
    </div>
  );
}
