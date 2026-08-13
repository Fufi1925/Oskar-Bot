"use client";

/**
 * Der Verlauf auf der Einstiegsseite des Dashboards.
 *
 * ── Warum eine Serverauswahl und keine Summe ────────────────────────
 *
 * Die naheliegende Lösung wäre gewesen, die Server dieses Nutzers zu
 * addieren. Dagegen sprechen zwei Dinge, und das zweite ist das
 * wichtigere:
 *
 *   1. Jeder Server ist eine eigene Anfrage. Bei zwölf Servern sind
 *      das zwölf Anfragen für ein Bild, das man vielleicht gar nicht
 *      anschaut.
 *   2. **Die Summe beantwortet keine Frage, die jemand hat.** Wer
 *      drei Server betreut, will wissen, wie es *dem einen* geht, der
 *      gerade Ärger macht. „Insgesamt 40 Beitritte“ verrät nicht, auf
 *      welchem.
 *
 * Voreingestellt ist der größte Server — der, bei dem eine
 * Veränderung am ehesten auffällt.
 *
 * ── Berechtigung ────────────────────────────────────────────────────
 *
 * Es wird `/guilds/<id>/history` benutzt, nicht `/admin/history`.
 * Der Admin-Endpunkt verlangt `metrics.view`; ein normaler
 * Server-Inhaber hat das nicht und bekäme hier nur eine
 * Fehlermeldung. Der Server-Endpunkt prüft genau das Richtige:
 * „Server verwalten“ auf diesem einen Server.
 */

import React, { useState } from "react";
import { HistoryCharts } from "@/components/dashboard/history-charts";

export interface ChartGuild {
  id: string;
  name: string;
  memberCount: number | null;
}

export function MyServersChart({ guilds }: { guilds: ChartGuild[] }) {
  // Der größte zuerst. Die Liste kommt bereits sortiert an, aber
  // darauf zu bauen hieße, dass eine Änderung dort hier etwas
  // kaputtmacht, ohne dass es jemand merkt.
  const sortiert = React.useMemo(
    () => [...guilds].sort((a, b) => (b.memberCount ?? 0) - (a.memberCount ?? 0)),
    [guilds],
  );

  const [gewaehlt, setGewaehlt] = useState<string>(sortiert[0]?.id ?? "");

  if (sortiert.length === 0) return null;

  const aktiv = sortiert.some((g) => g.id === gewaehlt)
    ? gewaehlt
    : sortiert[0].id;

  return (
    <section className="space-y-3">
      {sortiert.length > 1 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] text-slate-500">Verlauf von</span>
          <div className="flex flex-wrap gap-1">
            {sortiert.slice(0, 5).map((guild) => (
              <button
                key={guild.id}
                type="button"
                onClick={() => setGewaehlt(guild.id)}
                aria-pressed={aktiv === guild.id}
                className={
                  aktiv === guild.id
                    ? "max-w-[200px] truncate rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-1.5 text-[13px] font-semibold text-white"
                    : "max-w-[200px] truncate rounded-lg border border-slate-800 bg-[#131318] px-3 py-1.5 text-[13px] text-slate-400 transition-colors hover:border-slate-700 hover:text-white"
                }
              >
                {guild.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* `key` erzwingt einen frischen Baustein je Server. Ohne ihn
          bliebe der alte Verlauf stehen, bis die neue Antwort da ist
          -- und dann stünde kurz die Kurve des falschen Servers unter
          dem Namen des richtigen. */}
      <HistoryCharts key={aktiv} guildId={aktiv} />
    </section>
  );
}
