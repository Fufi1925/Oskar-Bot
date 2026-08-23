import React from "react";
import { HoneypotPanel } from "@/components/dashboard/honeypot-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <span className="text-2xl leading-none">🍯</span>
          Honeypot
        </h2>
        <p className="text-slate-400 mt-1">
          Ein K&ouml;der-Kanal ganz oben, in den niemand schreiben soll &mdash;
          wer es doch tut, wird softgebannt.
        </p>
      </div>

      <HoneypotPanel guildId={params.guildId} />
    </div>
  );
}
