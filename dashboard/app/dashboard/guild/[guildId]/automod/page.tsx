import { ModerationHeader } from "@/components/dashboard/moderation-design";
import React from "react";
import { Shield } from "lucide-react";
import { AutomodPanel } from "@/components/dashboard/automod-panel";
import { AutomodStatus } from "@/components/dashboard/automod-status";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-5 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <ModerationHeader icon={Shield} title="AutoMod" description="Spam, Caps, Links und Massenpings automatisch abfangen." />

      <AutomodPanel guildId={params.guildId} liveStatus={<AutomodStatus guildId={params.guildId} />} />

    </div>
  );
}
