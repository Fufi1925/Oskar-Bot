import React from "react";
import { LogOut } from "lucide-react";
import dynamicImport from "next/dynamic";

// Wie bei der Begrüßung: nicht zwischenspeichern. Das Formular liest die
// gespeicherte Einstellung, und eine alte Kopie macht Änderungen still
// wieder rückgängig.
export const dynamic = "force-dynamic";
export const revalidate = 0;

const LeaveForm = dynamicImport(
  () => import("@/components/dashboard/leave-form").then((m) => m.LeaveForm),
  { loading: () => <div className="h-96 w-full animate-pulse bg-slate-800/20 rounded-3xl" /> }
);

export default function LeavePage({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <LogOut className="h-6 w-6 text-primary" />
          Verabschiedung
        </h2>
        <p className="text-slate-400 mt-1">
          Was im Kanal steht, wenn jemand den Server verlässt.
        </p>
      </div>

      <LeaveForm guildId={params.guildId} />
    </div>
  );
}
