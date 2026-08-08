import React from "react";
import { Sparkles } from "lucide-react";
import { TemplateCommunityPanel } from "@/components/dashboard/template-community-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-primary" />
          Community-Vorlagen
          <span className="text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md bg-amber-400/10 text-amber-400 border border-amber-400/20">
            Experimentell
          </span>
        </h2>
        <p className="text-slate-400 mt-1">
          Fertige Server-Aufbauten von anderen &mdash; ansehen, ausw&auml;hlen,
          &uuml;bernehmen.
        </p>
      </div>

      <TemplateCommunityPanel guildId={params.guildId} />
    </div>
  );
}
