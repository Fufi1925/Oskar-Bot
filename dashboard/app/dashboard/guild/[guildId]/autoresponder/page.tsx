import React from "react";
import { MessageSquare } from "lucide-react";
import { AutoresponderPanel } from "@/components/dashboard/autoresponder-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function AutoresponderPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <MessageSquare className="h-6 w-6 text-primary" />
          Autoresponder
        </h2>
        <p className="text-slate-400 mt-1">Automatic replies to trigger words.</p>
      </div>
      <AutoresponderPanel guildId={params.guildId} />
    </div>
  );
}
