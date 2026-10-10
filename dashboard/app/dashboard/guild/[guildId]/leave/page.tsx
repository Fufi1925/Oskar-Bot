import { DoorOpen } from "lucide-react";
import { LeaveForm } from "@/components/dashboard/leave-form";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function LeavePage({ params }: { params: { guildId: string } }) {
  return <div className="mx-auto max-w-6xl space-y-5">
    <header className="rounded-2xl border border-white/[.07] cloudtix-workspace-card bg-[#202124] p-5 sm:p-6">
      <div className="flex items-start gap-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-rose-400/10 text-rose-300"><DoorOpen className="h-5 w-5" /></span><div><h1 className="text-xl font-semibold text-white sm:text-2xl">Abschied</h1><p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-400">Gestalte die Abschiedsnachricht wie deine Begrüßung: Kanal, Text, Embed, Bilder und Platzhalter – mit direkter Vorschau.</p></div></div>
    </header>
    <LeaveForm guildId={params.guildId} />
  </div>;
}
