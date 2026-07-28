import React from "react";
import { ShieldCheck } from "lucide-react";
import { VerifyPanel } from "@/components/dashboard/verify-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-primary" />
          Verifizierung
        </h2>
        <p className="text-slate-400 mt-1">
          Neue Mitglieder freischalten &mdash; mit eigenen Texten.
        </p>
      </div>

      <VerifyPanel guildId={params.guildId} />
    </div>
  );
}
