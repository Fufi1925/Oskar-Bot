import React from "react";
import { Music } from "lucide-react";
import { MusicPanel } from "@/components/dashboard/music-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Music className="h-6 w-6 text-primary" />
          Musik
        </h2>
        <p className="text-slate-400 mt-1">
          Ein fester Sprachkanal, Playlists zum Anlegen und Starten &mdash; und
          eine Live-Ansicht dessen, was gerade l&auml;uft.
        </p>
      </div>

      <MusicPanel guildId={params.guildId} />
    </div>
  );
}
