import React from "react";
import { ClipboardList } from "lucide-react";
import dynamicImport from "next/dynamic";

// Nicht zwischenspeichern: das Panel liest den gespeicherten Stand, und
// eine alte Kopie macht Änderungen still wieder rückgängig.
export const dynamic = "force-dynamic";
export const revalidate = 0;

const ApplicationsPanel = dynamicImport(
  () =>
    import("@/components/dashboard/applications-panel").then(
      (m) => m.ApplicationsPanel,
    ),
  { loading: () => <div className="h-96 w-full animate-pulse bg-slate-800/20 rounded-3xl" /> }
);

export default function ApplicationsPage({
  params,
}: {
  params: { guildId: string };
}) {
  return (
    <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <ClipboardList className="h-6 w-6 text-primary" />
          Bewerbungen
        </h2>
        <p className="text-slate-400 mt-1">
          Ein Auswahlmenü im Kanal, die Fragen kommen per Direktnachricht.
        </p>
      </div>

      <ApplicationsPanel guildId={params.guildId} />
    </div>
  );
}
