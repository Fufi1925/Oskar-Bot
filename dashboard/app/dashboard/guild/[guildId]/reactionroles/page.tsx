import React from "react";
import { Smile } from "lucide-react";
import { ReactionRolesPanel } from "@/components/dashboard/reactionroles-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function ReactionRolesPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Smile className="h-6 w-6 text-primary" />
          Reaktions-Rollen
        </h2>
        <p className="text-slate-400 mt-1">
          Auf ein Emoji klicken, Rolle bekommen.
        </p>
      </div>

      <ReactionRolesPanel guildId={params.guildId} />
    </div>
  );
}
