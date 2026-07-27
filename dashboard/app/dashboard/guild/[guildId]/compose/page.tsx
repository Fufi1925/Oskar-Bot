import React from "react";
import { PenLine } from "lucide-react";
import { ComposePanel } from "@/components/dashboard/compose-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function ComposePage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <PenLine className="h-6 w-6 text-primary" />
          Eigene Nachricht
        </h2>
        <p className="text-slate-400 mt-1">
          Eine Nachricht selbst gestalten und als Bot in einen Kanal schicken.
        </p>
      </div>

      <ComposePanel guildId={params.guildId} />
    </div>
  );
}
