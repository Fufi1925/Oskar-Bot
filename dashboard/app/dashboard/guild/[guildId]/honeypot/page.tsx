import { ShieldAlert } from "lucide-react";
import { ModerationHeader } from "@/components/dashboard/moderation-design";
import React from "react";
import { HoneypotPanel } from "@/components/dashboard/honeypot-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-5 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <ModerationHeader icon={ShieldAlert} title="Honeypot" description="Ein Köder-Kanal ganz oben, in den niemand schreiben soll — wer es doch tut, wird softgebannt." />

      <HoneypotPanel guildId={params.guildId} />
    </div>
  );
}
