"use client";

/**
 * Der Verweis, der an die Stelle einer Log-Einstellung tritt.
 *
 * Die Log-Kanäle aller Module liegen jetzt gesammelt unter Bot-Logs.
 * Sie zusätzlich auf der Modul-Seite stehen zu lassen, hieße: zwei
 * Felder für denselben Wert, und eines davon zeigt nach dem Speichern
 * am anderen Ort etwas Veraltetes an.
 *
 * Also steht hier stattdessen ein Verweis. Er nimmt `?highlight=<key>`
 * mit, damit der Zielreiter genau den richtigen Abschnitt aufklappt
 * und kurz gelb hervorhebt — ohne das landet man auf einer Liste mit
 * sechs Einträgen und sucht, welcher gemeint war.
 */

import React from "react";
import Link from "next/link";
import { ArrowRight, ScrollText } from "lucide-react";

export function LogUmgezogen({
  guildId,
  logKey,
  was,
}: {
  guildId: string;
  /** Der Schlüssel aus utils/bot_logs.py QUELLEN. */
  logKey: string;
  /** Was hier protokolliert wird, für den Satz. */
  was: string;
}) {
  return (
    <Link
      href={`/dashboard/guild/${guildId}/botlogs?highlight=${logKey}`}
      className="group flex items-center gap-3 rounded-2xl border border-slate-800 bg-[#0f0f13] p-4 transition hover:border-primary/40 hover:bg-white/[0.03]"
    >
      <div className="rounded-xl bg-primary/10 p-2">
        <ScrollText className="h-4 w-4 text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-white">
          Log-Kanal ist umgezogen
        </div>
        <p className="mt-0.5 text-xs text-slate-500">
          {was} stellst du jetzt unter{" "}
          <span className="text-slate-400">Bot-Logs</span> ein — dort stehen
          alle Protokolle beisammen.
        </p>
      </div>
      <ArrowRight className="h-4 w-4 shrink-0 text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-primary" />
    </Link>
  );
}
