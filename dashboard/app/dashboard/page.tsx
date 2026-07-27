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
  const firstName = (session?.user?.name || "").split(" ")[0] || "there";

  let botInfo: any = null;
  let botStatus: any = null;
  let error: string | null = null;

  try {
    botInfo = await api.getBotInfo();
  } catch (err: any) {
    error = err?.message || "Could not reach the bot API.";
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
  const preview = myGuilds.slice(0, 6);

  const stats = [
    {
      name: "Your servers",
      value: connected.length.toLocaleString("en-US"),
      hint: `${myGuilds.length} manageable`,
      icon: ServerIcon,
    },
    {
      name: "Members reached",
      value: connected
        .reduce((sum, g) => sum + (g.memberCount ?? 0), 0)
        .toLocaleString("en-US"),
      hint: "across your servers",
      icon: Users,
    },
    {
      name: "Bot servers",
      value: (botInfo?.guilds ?? 0).toLocaleString("en-US"),
      hint: "total",
      icon: Bot,
    },
    {
      name: "Latency",
      value: botStatus ? `${Math.round(botStatus.latency)}ms` : botInfo?.latency || "—",
      hint: botStatus ? "gateway" : error ? "offline" : "unknown",
      icon: Activity,
    },
  ];

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* ── Greeting ─────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="flex items-center gap-4">
          {session?.user?.image && (
            <Image
              src={session.user.image}
              alt=""
              width={56}
              height={56}
              unoptimized
              className="rounded-2xl border-2 border-slate-800"
            />
          )}
          <div>
            <h1 className="text-3xl md:text-4xl font-bold text-white tracking-tight">
              Welcome back, <span className="text-blue-500">{firstName}</span>
            </h1>
            <p className="text-slate-400 mt-1.5 text-sm">
              {connected.length > 0
                ? `You manage ${connected.length} server${connected.length === 1 ? "" : "s"} with ${botInfo?.name || "the bot"}.`
                : "Add the bot to a server to get started."}
            </p>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-amber-300 text-xs font-bold">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            <span>Bot offline — values may be incomplete.</span>
          </div>
        )}
      </div>

      {/* ── Stats ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <div
            key={stat.name}
            className="group glass border-white/5 p-6 rounded-[28px] relative overflow-hidden hover:border-blue-500/30 transition-all duration-500"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] font-black text-slate-500 uppercase tracking-[0.18em]">
                  {stat.name}
                </p>
                <p className="text-3xl font-bold text-white tracking-tight mt-2 tabular-nums truncate">
                  {stat.value}
                </p>
                <p className="text-[11px] text-slate-600 mt-1">{stat.hint}</p>
              </div>
              <div className="p-3 bg-blue-500/10 rounded-2xl border border-blue-500/20 group-hover:bg-blue-500/20 transition-all shrink-0">
                <stat.icon className="h-5 w-5 text-blue-500" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Your servers ─────────────────────────────────────── */}
      <section className="glass border-white/5 rounded-[32px] p-8">
        <div className="flex items-center justify-between mb-6 gap-4">
          <h2 className="text-xl font-bold text-white tracking-tight">Your servers</h2>
          {myGuilds.length > preview.length && (
            <Link
              href="/dashboard/guilds"
              className="flex items-center gap-1.5 text-xs font-black uppercase tracking-widest text-blue-400 hover:text-blue-300 transition-colors shrink-0"
            >
              All {myGuilds.length}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>

        {preview.length === 0 ? (
          <div className="text-center py-10">
            <ServerIcon className="h-12 w-12 text-slate-700 mx-auto mb-4" />
            <p className="text-slate-400 font-medium">No servers yet</p>
            <p className="text-sm text-slate-600 mt-1 mb-6">
              You need Manage Server or Administrator on a Discord server.
            </p>
            <a
              href={BOT_INVITE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-blue-500 text-white text-xs font-black uppercase tracking-widest hover:brightness-110 transition-all"
            >
              <Plus className="h-4 w-4" />
              Invite the bot
            </a>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {preview.map((guild) => {
              const url = iconUrl(guild.id, guild.icon);
              const card = (
                <>
                  {url ? (
                    <Image
                      src={url}
                      alt=""
                      width={44}
                      height={44}
                      unoptimized
                      className="rounded-xl border border-slate-800 shrink-0"
                    />
                  ) : (
                    <div className="h-11 w-11 rounded-xl bg-blue-500/15 border border-slate-800 flex items-center justify-center text-blue-400 font-black shrink-0">
                      {guild.name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-white text-sm truncate">{guild.name}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {guild.hasBot
                        ? guild.memberCount !== null
                          ? `${guild.memberCount.toLocaleString("en-US")} members`
                          : "Connected"
                        : "Bot not added"}
                    </p>
                  </div>
                  {guild.hasBot ? (
                    <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-blue-400 group-hover:translate-x-0.5 transition-all shrink-0" />
                  ) : (
                    <Plus className="h-4 w-4 text-slate-600 group-hover:text-blue-400 shrink-0" />
                  )}
                </>
              );

              const className =
                "group flex items-center gap-3 p-4 rounded-2xl bg-white/[0.02] border border-white/5 hover:bg-white/[0.05] hover:border-blue-500/25 transition-all";

              return guild.hasBot ? (
                <Link key={guild.id} href={`/dashboard/guild/${guild.id}`} className={className}>
                  {card}
                </Link>
              ) : (
                <a
                  key={guild.id}
                  href={BOT_INVITE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={className}
                >
                  {card}
                </a>
              );
            })}
          </div>
        )}
      </section>

      {/* ── Shortcuts ────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          {
            title: "All servers",
            desc: "Search and configure",
            icon: ServerIcon,
            href: "/dashboard/guilds",
          },
          {
            title: "Add the bot",
            desc: "Invite it to a server",
            icon: Plus,
            href: BOT_INVITE_URL,
            external: true,
          },
          {
            title: "Support",
            desc: "Ask us on Discord",
            icon: LifeBuoy,
            href: "https://discord.gg/MG3rYnUZJV",
            external: true,
          },
        ].map((item) => {
          const inner = (
            <>
              <div className="h-11 w-11 rounded-2xl bg-blue-500/5 border border-blue-500/10 flex items-center justify-center group-hover:bg-blue-500/15 transition-colors shrink-0">
                <item.icon className="h-5 w-5 text-blue-500/70 group-hover:text-blue-400 transition-colors" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-bold text-white group-hover:text-blue-400 transition-colors">
                  {item.title}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">{item.desc}</p>
              </div>
            </>
          );
          const className =
            "group flex items-center gap-4 p-5 rounded-[24px] glass border-white/5 hover:border-blue-500/25 transition-all";

          return item.external ? (
            <a
              key={item.title}
              href={item.href}
              target="_blank"
              rel="noopener noreferrer"
              className={className}
            >
              {inner}
            </a>
          ) : (
            <Link key={item.title} href={item.href} className={className}>
              {inner}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
