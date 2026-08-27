import React from "react";
import { Database } from "lucide-react";
import { BackupPanel } from "@/components/dashboard/backup-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Database className="h-6 w-6 text-amber-400" />
          Backup
        </h2>
        <p className="text-slate-400 mt-1">
          Kan&auml;le, Rollen, Rechte und alle Dashboard-Einstellungen sichern
          &mdash; ein Knopf, keine R&uuml;ckfragen.
        </p>
      </div>

      <BackupPanel guildId={params.guildId} />
    </div>
  );
}
