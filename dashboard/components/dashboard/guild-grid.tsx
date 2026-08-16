"use client";

/**
 * Die Server-Auswahl im Dashboard.
 *
 * ── Was an der alten Fassung nicht stimmte ──────────────────────────
 *
 * Fünf Dinge, alle nachgemessen und nicht vermutet:
 *
 *   1. **Die Mitgliederzahl wurde weggeworfen.** `page.tsx` fragt
 *      Discord mit `with_counts=true` und setzt `memberCount` für
 *      JEDEN Server -- auch für die ohne Bot. Die Karte zeigte sie
 *      trotzdem nicht, sondern behauptete: „Mitgliederzahl sichtbar,
 *      sobald der Bot auf dem Server ist.“ Nachgestellt in
 *      `repro/bug_guilds.mjs`: Server ohne Bot, `memberCount = 847`,
 *      angezeigt wurde der Satz. Die Angabe war da und wurde
 *      verschwiegen.
 *
 *   2. **Sortieren nach Mitgliedern, ohne sie zu zeigen.** Der Knopf
 *      „Mitglieder“ ordnete auch die Karten ohne Bot -- nach einer
 *      Zahl, die dort nirgends stand. Für den Betrachter war die
 *      Reihenfolge schlicht willkürlich.
 *
 *   3. **„Mitglieder gesamt“ zählte nur die verbundenen.** Die Zahl
 *      stand über einer Liste, in der auch andere Server stehen, und
 *      hieß „gesamt“.
 *
 *   4. **Versalien überall.** `MITGLIEDER`, `VERBUNDEN`, `OWNER` --
 *      fünf Stellen. Im Admin-Bereich ist genau das schon einmal
 *      aufgeräumt worden (`test_admin_stil.py`): Versalien gehören
 *      über Eingabefelder, nicht auf jede zweite Beschriftung.
 *
 *   5. **„Owner“ auf einer deutschen Seite.** Das Wörterbuch des
 *      Dashboards kennt „Besitzer“ und benutzt es an sechs anderen
 *      Stellen.
 *
 * ── Die eine Regel, die den Aufbau erklärt ──────────────────────────
 *
 * **Eine genaue Zahl und eine geschätzte sind nicht dasselbe.** Der
 * Bot kennt die echte Mitgliederzahl seiner Server; für alle anderen
 * liefert Discord nur `approximate_member_count` -- das steht so im
 * Feldnamen. Beide gleich zu drucken wäre eine Behauptung, die eine
 * davon nicht deckt. Deshalb trägt die geschätzte ein „ca.“ und die
 * Summe sagt, woraus sie besteht.
 */

import React, { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Bot, ChevronRight, Crown, ExternalLink, Plus, Search, Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface GuildEntry {
  id: string;
  name: string;
  icon: string | null;
  owner: boolean;
  hasBot: boolean;
  /**
   * Mitgliederzahl. Beim Bot-Server die echte, sonst Discords
   * Schätzung -- welche von beiden, sagt `hasBot`.
   */
  memberCount: number | null;
}

function iconUrl(id: string, icon: string | null) {
  return icon ? `https://cdn.discordapp.com/icons/${id}/${icon}.png?size=128` : null;
}

/** Deutsche Zahlen: 12.480, nicht 12,480. */
function zahl(wert: number) {
  return wert.toLocaleString("de-DE");
}

function Avatar({
  guild, size = 56, muted = false,
}: { guild: GuildEntry; size?: number; muted?: boolean }) {
  const url = iconUrl(guild.id, guild.icon);
  if (url) {
    return (
      <Image
        src={url}
        alt=""
        width={size}
        height={size}
        unoptimized
        className={cn(
          "rounded-2xl border border-slate-800 object-cover",
          muted && "opacity-60",
        )}
      />
    );
  }
  return (
    <div
      style={{ width: size, height: size }}
      className={cn(
        "flex items-center justify-center rounded-2xl border text-xl font-bold",
        muted
          ? "border-slate-800 bg-[#0e0e12] text-slate-500"
          : "border-indigo-500/25 bg-indigo-500/10 text-indigo-300",
      )}
    >
      {guild.name?.charAt(0)?.toUpperCase()}
    </div>
  );
}

/**
 * Die Mitgliederzahl einer Karte.
 *
 * `genau` unterscheidet die echte Zahl des Bots von Discords Schätzung.
 * Ohne diesen Unterschied stünde eine geschätzte Zahl so selbstsicher
 * da wie eine gezählte.
 */
function Mitglieder({
  anzahl, genau,
}: { anzahl: number | null; genau: boolean }) {
  if (anzahl === null) {
    return (
      <span className="text-[13px] text-slate-600">
        Mitgliederzahl nicht verfügbar
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-[#0e0e12] px-2.5 py-1.5"
      title={
        genau
          ? "Vom Bot gezählt"
          : "Schätzung von Discord — genau wird sie, sobald der Bot auf dem Server ist"
      }
    >
      <Users className="h-3.5 w-3.5 text-slate-500" />
      <span className="text-[13px] font-semibold tabular-nums text-slate-200">
        {genau ? "" : "ca. "}
        {zahl(anzahl)}
      </span>
      <span className="text-[12px] text-slate-500">Mitglieder</span>
    </span>
  );
}

/** Das Abzeichen für den Serverinhaber. */
function BesitzerAbzeichen({ gedaempft = false }: { gedaempft?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] font-semibold",
        gedaempft
          ? "border-slate-800 bg-[#0e0e12] text-slate-400"
          : "border-amber-500/25 bg-amber-500/10 text-amber-400",
      )}
    >
      <Crown className="h-3 w-3" />
      Besitzer
    </span>
  );
}

// `` bleibt: der Rand-Schimmer wurde bewusst nur im
// ADMIN-Bereich entfernt, weil der Nutzer ihn dort ausdruecklich
// nirgends wollte. Diese Seite gehoert nicht dazu -- ihn hier
// mitzunehmen waere eine Entscheidung gewesen, die niemand getroffen
// hat. `test_admin_stil.py` zaehlt die Traeger und hat den Verlust
// gemeldet: 111 Karten in 45 Dateien vorher, 108 in 44 danach.
//
// `` gehoert dazu: es sagt dem Schimmer, wie rund die Ecke
// ist. Ohne das sitzt der Lichtbogen an einer eckigen Bahn.
const KARTE =
  "rounded-2xl border border-slate-800 bg-[#131318]";

export function GuildGrid({
  connected,
  missing,
  inviteUrl,
}: {
  connected: GuildEntry[];
  missing: GuildEntry[];
  inviteUrl: string;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"members" | "name">("members");

  const filter = (list: GuildEntry[]) => {
    const q = query.trim().toLowerCase();
    const out = q
      ? list.filter(
          (g) => g.name.toLowerCase().includes(q) || g.id.includes(q),
        )
      : [...list];

    out.sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name, "de")
        : (b.memberCount ?? -1) - (a.memberCount ?? -1),
    );
    return out;
  };

  const shownConnected = useMemo(() => filter(connected), [connected, query, sort]);
  const shownMissing = useMemo(() => filter(missing), [missing, query, sort]);

  // Getrennt gezählt: die eine Summe ist gezählt, die andere geschätzt.
  // Sie zu addieren und „gesamt“ darüber zu schreiben wäre eine Zahl,
  // für die es keine Quelle gibt.
  const mitgliederVerbunden = connected.reduce(
    (summe, g) => summe + (g.memberCount ?? 0), 0,
  );
  const mitgliederOhneBot = missing.reduce(
    (summe, g) => summe + (g.memberCount ?? 0), 0,
  );
  const besitzer = [...connected, ...missing].filter((g) => g.owner).length;

  const nichtsGefunden =
    query.trim() !== "" && shownConnected.length === 0 && shownMissing.length === 0;

  const kennzahlen = [
    {
      label: "Verbunden",
      wert: zahl(connected.length),
      hinweis: connected.length === 1 ? "Server mit Bot" : "Server mit Bot",
      icon: Bot,
      farbe: "text-emerald-400",
    },
    {
      label: "Mitglieder erreicht",
      wert: zahl(mitgliederVerbunden),
      // Sagt, worauf sich die Zahl bezieht. Vorher hieß sie
      // „Mitglieder gesamt“ und zählte trotzdem nur die verbundenen.
      hinweis: "auf Servern mit Bot",
      icon: Users,
      farbe: "text-indigo-400",
    },
    {
      label: "Ohne Bot",
      wert: zahl(missing.length),
      hinweis:
        mitgliederOhneBot > 0
          ? `ca. ${zahl(mitgliederOhneBot)} weitere Mitglieder`
          : "Server ohne Bot",
      icon: Plus,
      farbe: "text-slate-400",
    },
    {
      label: "Deine Server",
      wert: zahl(besitzer),
      hinweis: besitzer === 1 ? "als Besitzer" : "als Besitzer",
      icon: Crown,
      farbe: "text-amber-400",
    },
  ];

  return (
    <div className="space-y-6">
      {/* ── Kennzahlen ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {kennzahlen.map((k) => (
          <div
            key={k.label}
            className={cn(KARTE, "flex items-start justify-between gap-3 p-4")}
          >
            <div className="min-w-0">
              <p className="text-[22px] font-bold leading-none tabular-nums text-white">
                {k.wert}
              </p>
              <p className="mt-1.5 text-[13px] font-semibold text-slate-300">
                {k.label}
              </p>
              <p className="mt-0.5 truncate text-[12px] text-slate-500">
                {k.hinweis}
              </p>
            </div>
            <k.icon className={cn("h-4 w-4 shrink-0", k.farbe)} />
          </div>
        ))}
      </div>

      {/* ── Suche und Reihenfolge ───────────────────────────────── */}
      {connected.length + missing.length > 3 && (
        <div className={cn(KARTE, "flex flex-wrap items-center gap-3 p-3")}>
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Nach Name oder Server-ID suchen"
              aria-label="Server suchen"
              className="w-full rounded-xl border border-slate-800 bg-[#0e0e12] py-2.5 pl-10 pr-4 text-sm text-white placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-slate-500">Sortieren:</span>
            <div className="flex gap-1 rounded-lg border border-slate-800 bg-[#0f0f13] p-1">
              {(
                [
                  ["members", "Mitglieder"],
                  ["name", "Name"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setSort(id)}
                  aria-pressed={sort === id}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-[13px] transition-colors",
                    sort === id
                      ? "bg-white/[0.07] font-semibold text-white"
                      : "text-slate-500 hover:text-slate-300",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {nichtsGefunden && (
        <div className={cn(KARTE, "px-6 py-10 text-center")}>
          <Search className="mx-auto mb-3 h-7 w-7 text-slate-700" />
          <p className="text-[15px] text-slate-300">
            Kein Server passt zu „{query}“.
          </p>
          <p className="mt-1.5 text-[13px] text-slate-500">
            Gesucht wird im Namen und in der Server-ID.
          </p>
        </div>
      )}

      {/* ── Mit Bot ─────────────────────────────────────────────── */}
      {shownConnected.length > 0 && (
        <section>
          <h2 className="mb-3 flex items-center gap-2 text-[15px] font-bold text-white">
            <Bot className="h-4 w-4 text-emerald-400" />
            Server mit Bot
            <span className="text-[13px] font-normal text-slate-500">
              {shownConnected.length}
            </span>
          </h2>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {shownConnected.map((guild) => (
              <Link
                key={guild.id}
                href={`/dashboard/guild/${guild.id}`}
                // Die ganze Karte ist der Knopf. Vorher war es ein
                // eigener Knopf am Fuß, und ein Klick auf den Namen
                // tat nichts -- obwohl die Karte insgesamt aussah,
                // als könnte man sie anklicken.
                className={cn(
                  KARTE,
                  "group flex flex-col p-5 transition-colors hover:border-slate-700",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="relative">
                    <Avatar guild={guild} />
                    <span
                      className="absolute -bottom-1 -right-1 h-3.5 w-3.5 rounded-full border-2 border-[#131318] bg-emerald-500"
                      title="Der Bot ist auf diesem Server"
                    />
                  </div>
                  {guild.owner && <BesitzerAbzeichen />}
                </div>

                <h3 className="mt-4 truncate text-[16px] font-bold text-white">
                  {guild.name}
                </h3>

                <div className="mt-3">
                  <Mitglieder anzahl={guild.memberCount} genau />
                </div>

                <span className="mt-4 flex items-center gap-1.5 border-t border-slate-800 pt-3.5 text-[13px] font-semibold text-slate-400 transition-colors group-hover:text-indigo-400">
                  Server verwalten
                  <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* ── Ohne Bot ────────────────────────────────────────────── */}
      {shownMissing.length > 0 && (
        <section>
          <h2 className="mb-3 flex items-center gap-2 text-[15px] font-bold text-white">
            <Plus className="h-4 w-4 text-slate-500" />
            Server ohne Bot
            <span className="text-[13px] font-normal text-slate-500">
              {shownMissing.length}
            </span>
          </h2>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {shownMissing.map((guild) => (
              <div
                key={guild.id}
                className={cn(KARTE, "flex flex-col p-5")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="relative">
                    <Avatar guild={guild} muted />
                    <span
                      className="absolute -bottom-1 -right-1 h-3.5 w-3.5 rounded-full border-2 border-[#131318] bg-slate-600"
                      title="Der Bot ist nicht auf diesem Server"
                    />
                  </div>
                  {guild.owner && <BesitzerAbzeichen gedaempft />}
                </div>

                <h3 className="mt-4 truncate text-[16px] font-bold text-slate-300">
                  {guild.name}
                </h3>

                {/* Die Zahl steht auch hier. Sie kam ohnehin mit
                    (with_counts=true) und wurde vorher verschwiegen --
                    mit dem Satz, sie sei erst mit Bot sichtbar. */}
                <div className="mt-3">
                  <Mitglieder anzahl={guild.memberCount} genau={false} />
                </div>

                <a
                  href={inviteUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 flex items-center justify-center gap-2 rounded-xl bg-[#5865f2] px-4 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-[#4752c4]"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Bot hinzufügen
                  <ExternalLink className="h-3 w-3 opacity-60" />
                </a>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
