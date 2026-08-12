"use client";

/**
 * Die Übersicht eines Servers.
 *
 * ── Was hier steht ──────────────────────────────────────────────────
 *
 *   1. Kopfzeile: Fortschritt der Einrichtung, vier Kennzahlen.
 *   2. Nächste Schritte — die drei wichtigsten Module, die noch
 *      fehlen. Nicht irgendwelche: nach Wichtigkeit geordnet.
 *   3. Eingerichtet / Noch offen, jeweils als schlichte Liste.
 *   4. Sicherung & Wiederherstellung im zweiten Reiter.
 *
 * ── Warum „nächste Schritte“ ────────────────────────────────────────
 *
 * Die alte Seite warf 17 gleich aussehende Kacheln aus, davon 14
 * grau. Wer neu ist, sieht daran nicht, womit er anfangen soll —
 * Begrüßung und Anti-Nuke sind wichtiger als Spitznamen. Die
 * Reihenfolge steht in `WICHTIGKEIT`.
 *
 * ── Warum Listen statt Kacheln ──────────────────────────────────────
 *
 * 17 Kacheln à 3 Spalten sind sechs Reihen, die man absuchen muss.
 * Eine Liste liest man von oben nach unten, und der Name steht immer
 * an derselben Stelle.
 */

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity, ArrowRight, BarChart4, Bot, Check, ChevronRight, FileJson,
  FileText, Hash, Link2, Loader2, Mic, Settings, Shield, ShieldCheck,
  SmilePlus, Sparkles, Ticket, UserCheck, Users, Volume2, Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ConfigTransferPanel } from "@/components/dashboard/config-transfer-panel";

const MODULE_ICONS: Record<string, any> = {
  welcome: SmilePlus,
  automod: ShieldCheck,
  antinuke: Shield,
  verification: UserCheck,
  leveling: BarChart4,
  tickets: Ticket,
  logging: FileText,
  autorole: Bot,
  reactionroles: Zap,
  vanityroles: Sparkles,
  customroles: Sparkles,
  invcrole: Volume2,
  j2c: Mic,
  nickname: UserCheck,
  noprefix: Hash,
  tracking: Link2,
  counting: Hash,
};

/**
 * Womit man anfangen sollte.
 *
 * Kleinere Zahl heißt wichtiger. Begrüßung und Schutz zuerst — sie
 * wirken vom ersten Tag an; Spitznamen und Vanity-Rollen sind
 * Feinschliff. Module ohne Eintrag landen hinten.
 */
const WICHTIGKEIT: Record<string, number> = {
  antinuke: 0,
  automod: 1,
  verification: 2,
  welcome: 3,
  logging: 4,
  tickets: 5,
  autorole: 6,
  leveling: 7,
  reactionroles: 8,
  j2c: 9,
  counting: 10,
  tracking: 11,
  customroles: 12,
  invcrole: 13,
  noprefix: 14,
  vanityroles: 15,
  nickname: 16,
};

/** Ein kurzer Satz, was das Modul bringt. */
const WOZU: Record<string, string> = {
  antinuke: "Schützt vor Massenlöschungen und feindlichen Bots.",
  automod: "Filtert Spam, Links und Beleidigungen automatisch.",
  verification: "Hält Raids fern, bevor sie den Server erreichen.",
  welcome: "Begrüßt neue Mitglieder mit Nachricht und Bild.",
  logging: "Schreibt mit, wer was wann geändert hat.",
  tickets: "Support-Anfragen in eigenen Kanälen, geordnet.",
  autorole: "Gibt neuen Mitgliedern automatisch eine Rolle.",
  leveling: "Belohnt aktive Mitglieder mit XP und Rängen.",
  reactionroles: "Rollen per Klick auf ein Emoji.",
  j2c: "Temporäre Sprachkanäle, die sich selbst aufräumen.",
  counting: "Gemeinsam zählen — ein Spiel für den ganzen Server.",
  tracking: "Zeigt, wer wen eingeladen hat.",
  customroles: "Mitglieder gestalten ihre eigene Rolle.",
  invcrole: "Rolle, solange jemand im Sprachkanal ist.",
  noprefix: "Befehle ohne Präfix für ausgewählte Personen.",
  vanityroles: "Rolle für alle mit deinem Link im Status.",
  nickname: "Regeln für Spitznamen, etwa ein fester Vorsatz.",
};

const CARD = "rounded-2xl border border-slate-800 bg-[#131318]";

interface ModuleState {
  key: string;
  label: string;
  configured: boolean;
  entries: number;
  path: string;
}

interface StatusPayload {
  prefix: string;
  modules: ModuleState[];
  active_count: number;
  total_count: number;
  completion: number;
  guild: {
    member_count: number;
    channel_count: number;
    role_count: number;
    bot_count: number;
    boost_level: number;
    boost_count: number;
    verification_level: string;
    created_at: number;
    owner_id: string | null;
  };
}

/** Eine Zeile in einer der beiden Listen. */
function Zeile({
  mod,
  guildId,
  fertig,
}: {
  mod: ModuleState;
  guildId: string;
  fertig: boolean;
}) {
  const Icon = MODULE_ICONS[mod.key] || Settings;
  return (
    <Link
      href={`/dashboard/guild/${guildId}/${mod.path}`}
      className="group flex items-center gap-3.5 rounded-xl border border-slate-800 bg-[#0f0f13] px-4 py-3 transition-colors hover:border-slate-700"
    >
      <Icon
        className={cn(
          "h-[18px] w-[18px] shrink-0",
          fertig ? "text-emerald-400" : "text-slate-600",
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-semibold text-white">
            {mod.label}
          </span>
          {fertig && mod.entries > 0 && (
            <span className="text-[11px] text-slate-600">
              {mod.entries} {mod.entries === 1 ? "Eintrag" : "Einträge"}
            </span>
          )}
        </div>
        <p className="mt-0.5 truncate text-[12px] text-slate-500">
          {WOZU[mod.key] || "Im Dashboard einstellbar."}
        </p>
      </div>
      {fertig ? (
        <span className="flex shrink-0 items-center gap-1 rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
          <Check className="h-2.5 w-2.5" />
          Aktiv
        </span>
      ) : (
        <ChevronRight className="h-4 w-4 shrink-0 text-slate-700 transition-colors group-hover:text-slate-400" />
      )}
    </Link>
  );
}

export default function GuildOverviewPage({
  params,
}: {
  params: { guildId: string };
}) {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"overview" | "backup">("overview");
  const [alleOffenen, setAlleOffenen] = useState(false);

  useEffect(() => {
    api
      .getModuleStatus(params.guildId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [params.guildId]);

  const sortiert = useMemo(() => {
    const rang = (m: ModuleState) => WICHTIGKEIT[m.key] ?? 99;
    // Nicht `module` nennen: der Name ist im Bundle reserviert und
    // Next bricht den Build ab (no-assign-module-variable).
    const liste = data?.modules || [];
    return {
      aktiv: liste.filter((m) => m.configured).sort((a, b) => rang(a) - rang(b)),
      offen: liste.filter((m) => !m.configured).sort((a, b) => rang(a) - rang(b)),
    };
  }, [data]);

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-400 opacity-50" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className={cn(CARD, "p-8 text-center")}>
        <p className="text-[15px] text-slate-300">
          Der Status dieses Servers ließ sich nicht laden.
        </p>
        <p className="mt-2 text-[13px] text-slate-500">
          Der Bot antwortet gerade nicht. Die Einstellungen sind trotzdem
          gespeichert — versuch es in einem Moment erneut.
        </p>
      </div>
    );
  }

  const naechste = sortiert.offen.slice(0, 3);
  const restOffen = sortiert.offen.slice(3);

  const kennzahlen = [
    { label: "Mitglieder", wert: data.guild.member_count.toLocaleString("de-DE"), icon: Users },
    { label: "Kanäle", wert: data.guild.channel_count, icon: Hash },
    { label: "Rollen", wert: data.guild.role_count, icon: Shield },
    { label: "Bots", wert: data.guild.bot_count, icon: Bot },
  ];

  const farbe =
    data.completion >= 70
      ? "text-emerald-400"
      : data.completion >= 35
        ? "text-amber-400"
        : "text-slate-400";
  const balken =
    data.completion >= 70
      ? "bg-emerald-500"
      : data.completion >= 35
        ? "bg-amber-500"
        : "bg-slate-600";

  return (
    <div className="space-y-5">
      {/* Reiter */}
      <div className="flex gap-1 rounded-xl border border-slate-800 bg-[#131318] p-1 w-fit">
        {(
          [
            ["overview", "Übersicht", Activity],
            ["backup", "Sicherung", FileJson],
          ] as const
        ).map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] transition-colors",
              tab === id
                ? "bg-white/[0.07] text-white font-semibold"
                : "text-slate-400 hover:text-white",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {tab === "backup" ? (
        <ConfigTransferPanel guildId={params.guildId} />
      ) : (
        <>
          {/* Fortschritt und Kennzahlen */}
          <div className={cn(CARD, "p-5 sm:p-6")}>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="text-[18px] font-bold text-white">
                  Einrichtung
                </h2>
                <p className="mt-1 text-[13px] text-slate-500">
                  {data.active_count} von {data.total_count} Modulen sind
                  eingerichtet
                </p>
              </div>
              <span className={cn("text-[32px] font-extrabold leading-none", farbe)}>
                {data.completion}%
              </span>
            </div>

            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-slate-800">
              <div
                className={cn("h-full rounded-full transition-all duration-500", balken)}
                style={{ width: `${data.completion}%` }}
              />
            </div>

            <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
              {kennzahlen.map((k) => (
                <div
                  key={k.label}
                  className="rounded-xl border border-slate-800 bg-[#0f0f13] px-4 py-3"
                >
                  <k.icon className="h-4 w-4 text-slate-600" />
                  <p className="mt-2 text-[20px] font-bold leading-none text-white">
                    {k.wert}
                  </p>
                  <p className="mt-1.5 text-[11px] text-slate-500">{k.label}</p>
                </div>
              ))}
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-slate-800 pt-4 text-[12px]">
              <span className="text-slate-500">
                Präfix{" "}
                <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-slate-300">
                  {data.prefix}
                </code>
              </span>
              {data.guild.boost_level > 0 && (
                <span className="text-slate-500">
                  Boost{" "}
                  <span className="text-pink-400">
                    Stufe {data.guild.boost_level} &middot; {data.guild.boost_count}
                  </span>
                </span>
              )}
              <span className="text-slate-500">
                Sicherheitsstufe{" "}
                <span className="text-slate-300 capitalize">
                  {data.guild.verification_level}
                </span>
              </span>
            </div>
          </div>

          {/* Nächste Schritte */}
          {naechste.length > 0 && (
            <div className={cn(CARD, "p-5 sm:p-6")}>
              <h2 className="text-[16px] font-bold text-white">
                Als Nächstes
              </h2>
              <p className="mt-1 text-[13px] text-slate-500">
                Die drei Module, die am meisten bringen und noch fehlen.
              </p>

              <div className="mt-4 grid gap-3 lg:grid-cols-3">
                {naechste.map((mod) => {
                  const Icon = MODULE_ICONS[mod.key] || Settings;
                  return (
                    <Link
                      key={mod.key}
                      href={`/dashboard/guild/${params.guildId}/${mod.path}`}
                      className="group rounded-xl border border-slate-800 bg-[#0f0f13] p-4 transition-colors hover:border-indigo-500/40"
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className="h-[18px] w-[18px] text-indigo-400" />
                        <span className="text-[15px] font-semibold text-white">
                          {mod.label}
                        </span>
                      </div>
                      <p className="mt-2 text-[13px] leading-relaxed text-slate-400">
                        {WOZU[mod.key] || "Im Dashboard einstellbar."}
                      </p>
                      <span className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-indigo-400">
                        Einrichten
                        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                      </span>
                    </Link>
                  );
                })}
              </div>
            </div>
          )}

          {/* Eingerichtet */}
          {sortiert.aktiv.length > 0 && (
            <div className={cn(CARD, "p-5 sm:p-6")}>
              <div className="mb-4 flex items-baseline gap-2.5">
                <h2 className="text-[16px] font-bold text-white">
                  Eingerichtet
                </h2>
                <span className="text-[13px] text-slate-600">
                  {sortiert.aktiv.length}
                </span>
              </div>
              <div className="space-y-2">
                {sortiert.aktiv.map((mod) => (
                  <Zeile key={mod.key} mod={mod} guildId={params.guildId} fertig />
                ))}
              </div>
            </div>
          )}

          {/* Noch offen */}
          {restOffen.length > 0 && (
            <div className={cn(CARD, "p-5 sm:p-6")}>
              <div className="mb-4 flex items-baseline gap-2.5">
                <h2 className="text-[16px] font-bold text-white">Noch offen</h2>
                <span className="text-[13px] text-slate-600">
                  {restOffen.length}
                </span>
              </div>

              <div className="space-y-2">
                {(alleOffenen ? restOffen : restOffen.slice(0, 5)).map((mod) => (
                  <Zeile
                    key={mod.key}
                    mod={mod}
                    guildId={params.guildId}
                    fertig={false}
                  />
                ))}
              </div>

              {restOffen.length > 5 && (
                <button
                  type="button"
                  onClick={() => setAlleOffenen((a) => !a)}
                  className="mt-3 text-[13px] text-slate-500 transition-colors hover:text-white"
                >
                  {alleOffenen
                    ? "Weniger anzeigen"
                    : `Alle ${restOffen.length} anzeigen`}
                </button>
              )}
            </div>
          )}

          {sortiert.offen.length === 0 && (
            <div
              className={cn(
                CARD,
                "flex items-center gap-3 border-emerald-500/25 p-5",
              )}
            >
              <Check className="h-5 w-5 shrink-0 text-emerald-400" />
              <p className="text-[14px] text-slate-300">
                Alles eingerichtet. Feinheiten stellst du in den einzelnen
                Reitern ein.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
