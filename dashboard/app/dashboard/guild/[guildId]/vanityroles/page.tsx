import React from "react";
import { Link2 } from "lucide-react";
import { VanityPanel } from "@/components/dashboard/vanity-panel";

// The panel loads its own data; caching the page meant a save was
// followed by the old values reappearing.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function VanityRolesPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Link2 className="h-6 w-6 text-primary" />
          Vanity-Rollen
        </h2>
        <p className="text-slate-400 mt-1">
          Eine Rolle für alle, die den Server in ihrem Status bewerben.
        </p>
      </div>

      <VanityPanel guildId={params.guildId} />
    </div>
  );
}
