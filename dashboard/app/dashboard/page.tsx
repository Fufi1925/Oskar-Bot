import { websiteLocale } from "@/lib/i18n/server-language";
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
  ShieldAlert,
  Users,
} from "lucide-react";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { api } from "@/lib/api";
import { SUPPORT_INVITE } from "@/lib/legal";
import { fetchDelegatedGuilds } from "@/lib/guild-auth";
import { compareGuildMembers } from "@/lib/guild-sorting";
import { MyServersChart } from "@/components/dashboard/my-servers-chart";

export const dynamic = "force-dynamic";

const BOT_INVITE_URL =
  process.env.NEXT_PUBLIC_BOT_INVITE_URL ||
  "https://discord.com/oauth2/authorize?client_id=1530349205372145715&permissions=8&scope=bot%20applications.commands";

const MANAGE_GUILD = BigInt(0x20);
const ADMINISTRATOR = BigInt(0x8);

function iconUrl(id: string, icon: string | null) {
  return icon ? /^https?:\/\//i.test(icon) ? icon : `https://cdn.discordapp.com/icons/${id}/${icon}.png?size=64` : null;
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
    botInfo = { name: "CloudTIX", guilds: 0, users: 0, commands: 0, latency: "0ms" };
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
          });
      }
    } catch {
      /* the section below simply stays empty */
    }
  }

  if (session?.user?.id) {
    try {
      const delegated = await fetchDelegatedGuilds(session.user.id);
      const known = new Set(myGuilds.map(guild => guild.id));
      for (const guild of delegated) {
        if (known.has(guild.id)) continue;
        myGuilds.push({ id: guild.id, name: guild.name, icon: guild.icon, hasBot: true, memberCount: guild.member_count });
        known.add(guild.id);
      }
    } catch { /* Existing Discord-managed servers remain available. */ }
  }

  myGuilds.sort(compareGuildMembers);

  const connected = myGuilds.filter((g) => g.hasBot);
  const ohneBot = myGuilds.filter((g) => !g.hasBot);
  const vorschau = myGuilds.slice(0, 6);
  const erreichte = connected.reduce((s, g) => s + (g.memberCount ?? 0), 0);

  const zahl = (n: number) => n.toLocaleString(websiteLocale());

  const metrics = [
    { label: "Verbundene Server", value: zahl(connected.length), note: `${zahl(myGuilds.length)} Server für dich verfügbar`, icon: ServerIcon },
    { label: "Deine Community", value: erreichte > 0 ? zahl(erreichte) : "—", note: "Mitglieder deiner verbundenen Server", icon: Users },
    { label: "CloudTIX Netzwerk", value: error ? "—" : zahl(botInfo?.guilds ?? 0), note: "Server mit CloudTIX insgesamt", icon: Bot },
    { label: "Discord-Verbindung", value: typeof botStatus?.latency === "number" && Number.isFinite(botStatus.latency) ? `${Math.round(botStatus.latency)} ms` : error ? "—" : botInfo?.latency || "—", note: "Aktuelle Antwortzeit des Bots", icon: Activity },
  ];
  const shortcuts = [
    { title: "Deine Server", text: "Wähle deine Community und richte ihre Module ein.", icon: ServerIcon, href: "/dashboard/guilds", external: false },
    { title: "CloudTIX hinzufügen", text: "Starte auf einem weiteren Discord-Server.", icon: Plus, href: BOT_INVITE_URL, external: true },
    { title: "Wir helfen dir weiter", text: "Sprich mit unserem Support auf Discord.", icon: LifeBuoy, href: SUPPORT_INVITE, external: true },
  ];

  return <div className="cloudtix-workspace-home">
    <header className="cloudtix-workspace-page-heading"><div><p className="cloudtix-workspace-eyebrow">DEIN CLOUDTIX WORKSPACE</p><h1>Hallo, <span data-no-translate>{firstName}</span>.</h1><p>Deine Server, deine Community und deine nächsten Schritte – alles an einem Ort.</p></div><Link href="/dashboard/guilds" className="cloudtix-workspace-action">Server verwalten<ArrowRight size={15} /></Link></header>
    {error && <div role="status" className="cloudtix-workspace-note flex items-center gap-3"><ShieldAlert size={17} className="shrink-0 text-amber-300" />CloudTIX ist gerade nicht erreichbar. Einige Zahlen sind nicht verfügbar.</div>}
    <section className="cloudtix-workspace-stat-grid" aria-label="Dein Überblick">{metrics.map(metric => <div key={metric.label} className="cloudtix-workspace-stat"><metric.icon size={19} /><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.note}</small></div>)}</section>
    <div className="cloudtix-workspace-home-grid">
      <section className="cloudtix-workspace-home-servers"><div className="cloudtix-workspace-section-heading"><div><h2>Deine Server</h2><p>Deine größten Communities zuerst.</p></div><Link href="/dashboard/guilds">Alle ansehen<ArrowRight size={13} /></Link></div>
        {vorschau.length ? <div>{vorschau.map(guild => {
          const src = iconUrl(guild.id, guild.icon);
          const content = <>{src ? <Image src={src} alt="" width={40} height={40} unoptimized /> : <b>{guild.name.charAt(0).toUpperCase()}</b>}<div><strong>{guild.name}</strong><small>{guild.hasBot ? guild.memberCount !== null ? `${zahl(guild.memberCount)} Mitglieder · Verbunden` : "Mit CloudTIX verbunden" : "CloudTIX noch nicht hinzugefügt"}</small></div>{guild.hasBot ? <ChevronRight size={16} /> : <Plus size={16} />}</>;
          return guild.hasBot ? <Link key={guild.id} href={`/dashboard/guild/${guild.id}`} className="cloudtix-workspace-server-row">{content}</Link> : <a key={guild.id} href={`${BOT_INVITE_URL}${BOT_INVITE_URL.includes("?") ? "&" : "?"}guild_id=${guild.id}&disable_guild_select=true`} target="_blank" rel="noopener noreferrer" className="cloudtix-workspace-server-row">{content}</a>;
        })}</div> : <div className="cloudtix-workspace-empty"><ServerIcon size={28} /><h2>Dein erster Server wartet.</h2><p>Du brauchst „Server verwalten“, Administratorrechte oder eine Dashboard-Freigabe, damit ein Server hier erscheint.</p><a href={BOT_INVITE_URL} target="_blank" rel="noopener noreferrer" className="cloudtix-workspace-action"><Plus size={15} />CloudTIX hinzufügen</a></div>}
        {ohneBot.length > 0 && <p className="mt-5 text-xs leading-relaxed text-slate-500">Auf {zahl(ohneBot.length)} {ohneBot.length === 1 ? "Server fehlt" : "Servern fehlt"} CloudTIX noch. Öffne einen Eintrag, um den Bot hinzuzufügen.</p>}
      </section>
      <aside className="cloudtix-workspace-shortcuts">{shortcuts.map(item => {
        const content = <><item.icon size={20} /><div><strong>{item.title}</strong><p>{item.text}</p></div><ArrowRight size={14} /></>;
        return item.external ? <a key={item.title} href={item.href} target="_blank" rel="noopener noreferrer" className="cloudtix-workspace-shortcut">{content}</a> : <Link key={item.title} href={item.href} className="cloudtix-workspace-shortcut">{content}</Link>;
      })}</aside>
    </div>
    {connected.length > 0 && <MyServersChart guilds={connected.map(guild => ({ id: guild.id, name: guild.name, memberCount: guild.memberCount }))} />}
  </div>;
}
