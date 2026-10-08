import { ModerationHeader } from "@/components/dashboard/moderation-design";
import React from "react";
import { ShieldAlert } from "lucide-react";
import { EmergencyPanel } from "@/components/dashboard/emergency-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function EmergencyPage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <ModerationHeader icon={ShieldAlert} title="Notfall" description="Strip dangerous permissions from every role while the server is under attack." />
      <EmergencyPanel guildId={params.guildId} />
    </div>
  );
}
