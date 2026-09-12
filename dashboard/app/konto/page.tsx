import Image from "next/image";
import Link from "next/link";
import { getServerSession } from "next-auth/next";
import { Activity, CalendarDays, CheckCircle2, Clock3, Crown, Gem, Hash, MessageSquare, Server, ShieldCheck, Sparkles, Trophy, Users } from "lucide-react";

import { authOptions } from "@/lib/auth";
import { api } from "@/lib/api";
import { SiteNav } from "@/components/site-nav";
import { AccountLoginGate } from "@/components/account-login-gate";
import { AccountActions } from "@/components/account-actions";
import { AccountDangerZone } from "@/components/account-danger-zone";
import { AccountActivityPanel } from "@/components/account-activity-panel";
import { AccountApplicationsPanel } from "@/components/account-applications-panel";
import { AccountPreferencesPanel } from "@/components/account-preferences-panel";
import { AccountPrivacyPanel } from "@/components/account-privacy-panel";
import { AccountSecurityPanel } from "@/components/account-security-panel";
import { AccountSupportPanel } from "@/components/account-support-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const MANAGE_GUILD = BigInt(0x20);
const ADMINISTRATOR = BigInt(0x8);

function discordCreatedAt(id: string): Date | null {
  try {
    const discordEpoch = BigInt("1420070400000");
    return new Date(Number(BigInt(id) / BigInt(4194304) + discordEpoch));
  } catch {
    return null;
  }
}

function formatDate(value: Date | null) {
  return value ? new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "long", year: "numeric" }).format(value) : "Nicht verfügbar";
}

function number(value: number | null | undefined) {
  return typeof value === "number" ? value.toLocaleString("de-DE") : "—";
}

function formatTimestamp(value?: number | null) {
  return value ? new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value * 1000)) : "Nicht verfügbar";
}

function remainingDays(value?: number | null) {
  return value ? Math.max(0, Math.ceil((value * 1000 - Date.now()) / 86_400_000)) : 0;
}

export default async function AccountPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return <><SiteNav /><AccountLoginGate /></>;
  }

  const userId = session.user.id;
  let discordUser: any = null;
  let manageableGuilds: any[] = [];
  let connectedGuilds = 0;
  let stats: Awaited<ReturnType<typeof api.getMyAccountStats>> | null = null;
  let premium: any = null;

  const discordHeaders = session.accessToken ? { Authorization: `Bearer ${session.accessToken}` } : undefined;

  await Promise.all([
    (async () => {
      if (!discordHeaders) return;
      try {
        const response = await fetch("https://discord.com/api/users/@me", { headers: discordHeaders, cache: "no-store" });
        if (response.ok) discordUser = await response.json();
      } catch { /* profile falls back to the verified session */ }
    })(),
    (async () => {
      if (!discordHeaders) return;
      try {
        const [discordResponse, botGuilds] = await Promise.all([
          fetch("https://discord.com/api/users/@me/guilds?with_counts=true", { headers: discordHeaders, cache: "no-store" }),
          api.listGuilds().catch(() => []),
        ]);
        if (!discordResponse.ok) return;
        const guilds = await discordResponse.json();
        manageableGuilds = guilds.filter((guild: any) => {
          try {
            const permissions = BigInt(guild.permissions);
            return guild.owner === true || (permissions & ADMINISTRATOR) === ADMINISTRATOR || (permissions & MANAGE_GUILD) === MANAGE_GUILD;
          } catch { return guild.owner === true; }
        });
        const installed = new Set((botGuilds as any[]).map(guild => String(guild.id)));
        connectedGuilds = manageableGuilds.filter(guild => installed.has(String(guild.id))).length;
      } catch { /* real values remain unavailable rather than being invented */ }
    })(),
    api.getMyAccountStats(userId).then(value => { stats = value; }).catch(() => {}),
    api.getMyPremium(userId).then(value => { premium = value?.premium ?? null; }).catch(() => {}),
  ]);

  const realStats = stats as {
    guilds: number;
    total_xp: number;
    messages: number;
    highest_level: number;
    last_active: number;
    activity?: any;
  } | null;
  const displayName = discordUser?.global_name || session.user.name || discordUser?.username || "Discord-Nutzer";
  const username = discordUser?.username || session.user.name || displayName;
  const createdAt = discordCreatedAt(userId);
  const premiumLabel = premium?.premium
    ? premium.via_tester ? "Tester-Zugang" : premium.via_trial ? "Kostenlose Probewoche" : premium.lifetime ? "Premium dauerhaft" : "Premium aktiv"
    : "Free";
  const lastActive = realStats?.last_active ? new Date(realStats.last_active * 1000) : null;
  const premiumSlots = Array.isArray(premium?.slots) ? premium.slots : [];
  const premiumRequests = Array.isArray(premium?.purchase_requests) ? premium.purchase_requests : [];
  const premiumDaysLeft = remainingDays(premium?.expires_at);
  const guildById = new Map(manageableGuilds.map(guild => [String(guild.id), guild]));

  const cards = [
    { label: "Verwaltbare Server", value: number(manageableGuilds.length), hint: `${number(connectedGuilds)} davon mit dem Bot`, icon: Server, color: "text-cyan-400" },
    { label: "Gesammelte XP", value: number(realStats?.total_xp), hint: `auf ${number(realStats?.guilds)} aktiven Servern`, icon: Sparkles, color: "text-indigo-400" },
    { label: "Leveling-Nachrichten", value: number(realStats?.messages), hint: "vom Level-System erfasst", icon: MessageSquare, color: "text-emerald-400" },
    { label: "Höchstes Level", value: number(realStats?.highest_level), hint: "dein bester Serverwert", icon: Trophy, color: "text-amber-400" },
  ];

  return (
    <div className="min-h-screen bg-[#090a0d]">
      <SiteNav />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8 lg:py-12">
        <Link href="/" className="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-[#131318] px-4 py-2 text-sm text-slate-400 transition-colors hover:border-slate-700 hover:text-white">← Zur Startseite</Link>

        <section className="relative overflow-hidden rounded-[28px] border border-slate-800 bg-[#131318] p-6 sm:p-9">
          <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(circle_at_90%_20%,rgba(56,189,248,0.13),transparent_35%),radial-gradient(circle_at_15%_0%,rgba(99,102,241,0.18),transparent_42%)]" />
          <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center">
            <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-3xl border border-white/10 bg-indigo-500/10">
              {session.user.image ? <Image src={session.user.image} alt={`Profilbild von ${displayName}`} fill sizes="96px" unoptimized className="object-cover" /> : <div className="grid h-full place-items-center text-3xl font-black text-indigo-300">{displayName.slice(0, 2).toUpperCase()}</div>}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-indigo-300">University Bot Konto</p>
              <h1 className="mt-2 truncate text-3xl font-black tracking-tight text-white sm:text-4xl">{displayName}</h1>
              <p className="mt-2 text-sm text-slate-400">@{username} · Deine echten Discord- und Bot-Daten auf einen Blick.</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-black/20 px-3 py-1.5 text-xs text-slate-400"><Hash className="h-3.5 w-3.5" /> Discord-ID: {userId}</span>
                <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs ${premium?.premium ? "border-amber-400/25 bg-amber-400/10 text-amber-300" : "border-slate-700 bg-black/20 text-slate-400"}`}><Gem className="h-3.5 w-3.5" /> {premiumLabel}</span>
              </div>
            </div>
          </div>
        </section>

        <section className="overflow-hidden rounded-[28px] border border-amber-400/20 bg-[#131318]">
          <div className="flex flex-col gap-4 border-b border-slate-800 bg-amber-400/[0.04] px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
            <div className="flex items-center gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-2xl bg-amber-400/10"><Crown className="h-5 w-5 text-amber-300" /></span>
              <div><h2 className="text-lg font-black text-white">Dein Premium</h2><p className="text-sm text-slate-500">Kauf, Laufzeit und deine drei festen Premiumserver.</p></div>
            </div>
            <Link href="/dashboard/premium" className="rounded-xl bg-amber-400 px-4 py-2.5 text-center text-sm font-black text-black hover:brightness-110">Premium verwalten</Link>
          </div>
          <div className="p-5 sm:p-7">
            {premium?.premium ? <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <PremiumFact label="Status" value="Premium aktiv" detail={`${premiumDaysLeft} Tage verbleibend`} icon={CheckCircle2} />
                <PremiumFact label="Gekauft / vergeben" value={formatTimestamp(premium.granted_at)} detail={premium.source === "purchase_request" ? "Bestätigte Kaufanfrage" : "Durch einen Admin vergeben"} icon={CalendarDays} />
                <PremiumFact label="Läuft ab" value={formatTimestamp(premium.expires_at)} detail={`${premium.duration_days || "–"}-Tage-Paket`} icon={Clock3} />
                <PremiumFact label="Serverplätze" value={`${premiumSlots.length} von 3 belegt`} detail={`${3 - premiumSlots.length} Plätze verfügbar`} icon={Server} />
              </div>
              <div className="mt-5">
                <div className="mb-2 flex justify-between text-xs"><span className="font-bold text-slate-400">Verbleibende Laufzeit</span><span className="text-amber-300">{premiumDaysLeft} Tage</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-amber-500 to-yellow-300" style={{ width: `${Math.max(2, Math.min(100, (premiumDaysLeft / Math.max(1, premium.duration_days || 1)) * 100))}%` }} /></div>
              </div>
            </> : <div className="flex flex-col gap-4 rounded-2xl border border-dashed border-slate-700 p-5 sm:flex-row sm:items-center"><Gem className="h-8 w-8 text-slate-600"/><div className="flex-1"><h3 className="font-black text-white">Noch kein aktives Premium</h3><p className="mt-1 text-sm text-slate-500">Sende eine Kaufanfrage für 30, 90 oder 365 Tage und erhalte drei feste Serverplätze.</p></div><Link href="/dashboard/premium" className="rounded-xl border border-amber-400/30 px-4 py-2.5 text-center text-sm font-bold text-amber-300">Pakete ansehen</Link></div>}

            <div className="mt-6 grid gap-3 md:grid-cols-3">
              {[1, 2, 3].map(slotNo => {
                const slot = premiumSlots.find((entry: any) => Number(entry.slot_no) === slotNo);
                const guild = slot ? guildById.get(String(slot.guild_id)) : null;
                const icon = slot?.guild_icon || (guild?.icon ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=128` : null);
                return <article key={slotNo} className={`rounded-2xl border p-4 ${slot ? "border-violet-500/25 bg-violet-500/[0.05]" : "border-dashed border-slate-700"}`}>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Premium-Platz {slotNo}</p>
                  {slot ? <div className="mt-3 flex items-center gap-3">{icon ? <Image src={icon} alt="" width={42} height={42} unoptimized className="h-11 w-11 rounded-xl" /> : <span className="grid h-11 w-11 place-items-center rounded-xl bg-violet-500/10"><Server className="h-5 w-5 text-violet-300" /></span>}<div className="min-w-0"><p className="truncate font-black text-white">{slot.guild_name || guild?.name || `Server ${slot.guild_id}`}</p><p className="mt-0.5 text-xs text-emerald-300">Fest zugewiesen · Premium</p></div></div> : <div className="mt-3"><p className="font-bold text-slate-400">Platz ist frei</p><p className="mt-1 text-xs text-slate-600">Im Dashboard fest einem Server zuweisen.</p></div>}
                </article>;
              })}
            </div>

            {premiumRequests.length > 0 && <div className="mt-6 border-t border-slate-800 pt-5">
              <h3 className="font-black text-white">Kauf- und Anfrageverlauf</h3>
              <div className="mt-3 space-y-2">{premiumRequests.map((request: any) => <div key={request.id} className="flex flex-col gap-2 rounded-xl border border-slate-800 bg-black/10 px-4 py-3 sm:flex-row sm:items-center"><div className="flex-1"><p className="text-sm font-bold text-white">{request.duration_days}-Tage-Paket</p><p className="mt-0.5 text-xs text-slate-600">Angefragt am {formatTimestamp(request.created_at)}</p></div><span className={`w-fit rounded-full px-2.5 py-1 text-[11px] font-black ${request.status === "approved" ? "bg-emerald-500/10 text-emerald-300" : request.status === "pending" ? "bg-amber-400/10 text-amber-300" : "bg-slate-800 text-slate-400"}`}>{request.status === "approved" ? `Bestätigt${request.decided_at ? ` am ${formatTimestamp(request.decided_at)}` : ""}` : request.status === "pending" ? "Wird geprüft" : request.status === "denied" ? "Abgelehnt" : "Beendet"}</span></div>)}</div>
            </div>}
          </div>
        </section>

        <section className="grid gap-4 sm:grid-cols-2">
          {cards.map(card => <article key={card.label} className="rounded-2xl border border-slate-800 bg-[#131318] p-5 sm:p-6"><div className="flex items-start gap-4"><span className="grid h-11 w-11 place-items-center rounded-xl bg-white/[0.04]"><card.icon className={`h-5 w-5 ${card.color}`} /></span><div><p className="text-sm font-semibold text-slate-400">{card.label}</p><p className="mt-1 text-2xl font-bold tabular-nums text-white">{card.value}</p><p className="mt-1 text-xs text-slate-600">{card.hint}</p></div></div></article>)}
        </section>

        <section className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]">
          <div className="border-b border-slate-800 px-5 py-4 sm:px-6"><h2 className="text-lg font-bold text-white">Konto & Aktivität</h2><p className="mt-1 text-sm text-slate-500">Direkt aus Discord, Premium und dem Level-System.</p></div>
          <div className="grid sm:grid-cols-2">
            {[
              { label: "Discord-Konto seit", value: formatDate(createdAt), icon: CalendarDays },
              { label: "Letzte Leveling-Aktivität", value: lastActive ? formatDate(lastActive) : "Noch keine Aktivität", icon: Activity },
              { label: "Discord-Sprache", value: discordUser?.locale || "Nicht verfügbar", icon: Users },
              { label: "Kontostatus", value: premiumLabel, icon: ShieldCheck },
            ].map(item => <div key={item.label} className="flex items-center gap-4 border-b border-slate-800 px-5 py-5 last:border-b-0 sm:px-6 sm:[&:nth-child(odd)]:border-r"><item.icon className="h-5 w-5 text-indigo-400" /><div><p className="text-xs text-slate-600">{item.label}</p><p className="mt-1 text-sm font-semibold text-slate-200">{item.value}</p></div></div>)}
          </div>
        </section>

        <AccountActivityPanel activity={realStats?.activity || null} />
        <AccountSupportPanel userId={userId} />
        <AccountApplicationsPanel userId={userId} />
        <AccountPreferencesPanel userId={userId} />
        <AccountSecurityPanel userId={userId} />
        <AccountPrivacyPanel userId={userId} />
        <AccountActions />
        <AccountDangerZone userId={userId} username={username} />
      </main>
    </div>
  );
}

function PremiumFact({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: any }) {
  return <div className="rounded-2xl border border-slate-800 bg-black/15 p-4"><Icon className="h-4 w-4 text-amber-300"/><p className="mt-3 text-[10px] font-black uppercase tracking-wider text-slate-600">{label}</p><p className="mt-1 text-sm font-black text-white">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></div>;
}
