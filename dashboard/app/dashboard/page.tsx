import React from "react";
import Link from "next/link";
import Image from "next/image";
import {
  Activity,
  ArrowRight,
  Bot,
  ChevronRight,
  LifeBuoy,
  Plus,
  Server as ServerIcon,
  Settings,
  ShieldAlert,
  Users,
} from "lucide-react";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { api } from "@/lib/api";
import { SUPPORT_INVITE } from "@/lib/legal";
import { MyServersChart } from "@/components/dashboard/my-servers-chart";

export const dynamic = "force-dynamic";

const BOT_INVITE_URL =
  process.env.NEXT_PUBLIC_BOT_INVITE_URL ||
  "https://discord.com/oauth2/authorize?client_id=1530349205372145715&permissions=8&scope=bot%20applications.commands";

const MANAGE_GUILD = BigInt(0x20);
const ADMINISTRATOR = BigInt(0x8);

function iconUrl(id: string, icon: string | null) {
  return icon ? `https://cdn.discordapp.com/icons/${id}/${icon}.png?size=64` : null;
}

export default async function DashboardPage() {
  const session = await getServerSession(authOptions);
  const firstName = (session?.user?.name || "").split(" ")[0] || "du";

  let botInfo: any = null;
  let botStatus: any = null;
  let error: string | null = null;

  try {
    botInfo = await api.getBotInfo();
  } catch (err: any) {
    error = err?.message || "Die Bot-API antwortet nicht.";
    botInfo = { name: "Bot", guilds: 0, users: 0, commands: 0, latency: "0ms" };
  }

  try {
    botStatus = await api.getBotStatus();
  } catch {
    botStatus = null;
  }

  // The servers this user can actually manage — the reason they are here.
  let myGuilds: Array<{
    id: string;
    name: string;
    icon: string | null;
    hasBot: boolean;
    memberCount: number | null;
  }> = [];

  if (session?.accessToken) {
    try {
      const [botGuilds, res] = await Promise.all([
        api.listGuilds().catch(() => []),
        fetch("https://discord.com/api/users/@me/guilds?with_counts=true", {
          headers: { Authorization: `Bearer ${session.accessToken}` },
          next: { revalidate: 300 },
        }),
      ]);

      if (res.ok) {
        const all = await res.json();
        const botMap = new Map(
          (botGuilds as any[]).map((g) => [String(g.id), g])
        );

        myGuilds = all
          .filter((g: any) => {
            try {
              const perms = BigInt(g.permissions);
              return (
                (perms & ADMINISTRATOR) === ADMINISTRATOR ||
                (perms & MANAGE_GUILD) === MANAGE_GUILD ||
                g.owner === true
              );
            } catch {
              return g.owner === true;
            }
          })
          .map((g: any) => {
            const info: any = botMap.get(String(g.id));
            return {
              id: String(g.id),
              name: g.name,
              icon: g.icon ?? null,
              hasBot: Boolean(info),
              memberCount:
                typeof info?.member_count === "number" && info.member_count > 0
                  ? info.member_count
                  : typeof g.approximate_member_count === "number"
                  ? g.approximate_member_count
                  : null,
            };
          })
          .sort(
            (a: any, b: any) =>
              Number(b.hasBot) - Number(a.hasBot) ||
              (b.memberCount ?? 0) - (a.memberCount ?? 0)
          );
      }
    } catch {
      /* the section below simply stays empty */
    }
  }

  const connected = myGuilds.filter((g) => g.hasBot);
  const ohneBot = myGuilds.filter((g) => !g.hasBot);
  const vorschau = myGuilds.slice(0, 6);
  const erreichte = connected.reduce((s, g) => s + (g.memberCount ?? 0), 0);

  const zahl = (n: number) => n.toLocaleString("de-DE");

  return (
    <div className="space-y-5">
      {/* ── Begrüßung ─────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-4">
        {session?.user?.image && (
          <Image
            src={session.user.image}
            alt=""
            width={48}
            height={48}
            unoptimized
            className="rounded-xl"
          />
        )}
        <div className="min-w-0 flex-1">
          <h1 className="text-[24px] sm:text-[28px] font-bold tracking-tight text-white">
            Hallo, {firstName}
          </h1>
          <p className="mt-0.5 text-[14px] text-slate-500">
            {connected.length > 0
              ? `Du verwaltest ${zahl(connected.length)} ${
                  connected.length === 1 ? "Server" : "Server"
                } mit dem Bot.`
              : "Füge den Bot zu einem Server hinzu, um loszulegen."}
          </p>
        </div>

        {error && (
          <span className="flex items-center gap-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-[13px] text-amber-300">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            Bot offline — Zahlen unvollständig
          </span>
        )}
      </div>

      {/* ── Zahlen ────────────────────────────────────────── */}
      {/*
        Vier Kacheln mit Symbolrahmen und 0.18em Sperrung waren das
        Lauteste auf der Seite -- dabei ist die Serverliste der Grund,
        warum jemand hier ist. Jetzt eine Zeile, die man überfliegt.
      */}
      <div className="flex flex-wrap gap-x-8 gap-y-3 rounded-2xl border border-slate-800 bg-[#131318] px-5 py-4">
        {[
          {
            wert: zahl(connected.length),
            label: "deiner Server",
            hint: myGuilds.length > connected.length
              ? `${zahl(myGuilds.length)} verwaltbar`
              : null,
            icon: ServerIcon,
          },
          {
            wert: erreichte > 0 ? zahl(erreichte) : "—",
            label: "Mitglieder erreicht",
            hint: null,
            icon: Users,
          },
          {
            wert: zahl(botInfo?.guilds ?? 0),
            label: "Server insgesamt",
            hint: null,
            icon: Bot,
          },
          {
            wert: botStatus
              ? `${Math.round(botStatus.latency)} ms`
              : botInfo?.latency || "—",
            label: "zu Discord",
            hint: null,
            icon: Activity,
          },
        ].map((k) => (
          <div key={k.label} className="flex items-center gap-2.5">
            <k.icon className="h-4 w-4 shrink-0 text-slate-600" />
            <div>
              <span className="text-[17px] font-semibold tabular-nums text-white">
                {k.wert}
              </span>{" "}
              <span className="text-[13px] text-slate-500">{k.label}</span>
              {k.hint && (
                <span className="ml-1.5 text-[12px] text-slate-600">
                  ({k.hint})
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ── Deine Server ──────────────────────────────────── */}
      <section className="rounded-2xl border border-slate-800 bg-[#131318] p-5 sm:p-6">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 className="text-[16px] font-bold text-white">Deine Server</h2>
          {myGuilds.length > vorschau.length && (
            <Link
              href="/dashboard/guilds"
              className="flex shrink-0 items-center gap-1.5 text-[13px] text-indigo-400 transition-colors hover:text-indigo-300"
            >
              Alle {zahl(myGuilds.length)}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>

        {vorschau.length === 0 ? (
          <div className="py-10 text-center">
            <ServerIcon className="mx-auto mb-3 h-8 w-8 text-slate-700" />
            <p className="text-[15px] text-slate-300">Noch keine Server</p>
            <p className="mx-auto mt-1.5 max-w-sm text-[13px] leading-relaxed text-slate-500">
              Du brauchst auf einem Discord-Server das Recht „Server
              verwalten“ oder „Administrator“, damit er hier auftaucht.
            </p>
            <a
              href={BOT_INVITE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#5865f2] px-5 py-2.5 text-[14px] font-semibold text-white transition-colors hover:bg-[#4752c4]"
            >
              <Plus className="h-4 w-4" />
              Bot hinzufügen
            </a>
          </div>
        ) : (
          <div className="space-y-2">
            {vorschau.map((guild) => {
              const url = iconUrl(guild.id, guild.icon);
              const inhalt = (
                <>
                  {url ? (
                    <Image
                      src={url}
                      alt=""
                      width={36}
                      height={36}
                      unoptimized
                      className="shrink-0 rounded-lg"
                    />
                  ) : (
                    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-indigo-500/15 text-[14px] font-bold text-indigo-300">
                      {guild.name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[14px] font-semibold text-white">
                      {guild.name}
                    </p>
                    <p className="mt-0.5 text-[12px] text-slate-500">
                      {guild.hasBot
                        ? guild.memberCount !== null
                          ? `${zahl(guild.memberCount)} Mitglieder`
                          : "Verbunden"
                        : "Bot noch nicht hinzugefügt"}
                    </p>
                  </div>
                  {guild.hasBot ? (
                    <ChevronRight className="h-4 w-4 shrink-0 text-slate-700 transition-colors group-hover:text-slate-400" />
                  ) : (
                    <span className="shrink-0 rounded-md border border-slate-800 px-2 py-0.5 text-[11px] text-slate-500">
                      Hinzufügen
                    </span>
                  )}
                </>
              );

              const klasse =
                "group flex items-center gap-3 rounded-xl border border-slate-800 bg-[#0f0f13] px-4 py-3 transition-colors hover:border-slate-700";

              return guild.hasBot ? (
                <Link
                  key={guild.id}
                  href={`/dashboard/guild/${guild.id}`}
                  className={klasse}
                >
                  {inhalt}
                </Link>
              ) : (
                <a
                  key={guild.id}
                  href={BOT_INVITE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={klasse}
                >
                  {inhalt}
                </a>
              );
            })}
          </div>
        )}

        {ohneBot.length > 0 && vorschau.length > 0 && (
          <p className="mt-4 border-t border-slate-800 pt-4 text-[13px] text-slate-500">
            Auf {zahl(ohneBot.length)}{" "}
            {ohneBot.length === 1 ? "Server" : "Servern"} fehlt der Bot noch —
            ein Klick auf den Eintrag lädt ihn ein.
          </p>
        )}
      </section>

      {/* ── Verlauf ───────────────────────────────────────── */}
      {/*
        Steht unter der Serverliste, nicht darüber: die Liste ist der
        Grund, warum jemand hier ist. Der Verlauf ist die Antwort auf
        die zweite Frage — "und wie läuft es?".

        Nur verbundene Server: für einen Server ohne Bot gibt es
        nichts zu messen, und ein leeres Diagramm mit "noch keine
        Daten" wäre die falsche Erklärung dafür.
      */}
      {connected.length > 0 && (
        <MyServersChart
          guilds={connected.map((g) => ({
            id: g.id,
            name: g.name,
            memberCount: g.memberCount,
          }))}
        />
      )}

      {/* ── Schnellzugriff ────────────────────────────────── */}
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          {
            titel: "Alle Server",
            text: "Suchen und einrichten",
            icon: ServerIcon,
            href: "/dashboard/guilds",
          },
          {
            titel: "Bot hinzufügen",
            text: "Auf einen weiteren Server",
            icon: Plus,
            href: BOT_INVITE_URL,
            extern: true,
          },
          {
            titel: "Support",
            text: "Frag uns auf Discord",
            icon: LifeBuoy,
            href: SUPPORT_INVITE,
            extern: true,
          },
        ].map((item) => {
          const inhalt = (
            <>
              <item.icon className="h-[18px] w-[18px] shrink-0 text-slate-600 transition-colors group-hover:text-indigo-400" />
              <div className="min-w-0">
                <p className="text-[14px] font-semibold text-white">
                  {item.titel}
                </p>
                <p className="mt-0.5 text-[12px] text-slate-500">{item.text}</p>
              </div>
            </>
          );
          const klasse =
            "group flex items-center gap-3 rounded-xl border border-slate-800 bg-[#131318] px-4 py-3.5 transition-colors hover:border-slate-700";

          return item.extern ? (
            <a
              key={item.titel}
              href={item.href}
              target="_blank"
              rel="noopener noreferrer"
              className={klasse}
            >
              {inhalt}
            </a>
          ) : (
            <Link key={item.titel} href={item.href} className={klasse}>
              {inhalt}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
