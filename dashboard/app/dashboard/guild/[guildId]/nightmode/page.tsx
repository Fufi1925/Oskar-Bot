import { ModerationHeader } from "@/components/dashboard/moderation-design";
import React from "react";
import { Moon } from "lucide-react";
import { NightmodePanel } from "@/components/dashboard/extras-panels";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-5 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <ModerationHeader icon={Moon} title="Nachtmodus" description="Kanäle nachts automatisch schließen." />

      <NightmodePanel guildId={params.guildId} />
    </div>
  );
}
