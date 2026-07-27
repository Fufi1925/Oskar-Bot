import React from "react";
import { SmilePlus } from "lucide-react";
import dynamicImport from "next/dynamic";
import { api } from "@/lib/api";

// The channel list is fetched by the picker itself, so the page no longer
// needs to pass it down. It also has to stay uncached: the form reads the
// saved configuration and a stale copy silently reverts edits.
export const dynamic = "force-dynamic";
export const revalidate = 0;

const WelcomeForm = dynamicImport(
  () => import("@/components/dashboard/welcome-form").then((m) => m.WelcomeForm),
  { loading: () => <div className="h-96 w-full animate-pulse bg-slate-800/20 rounded-3xl" /> }
);

export default async function WelcomePage({ params }: { params: { guildId: string } }) {
  const welcomeData = await api.getWelcome(params.guildId);

  return (
    <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <SmilePlus className="h-6 w-6 text-primary" />
          Begrüßung
        </h2>
        <p className="text-slate-400 mt-1">
          Was neue Mitglieder als Erstes zu sehen bekommen.
        </p>
      </div>

      <WelcomeForm
        initialConfig={welcomeData || { guild_id: Number(params.guildId) }}
        guildId={params.guildId}
      />
    </div>
  );
}
