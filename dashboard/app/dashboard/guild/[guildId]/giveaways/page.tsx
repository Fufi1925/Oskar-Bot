import React from "react";
import { Gift } from "lucide-react";
import { api } from "@/lib/api";
import { GiveawaysPanel } from "@/components/dashboard/giveaways-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function GiveawaysPage({ params }: { params: { guildId: string } }) {
  const channels = await api.getChannels(params.guildId).catch(() => []);
  const textChannels = (channels as any[])
    .filter((c) => !c.type || c.type === "text" || c.type === "news")
    .map((c) => ({ id: String(c.id), name: c.name }));

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Gift className="h-6 w-6 text-primary" />
          Giveaways
        </h2>
        <p className="text-slate-400 mt-1">Start and draw giveaways without leaving the dashboard.</p>
      </div>
      <GiveawaysPanel guildId={params.guildId} channels={textChannels} />
    </div>
  );
}
