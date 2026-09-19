/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LanguageSwitcher } from "@/components/language-switcher";
import { GlobalSearch } from "@/components/global-search";
import { useProximity } from "@/components/ui/proximity";
import { PopoverLayer } from "@/components/ui/popover-layer";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import {
  LayoutDashboard, Palette, ScrollText, Server, ShieldCheck, ShieldAlert, Ticket, BarChart4, Command, FileText, Settings,
  Menu, X, Bell, User, Search, ChevronRight, Star, Sparkles, LogOut,
  Lock, PenLine, Gem, Pin, Moon, Calculator, Youtube, Cake, Crown,
  Database,
  LifeBuoy, ChevronDown, Bot, Shield, UserCheck, Badge, Gauge, Headphones,
  KeyRound, Music, Upload, Users, UserCog
} from "lucide-react";
import { useSession, signIn, signOut } from "next-auth/react";
import { cn, isAdmin } from "@/lib/utils";
import { api } from "@/lib/api";
import { AdminConfig } from "@/types/api";
import { SUPPORT_INVITE } from "@/lib/legal";

// Farbige Funktionssymbole wie im Referenz-Dashboard. Die Farbe beschreibt
// den Bereich; der aktive Zustand bleibt für alle Einträge einheitlich blau.
const SIDEBAR_ICON_COLORS: Record<string, string> = {
  "Allgemein": "text-sky-400", "Übersicht": "text-sky-400", "Hilfe": "text-indigo-300", "Design": "text-amber-400", "Premium": "text-amber-400", "Admin": "text-red-400",
  "Dashboard Access": "text-blue-400", "Server Einstellungen": "text-slate-300",
  "Backup": "text-amber-400", "Server Stats": "text-sky-400",
  "Anti-Nuke": "text-rose-400", "Automod": "text-pink-400", "Honeypot": "text-orange-400",
  "Verifizierung": "text-emerald-400", "Pull": "text-blue-400", "Notfall": "text-red-400", "Jail": "text-violet-400", "Nachtmodus": "text-indigo-400",
  "Begrüßung": "text-pink-400", "Bewerbungen": "text-violet-300", "Abschied": "text-orange-400",
  "Beitritts-DM": "text-cyan-400", "Auto-Rolle": "text-emerald-400", "Reaktions-Rollen": "text-fuchsia-400",
  "Eigene Rollen": "text-blue-400", "Vanity-Rollen": "text-amber-400", "Nickname": "text-purple-400", "Level-System": "text-orange-400",
  "Giveaways": "text-pink-400", "Counting": "text-teal-400", "Booster": "text-fuchsia-400",
  "Benachrichtigungen": "text-red-400", "Auto-Reaktion": "text-yellow-400", "Autoresponder": "text-cyan-400",
  "Custom Commands": "text-blue-400", "Anonymer Chat (Beta)": "text-violet-400",
  "Musik": "text-purple-400", "Join to Create": "text-sky-400", "Sprach-Rolle": "text-violet-400",
  "Tickets": "text-cyan-400", "Eigene Nachricht": "text-blue-400", "Sticky-Nachricht": "text-amber-400",
  "Einladungen": "text-emerald-400", "Einladungs-Log": "text-teal-400", "No Prefix": "text-lime-400",
  "Speedrun": "text-amber-400", "Hochladen (Experimentell)": "text-sky-400", "Community (Experimentell)": "text-fuchsia-400",
  "Teamliste": "text-emerald-400", "Team-Update (Beta)": "text-cyan-400", "Logs": "text-slate-300",
  "Bot-Logs": "text-indigo-300", "Server-Werkzeuge": "text-rose-400", "Support-Warteraum (Beta)": "text-cyan-400",
  "Einstellungen": "text-slate-300", "Zurück zur Serverliste": "text-sky-400",
};
const sidebarIconColor = (name: string) => SIDEBAR_ICON_COLORS[name] || "text-cyan-400";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isProfilOpen, setIsProfilOpen] = useState(false);
  const pathname = usePathname();
  const guildMatch = pathname.match(/\/dashboard\/guild\/([^\/]+)/);
  const currentGuildId = guildMatch ? guildMatch[1] : null;
  const [verificationOpen, setVerificationOpen] = useState(
    pathname.includes("/verification")
  );
  const { data: session, status } = useSession();
  const sessionUserId = (session?.user as any)?.id as string | undefined;
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [globalNotification, setGlobalNotification] = useState<string | null>(null);
  const [pendingSupportRequests, setPendingSupportRequests] = useState(0);
  // Driven by the maintenance_mode config plus the maintenance_banner feature flag.
  const [maintenance, setMaintenance] = useState(false);
  // True when the user holds a dashboard team role, which unlocks the admin panel.
  const [hasTeamRole, setHasTeamRole] = useState(false);
  // Full team access info, used for the role badge in the sidebar footer.
  const [teamAccess, setTeamAccess] = useState<{
    is_owner: boolean;
    roles: Array<{ key: string; label: string; color: string; rank: number }>;
  } | null>(null);
  // Hat dieses Konto Premium? Steht als goldenes Abzeichen unten
  // links, neben der Team-Rolle. Beides kann gleichzeitig gelten:
  // eine Team-Rolle sagt, was jemand DARF, Premium sagt, was er HAT.
  const [premium, setPremium] = useState<{
    aktiv: boolean;
    probewoche: boolean;
    tester: boolean;
  } | null>(null);
  // Support link comes from the bot settings so it is configurable.
  // The initial value is the shared default, not a second hard-coded
  // copy -- it is what shows for the moment before the fetch lands.
  const [supportInvite, setSupportInvite] = useState(SUPPORT_INVITE);
  
  const bellRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  // Klick daneben macht `PopoverLayer` fuer beide Menues selbst.
  //
  // Der alte Haken hier waere jetzt sogar schaedlich: die Menues
  // haengen per Portal an `document.body` und liegen nicht mehr in
  // `bellRef`/`profileRef`. Jeder Klick hinein -- etwa auf
  // "Abmelden" -- haette als "daneben" gezaehlt und das Menue
  // geschlossen, bevor der Knopf reagiert.

  // Auto-close sidebar on mobile when navigating
  React.useEffect(() => {
    setIsSidebarOpen(false);
    setIsProfilOpen(false);
  }, [pathname]);

  React.useEffect(() => {
    if (status === "unauthenticated") {
      signIn("discord", { callbackUrl: "/auth/success?next=%2Fdashboard" });
    }
    
    // Fetch global notification + maintenance state
    const fetchNotification = async () => {
      try {
        const config = await api.getAdminConfig();
        setGlobalNotification(config.global_notification);

        // The banner is only shown when maintenance mode is on AND the
        // maintenance_banner feature flag allows it.
        if (config.maintenance_mode) {
          try {
            const policy = await api.getSessionPolicy();
            setMaintenance(Boolean(policy.maintenance_banner));
          } catch {
            setMaintenance(true);
          }
        } else {
          setMaintenance(false);
        }
      } catch (err) {
        console.error("Failed to fetch notifications:", err);
      }
    };
    fetchNotification();

    // Does this user hold a dashboard role? Decides whether the admin link shows.
    const fetchTeamRole = async () => {
      const userId = (session?.user as any)?.id;
      if (!userId) return;
      try {
        const access = await api.getOwnAccess(userId);
        setTeamAccess(access);
        setHasTeamRole(Boolean(access?.is_owner || (access?.roles?.length ?? 0) > 0));
      } catch {
        setTeamAccess(null);
        setHasTeamRole(false);
      }
    };
    fetchTeamRole();

    // Premium-Status fuers Abzeichen unten links.
    //
    // Eigener Aufruf statt eines Felds in getOwnAccess: Premium haengt
    // am Konto, die Team-Rolle am Dashboard -- zwei Fragen, zwei
    // Quellen. Ein Fehler darf die Seitenleiste nicht aufhalten.
    const fetchPremium = async () => {
      const userId = (session?.user as any)?.id;
      if (!userId) return;
      try {
        const zustand = await api.getMyPremium(userId);
        const p = zustand?.premium ?? zustand?.template_bot;
        setPremium({
          aktiv: Boolean(p?.premium),
          probewoche: Boolean(p?.via_trial),
          tester: Boolean(p?.via_tester),
        });
      } catch {
        setPremium(null);
      }
    };
    fetchPremium();

    // Support invite is a bot setting; fall back to the default on error.
    api
      .getBotSettings()
      .then((data) => {
        const entry = (data?.settings || []).find(
          (x: any) => x.key === "support_server_invite"
        );
        if (entry?.effective) setSupportInvite(entry.effective);
      })
      .catch(() => {});
  }, [status, session?.user]);

  // Only the actual server owner is authorized for this endpoint. Everyone
  // else receives 403, which is intentionally treated as "no owner badge".
  React.useEffect(() => {
    if (!currentGuildId || !sessionUserId) {
      setPendingSupportRequests(0);
      return;
    }
    let active = true;
    const load = () => api.getGuildSupportCases(currentGuildId)
      .then((data) => { if (active) setPendingSupportRequests(Math.min(1, Number(data?.pending_count || 0))); })
      .catch(() => { if (active) setPendingSupportRequests(0); });
    load();
    const timer = window.setInterval(load, 30_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [currentGuildId, sessionUserId]);

  // The proximity effect from React Bits' LineSidebar.
  //
  // Above the early return on purpose: React requires every hook to run
  // on every render, and the loading branch below returns before the
  // sidebar is built. Placing it further down threw
  // "Rendered fewer hooks than expected" the moment the session
  // resolved.
  //
  // pathname is enough to derive the active row; the item list is not
  // needed yet at this point.
  const proximity = useProximity({ radius: 90, smoothing: 4 });

  if (status === "loading" || status === "unauthenticated") {
    return (
      <div className="min-h-screen bg-[#0a0a0c] flex items-center justify-center">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <div className="h-12 w-12 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/20">
            <span className="font-black text-white italic text-xl">{process.env.NEXT_PUBLIC_BRAND_NAME_WORD || "UB"}</span>
          </div>
          <p className="text-slate-400 font-bold tracking-widest uppercase text-xs">
            Authenticating...
          </p>
        </div>
      </div>
    );
  }

  // Base sidebar items – will be filtered if we are inside a guild
  const allSidebarItems = currentGuildId
    ? [
        { name: "Übersicht", href: `/dashboard/guild/${currentGuildId}`, icon: LayoutDashboard },
        { name: "Hilfe", href: `/dashboard/guild/${currentGuildId}/help`, icon: LifeBuoy, notification: pendingSupportRequests },
        // Ganz oben und gelb hervorgehoben: das Design ist die
        // Premium-Funktion, die man sehen soll, bevor man sie hat.
        //
        // Als eigene Gruppe, nicht als einzelner Eintrag: die
        // Reiterleiste darueber hat ebenfalls eine Gruppe "Design",
        // und test_navigation besteht zu Recht darauf, dass beide
        // Navigationen dieselben Gruppennamen benutzen.
        {
          name: "Design",
          items: [
            {
              name: "Premium",
              href: `/dashboard/guild/${currentGuildId}/premium`,
              icon: Crown,
              highlight: true,
            },
            {
              name: "Design",
              href: `/dashboard/guild/${currentGuildId}/design`,
              icon: Palette,
              highlight: true,
            },
            {
              // Golden wie Design: die Automatik und zehn Plaetze
              // sind Premium. Das Erstellen selbst geht auch ohne.
              name: "Backup",
              href: `/dashboard/guild/${currentGuildId}/backup`,
              icon: Database,
              highlight: true,
            },
            {
              name: "Server Stats",
              href: `/dashboard/guild/${currentGuildId}/server-stats`,
              icon: BarChart4,
            },
          ],
        },
        {
          // Same grouping as the tab bar. Two navigations that disagree
          // about where something lives is worse than one.
          name: "Schutz",
          items: [
            { name: "Anti-Nuke", href: `/dashboard/guild/${currentGuildId}/antinuke`, icon: ShieldCheck },
            { name: "Automod", href: `/dashboard/guild/${currentGuildId}/automod`, icon: ShieldCheck },
            { name: "Honeypot", href: `/dashboard/guild/${currentGuildId}/honeypot`, icon: ShieldAlert },
            {
              name: "Verifizierung",
              href: `/dashboard/guild/${currentGuildId}/verification`,
              icon: User,
              children: [
                { name: "Einstellungen", href: `/dashboard/guild/${currentGuildId}/verification`, icon: ShieldCheck },
                { name: "Pull", href: `/dashboard/guild/${currentGuildId}/verification/pull`, icon: Users, highlight: true },
              ],
            },
            { name: "Notfall", href: `/dashboard/guild/${currentGuildId}/emergency`, icon: Shield },
            { name: "Jail", href: `/dashboard/guild/${currentGuildId}/jail`, icon: Lock },
            { name: "Nachtmodus", href: `/dashboard/guild/${currentGuildId}/nightmode`, icon: Moon },
          ],
        },
        {
          name: "Mitglieder",
          items: [
            { name: "Begrüßung", href: `/dashboard/guild/${currentGuildId}/welcome`, icon: Bell },
            { name: "Bewerbungen", href: `/dashboard/guild/${currentGuildId}/applications`, icon: FileText },
            { name: "Abschied", href: `/dashboard/guild/${currentGuildId}/leave`, icon: LogOut },
            { name: "Beitritts-DM", href: `/dashboard/guild/${currentGuildId}/joindm`, icon: User },
            { name: "Auto-Rolle", href: `/dashboard/guild/${currentGuildId}/autorole`, icon: Search },
            { name: "Reaktions-Rollen", href: `/dashboard/guild/${currentGuildId}/reactionroles`, icon: Search },
            { name: "Eigene Rollen", href: `/dashboard/guild/${currentGuildId}/customroles`, icon: ShieldCheck },
            { name: "Vanity-Rollen", href: `/dashboard/guild/${currentGuildId}/vanityroles`, icon: Star },
            { name: "Nickname", href: `/dashboard/guild/${currentGuildId}/nickname`, icon: Badge },
            { name: "Level-System", href: `/dashboard/guild/${currentGuildId}/leveling`, icon: BarChart4 },
          ],
        },
        {
          name: "Aktivität",
          items: [
            { name: "Giveaways", href: `/dashboard/guild/${currentGuildId}/giveaways`, icon: Star },
            { name: "Counting", href: `/dashboard/guild/${currentGuildId}/counting`, icon: Calculator },
            { name: "Booster", href: `/dashboard/guild/${currentGuildId}/booster`, icon: Gem },
            { name: "Benachrichtigungen", href: `/dashboard/guild/${currentGuildId}/notify`, icon: Youtube },
            { name: "Auto-Reaktion", href: `/dashboard/guild/${currentGuildId}/autoreact`, icon: Settings },
            { name: "Autoresponder", href: `/dashboard/guild/${currentGuildId}/autoresponder`, icon: PenLine },
            { name: "Custom Commands", href: `/dashboard/guild/${currentGuildId}/custom-commands`, icon: Command },
            { name: "Anonymer Chat (Beta)", href: `/dashboard/guild/${currentGuildId}/anonchat`, icon: Lock },
          ],
        },
        {
          name: "Sprache",
          items: [
            { name: "Musik", href: `/dashboard/guild/${currentGuildId}/music`, icon: Music },
            { name: "Join to Create", href: `/dashboard/guild/${currentGuildId}/j2c`, icon: Menu },
            { name: "Sprach-Rolle", href: `/dashboard/guild/${currentGuildId}/invcrole`, icon: Settings },
          ],
        },
        {
          name: "Werkzeuge",
          items: [
            { name: "Tickets", href: `/dashboard/guild/${currentGuildId}/tickets`, icon: Ticket },
            { name: "Eigene Nachricht", href: `/dashboard/guild/${currentGuildId}/compose`, icon: PenLine },
            { name: "Sticky-Nachricht", href: `/dashboard/guild/${currentGuildId}/sticky`, icon: Pin },
            { name: "Einladungen", href: `/dashboard/guild/${currentGuildId}/invites`, icon: Search },
            { name: "Einladungs-Log", href: `/dashboard/guild/${currentGuildId}/tracking`, icon: BarChart4 },
            { name: "No Prefix", href: `/dashboard/guild/${currentGuildId}/noprefix`, icon: UserCheck },
          ],
        },
        {
          // Alles, was einen Server aufsetzt oder umbaut, an einer
          // Stelle. Der Speedrun stand vorher unter "Verwaltung" --
          // er gehoert thematisch hierher.
          name: "Templates",
          items: [
            {
              // Golden wie Design: der Speedrun ist eine
              // Premium-Funktion, keine Beta mehr. `highlight` ist
              // dasselbe Feld, an dem der Design-Reiter haengt --
              // kein zweiter Sonderfall.
              name: "Speedrun",
              href: `/dashboard/guild/${currentGuildId}/speedrun`,
              icon: Gauge,
              highlight: true,
            },
            { name: "Hochladen (Experimentell)", href: `/dashboard/guild/${currentGuildId}/template-upload`, icon: Upload },
            { name: "Community (Experimentell)", href: `/dashboard/guild/${currentGuildId}/templates`, icon: Sparkles },
          ],
        },
        {
          name: "Verwaltung",
          items: [
            { name: "Teamliste", href: `/dashboard/guild/${currentGuildId}/teamlist`, icon: Users },
            { name: "Team-Update (Beta)", href: `/dashboard/guild/${currentGuildId}/teamupdate`, icon: UserCog },
            { name: "Logs", href: `/dashboard/guild/${currentGuildId}/logging`, icon: LayoutDashboard },
            { name: "Bot-Logs", href: `/dashboard/guild/${currentGuildId}/botlogs`, icon: ScrollText },
            { name: "Server-Werkzeuge", href: `/dashboard/guild/${currentGuildId}/admin-dashboard`, icon: Shield },
            { name: "Dashboard Access", href: `/dashboard/guild/${currentGuildId}/dashboard-access`, icon: KeyRound },
            { name: "Support-Warteraum (Beta)", href: `/dashboard/guild/${currentGuildId}/supportqueue`, icon: Headphones },
          ],
        },
        { name: "Einstellungen", href: `/dashboard/guild/${currentGuildId}/settings`, icon: Settings },
        { name: "Zurück zur Serverliste", href: "/dashboard/guilds", icon: Server },
      ]
    : [
        { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
        { name: "Server", href: "/dashboard/guilds", icon: Server },
        // Premium is for everyone: a customer who bought a key needs to
        // reach the redeem field without being staff.
        { name: "Premium", href: "/dashboard/premium", icon: Gem },
        ...(isAdmin(session?.user?.id) || hasTeamRole
            ? [{ name: "Admin Panel", href: "/dashboard/admin", icon: Shield }]
            : []),
      ];

  // Separate the "Back to Server" item when inside a guild
  let mainSidebarItems = allSidebarItems;
  let backLinkItem: any = null;

  if (currentGuildId) {
    mainSidebarItems = allSidebarItems.filter(
      (item) => !(item.name === "Back to Server")
    );
    backLinkItem = allSidebarItems.find((item) => item.name === "Back to Server");
  }

  const BackLinkIcon = backLinkItem?.icon || Server;

  return (
    <div className="min-h-screen bg-[#0a0a0c] text-slate-200">
      {/* Liquid Background Elements */}
      {/* Ein ruhiger Schein statt zwei pulsierender Flaechen. */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-15%] right-[-10%] h-[45%] w-[45%] rounded-full bg-indigo-600/[0.05] blur-[140px]" />
      </div>

      {/* Mobile Sidebar Overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-[#02030a]/72 backdrop-blur-md lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar - now using flex column */}
      <aside
        className={cn(
          // Sitzt am Rand statt zu schweben: eine 2.5rem-Rundung mit
          // Schlagschatten sieht aus wie eine Karte auf einer Karte.
          "fixed bottom-2 left-2 top-2 z-50 w-[min(88vw,360px)] transform transition-transform duration-300 lg:bottom-0 lg:left-0 lg:top-0 lg:w-[272px] lg:translate-x-0 lg:rounded-none",
          "overflow-hidden rounded-[28px] border border-white/[.12] bg-[#090b12]/82 shadow-[0_28px_100px_rgba(0,0,0,.72)] backdrop-blur-3xl flex flex-col",
          isSidebarOpen ? "translate-x-0" : "-translate-x-[115%]"
        )}
      >
        <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-blue-600/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-20 h-56 w-56 rounded-full bg-indigo-500/10 blur-3xl" />

        {/* Header */}
        <div className="relative flex flex-shrink-0 items-center gap-3 border-b border-white/[.08] px-4 py-4">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl border border-blue-300/20 bg-blue-500/10 shadow-[0_8px_24px_rgba(37,99,235,.18)]">
            <Bot className="h-5 w-5 text-indigo-300" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[16px] font-black leading-none tracking-tight text-white">
              {process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot"}
            </h1>
            <span className="mt-1.5 block text-[9px] font-black uppercase tracking-[.22em] text-blue-300/80">Control Center</span>
          </div>
          <button
            className="grid h-10 w-10 place-items-center rounded-2xl border border-white/[.08] bg-white/[.045] text-slate-400 transition hover:bg-white/[.09] hover:text-white lg:hidden"
            onClick={() => setIsSidebarOpen(false)}
            aria-label="Navigation schließen"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Navigation */}
        <nav
          // pr-10 rather than px-4 on both sides: the rows slide right
          // by up to 37px, and a scroll container clips at its padding
          // box. With 16px of room they were cut off; 40px clears the
          // full travel with 3px to spare. 44px would be too much --
          // "Zurück zur Serverliste" starts wrapping. Worked out in
          // repro/prox_shift_budget.py.
          className="relative z-10 flex-1 space-y-2 overflow-y-auto py-3 pl-3 pr-10 no-scrollbar"
          {...proximity.containerProps}
        >
          {(() => {
            // Every link in the sidebar takes part, sub-links included.
            // They are all in one scrolling column, so one running index
            // over the whole thing is all the effect needs -- a group
            // heading is not a link and simply does not get one.
            let flat = -1;
            const nextIndex = () => ++flat;
            return mainSidebarItems.map((item: any) => {
              const proxIndex = item.items ? -1 : nextIndex();
            if (item.items) {
              return (
                <div key={item.name} className="space-y-1.5 pt-2">
                  <p className="px-3 text-[9px] font-black uppercase tracking-[.2em] text-slate-500">
                    {item.name}
                  </p>
                  <div className="space-y-1.5">
                    {item.items.map((subItem: any) => {
                      const isActive = pathname === subItem.href;
                      const subIndex = nextIndex();
                      // Der Speedrun steht in der Gruppe "Verwaltung",
                      // wird also *hier* gerendert und nicht im Zweig
                      // für die oberste Ebene weiter unten.
                      //
                      // Genau daran ist die Hervorhebung vorher
                      // gescheitert: sie stand nur dort. Premium sah
                      // richtig aus, weil Premium ein Eintrag der
                      // obersten Ebene ist -- der Speedrun ist es
                      // nicht, und der Stil kam nie an.
                      // Beta-Reiter tragen denselben Stil: eigenes
                      // Symbol-Feld, Abzeichen, ruhigeres Licht. Der
                      // Warteraum ist der zweite davon -- die Liste
                      // steht hier, damit ein dritter nicht wieder
                      // durchs Raster fällt.
                      const isSpeedrun = ["/speedrun", "/supportqueue"].some(
                        (path) => subItem.href.endsWith(path)
                      );
                      if (subItem.children) {
                        const sectionActive = pathname.startsWith(subItem.href);
                        return (
                          <div key={subItem.name} className="space-y-1">
                            <div
                              data-active={sectionActive ? "true" : undefined}
                              {...proximity.itemProps(subIndex)}
                              className={cn(
                                "prox-row prox-row-sm flex items-center rounded-2xl border transition-all text-[13px]",
                                sectionActive
                                  ? "border-blue-400/25 bg-blue-500/12 text-white font-semibold"
                                  : "border-white/[.07] bg-white/[.035] text-slate-400 hover:border-white/[.12] hover:bg-white/[.065] hover:text-slate-200"
                              )}
                            >
                              <Link href={subItem.href} className="flex min-w-0 flex-1 items-center gap-3 px-3 py-2">
                                <subItem.icon className={cn("h-4 w-4 shrink-0", sidebarIconColor(subItem.name))} />
                                <span className="truncate">{subItem.name}</span>
                              </Link>
                              <button
                                type="button"
                                onClick={() => setVerificationOpen((open) => !open)}
                                aria-expanded={verificationOpen}
                                aria-label="Verifizierung aufklappen"
                                className="mr-1 grid h-8 w-8 shrink-0 place-items-center rounded-md hover:bg-white/5"
                              >
                                <ChevronDown className={cn("h-4 w-4 transition-transform", verificationOpen && "rotate-180")} />
                              </button>
                            </div>
                            {verificationOpen && (
                              <div className="space-y-1 pl-7">
                                {subItem.children.map((child: any) => {
                                  const childActive = pathname === child.href;
                                  return (
                                    <Link
                                      key={child.name}
                                      href={child.href}
                                      className={cn(
                                        "flex items-center gap-2 rounded-xl border px-3 py-2 text-xs transition-colors",
                                        child.highlight
                                          ? childActive
                                            ? "border-amber-400/20 bg-amber-400/10 font-semibold text-amber-200"
                                            : "border-amber-400/10 bg-amber-400/[.035] text-amber-300/80 hover:bg-amber-400/[.07]"
                                          : childActive
                                            ? "border-blue-400/20 bg-blue-500/10 font-semibold text-blue-200"
                                            : "border-white/[.05] bg-white/[.025] text-slate-500 hover:bg-white/[.055] hover:text-slate-300"
                                      )}
                                    >
                                      <child.icon className={cn("h-3.5 w-3.5", child.highlight ? "text-amber-400" : sidebarIconColor(child.name))} />
                                      <span className="min-w-0 flex-1 truncate">{child.name}</span>
                                      {child.highlight && <Crown className="h-3 w-3 shrink-0 text-amber-400" aria-label="Premium" />}
                                    </Link>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      }
                      return (
                        <Link
                          key={subItem.name}
                          href={subItem.href}
                          data-active={isActive ? "true" : undefined}
                          {...proximity.itemProps(subIndex)}
                          // Ein Stil fuer jede Zeile.
                          //
                          // Vorher hatte der Speedrun einen eigenen
                          // (cyan, wanderndes Licht), der aktive
                          // Eintrag ein blaues Leuchten und einen
                          // pulsierenden Punkt. Vier Sonderfaelle in
                          // einer Liste heisst: nichts sticht mehr
                          // hervor, weil alles hervorsticht.
                          className={cn(
                            "prox-row prox-row-sm",
                            "flex items-center gap-3 rounded-2xl border px-3 py-2.5 transition-all group text-[13px]",
                            // Gelb auch in einer Gruppe.
                            //
                            // Genau der Fall, vor dem der Kommentar
                            // oben warnt: `isPremium` gibt es nur auf
                            // der obersten Ebene. Der Design-Reiter
                            // steht in einer Gruppe, also haette er
                            // den Stil sonst nie bekommen -- der
                            // gelbe Rahmen waere im Code gestanden
                            // und auf dem Bildschirm nicht zu sehen.
                            (subItem as any).highlight
                              ? isActive
                                ? "border-amber-400/25 bg-amber-400/10 text-amber-200 font-semibold"
                                : "border-amber-400/10 bg-amber-400/[.035] text-amber-300/80 hover:bg-amber-400/[.07] hover:text-amber-200"
                              : isActive
                              ? "border-blue-400/25 bg-blue-500/12 text-white font-semibold"
                              : "border-white/[.07] bg-white/[.035] text-slate-400 hover:border-white/[.12] hover:bg-white/[.065] hover:text-slate-200"
                          )}
                        >
                          <subItem.icon
                            className={cn(
                              "h-4 w-4 shrink-0 transition-colors",
                              (subItem as any).highlight
                                ? "text-amber-400"
                                : sidebarIconColor(subItem.name)
                            )}
                          />
                          {/* "(Beta)" als Zeichen statt als Text: in
                              einer Untereintrag-Zeile ist der Platz
                              knapp, und die Klammer ist lauter als
                              das, was sie sagt. */}
                          <span className="min-w-0 truncate">
                            {subItem.name.replace(" (Beta)", "")}
                          </span>
                          {/* "(Beta)" als ruhiges Zeichen statt als
                              Klammer im Text -- und in derselben
                              Farbe wie ueberall sonst. */}
                          {subItem.name.includes("(Beta)") && (
                            <span className="ml-auto shrink-0 rounded bg-white/[0.06] px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-slate-400">
                              BETA
                            </span>
                          )}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              );
            }

            const isActive = pathname === item.href;
            // Premium is the one entry that should catch the eye before
            // it is read, so it glows gold instead of using the flat
            // blue every other link shares. Keyed off the href, not the
            // label, because the label is translated.
            // Golden wird alles, was Premium verkauft oder braucht.
            //
            // Der Design-Reiter haengt sich hier an, statt einen
            // vierten Sonderfall zu bauen: er ist die
            // Premium-Funktion, die man sehen soll, bevor man sie
            // hat -- und `highlight` am Eintrag sagt genau das.
            const isPremium =
              item.href === "/dashboard/premium" || Boolean((item as any).highlight);
            // Admin gets its own treatment: a steel plate rather than the
            // flat blue, but deliberately without Premium's pulse — this
            // one is clicked daily and a permanent animation would wear
            // thin. Keyed off the href, not the label, which is
            // translated.
            const isAdmin = item.href === "/dashboard/admin";
            // Der Speedrun baut einen ganzen Server -- er soll
            // nicht aussehen wie "Nickname" drei Zeilen darüber.
            // Eigene Farbe, eigenes Symbol-Feld und ein Licht,
            // das über die Oberkante läuft.
            const isSpeedrun = ["/speedrun", "/supportqueue"].some((path) =>
              item.href.endsWith(path)
            );
            return (
              <Link
                key={item.name}
                href={item.href}
                data-active={isActive ? "true" : undefined}
                // Still a real Link: right-click, middle-click, the URL
                // preview and Next.js prefetching all keep working. The
                // original component renders <li onClick>, which loses
                // every one of those.
                {...proximity.itemProps(proxIndex)}
                // Ein Stil, drei Zustaende.
                //
                // Premium hatte ein goldenes Pulsieren, Admin eine
                // Stahlplatte, der Speedrun ein wanderndes Licht --
                // drei Ausnahmen in einer Liste von fuenf Eintraegen.
                // Premium bleibt farblich hervorgehoben, weil es
                // etwas verkauft; alles andere ist jetzt gleich
                // ruhig.
                className={cn(
                  "prox-row",
                  "flex items-center gap-3 rounded-2xl border px-3 py-3 transition-all group text-[14px]",
                  isPremium
                    ? isActive
                      ? "border-amber-400/25 bg-amber-400/10 text-amber-200 font-semibold"
                      : "border-amber-400/10 bg-amber-400/[.035] text-amber-300/80 hover:bg-amber-400/[.07] hover:text-amber-200"
                    : isActive
                    ? "border-blue-300/25 bg-gradient-to-r from-blue-600/25 to-indigo-500/15 text-white font-semibold shadow-[0_12px_30px_rgba(37,99,235,.14)]"
                    : "border-white/[.07] bg-white/[.035] text-slate-400 hover:border-white/[.12] hover:bg-white/[.065] hover:text-slate-200"
                )}
              >
                {/* No leading line and no 01/02/03 gutter, both from the
                    original LineSidebar. The numbers were the loudest
                    thing in a sidebar that is read by label, and the
                    line was a second signal for what the movement
                    already says. The shift alone carries the effect. */}
                <item.icon
                  className={cn(
                    "box-content h-[18px] w-[18px] shrink-0 rounded-xl border border-white/[.07] bg-black/15 p-2 transition-colors",
                    isPremium
                      ? "text-amber-400"
                      : sidebarIconColor(item.name)
                  )}
                />
                {/* Der Reiter heißt in der Navigation "Speedrun (Beta)".
                    Das Wort in Klammern mitzuschleppen macht die Zeile
                    lang und die Klammer laut; als kleines Zeichen sagt
                    es dasselbe und stört nicht beim Lesen. */}
                <span className="min-w-0 truncate">
                  {item.name.replace(" (Beta)", "")}
                </span>
                {Number((item as any).notification || 0) > 0 && (
                  <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-black text-white shadow-[0_0_12px_rgba(244,63,94,.45)]">1</span>
                )}
                {item.name.includes("(Beta)") && (
                  <span className="ml-auto shrink-0 rounded bg-white/[0.06] px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-slate-400">
                    BETA
                  </span>
                )}
              </Link>
            );
            });
          })()}
        </nav>

        {/* Fixed "Back to Server" link (only shown inside a guild) */}
        {backLinkItem && (
          <div className="relative flex-shrink-0 px-3 py-2">
            <div className="mx-auto mb-2 h-px w-3/4 rounded-full bg-white/[.08]" />
            <Link
              href={backLinkItem.href || "/dashboard/guilds"}
              className={cn(
                "flex items-center gap-3 rounded-2xl border px-3 py-3 transition-all group text-[13px]",
                pathname === backLinkItem.href
                  ? "border-blue-400/25 bg-blue-500/12 text-white font-semibold"
                  : "border-white/[.07] bg-white/[.035] text-slate-400 hover:border-white/[.12] hover:bg-white/[.065] hover:text-slate-200"
              )}
            >
              <BackLinkIcon
                className={cn(
                  "h-[18px] w-[18px] shrink-0 transition-colors",
                  sidebarIconColor(backLinkItem.name)
                )}
              />
              {backLinkItem.name}
              {pathname === backLinkItem.href ? (
                <ChevronRight className="ml-auto h-4 w-4 text-blue-500" />
              ) : (
                <ChevronRight className="ml-auto h-4 w-4 opacity-0 group-hover:opacity-30 transition-opacity" />
              )}
            </Link>
          </div>
        )}

        {/* User Profil - now a normal flex child, no absolute positioning */}
        <div className="relative flex-shrink-0 border-t border-white/[.08] p-3">
          <div className="flex items-center gap-3 rounded-2xl border border-white/[.09] bg-white/[.05] p-2.5 shadow-[0_12px_30px_rgba(0,0,0,.2)]">
            <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-xl border border-blue-400/20 bg-blue-500/10 ring-1 ring-white/10">
              {session?.user?.image ? (
                <img
                  src={session.user.image}
                  alt="User Avatar"
                  className="h-full w-full object-cover opacity-80"
                />
              ) : (
                <User className="h-6 w-6 text-blue-500/50" />
              )}
            </div>
            <div className="overflow-hidden min-w-0">
              <p className="text-sm font-bold text-white truncate font-outfit">
                {session?.user?.name || "Administrator"}
              </p>
              {/* Shows the actual dashboard role instead of a hardcoded "User" */}
              {teamAccess?.is_owner ? (
                <p className="text-[10px] font-black uppercase truncate tracking-widest text-amber-400">
                  Owner
                </p>
              ) : teamAccess?.roles?.length ? (
                <p
                  className="text-[10px] font-black uppercase truncate tracking-widest"
                  style={{ color: teamAccess.roles[0].color }}
                  title={teamAccess.roles.map((r) => r.label).join(", ")}
                >
                  {teamAccess.roles[0].label}
                  {teamAccess.roles.length > 1 && (
                    <span className="text-slate-500"> +{teamAccess.roles.length - 1}</span>
                  )}
                </p>
              ) : (
                <p className="text-[10px] font-black uppercase text-slate-500 truncate tracking-widest">
                  Member
                </p>
              )}
            </div>

            {/* Das Premium-Abzeichen.
                
                Steht NEBEN der Rolle, nicht statt ihr: eine Team-Rolle
                sagt, was jemand darf, Premium sagt, was er hat. Beides
                kann gleichzeitig gelten, und wer beides hat, soll auch
                beides sehen.

                Nur wenn wirklich Premium besteht -- ein graues
                „kein Premium" wäre eine Dauerwerbung an der Stelle,
                an der sonst der eigene Name steht. */}
            {premium?.aktiv && (
              <span
                className="ml-auto shrink-0 rounded-lg border border-amber-400/30 bg-amber-400/10 px-1.5 py-1 text-amber-400"
                title={
                  premium.probewoche
                    ? "Premium über die Probewoche"
                    : premium.tester
                      ? "Premium über den Tester-Zugang"
                      : "Premium ist aktiv"
                }
              >
                <Crown className="h-3.5 w-3.5" />
              </span>
            )}
          </div>

          {/* Was das Premium gerade ist -- eine Zeile, nur wenn es
              etwas zu sagen gibt. Eine laufende Probewoche endet, und
              das soll man sehen, bevor sie weg ist. */}
          {premium?.aktiv && (premium.probewoche || premium.tester) && (
            <p className="mt-1.5 px-2 text-[10px] font-bold uppercase tracking-widest text-amber-400/70">
              {premium.probewoche ? "Probewoche läuft" : "Tester-Zugang"}
            </p>
          )}
        </div>
      </aside>

      {/* Main Content Area (unchanged) */}
      <div className="relative z-10 flex min-h-screen flex-col lg:pl-[272px]">
        {/* Top Navbar (unchanged) */}
        <header className="h-16 lg:h-20 sticky top-2 lg:top-4 z-30 mx-3 lg:mx-10 flex items-center justify-between gap-2 border border-white/10 glass bg-white/[0.01] backdrop-blur-3xl px-3 lg:px-8 rounded-[1.5rem] lg:rounded-[2rem] shadow-xl shadow-black/20 mb-4 lg:mb-6 mt-3 lg:mt-4">
          <button
            className="p-2 lg:hidden text-slate-400 hover:bg-white/5 rounded-xl transition-colors"
            onClick={() => setIsSidebarOpen(true)}
          >
            <Menu className="h-6 w-6" />
          </button>

          <GlobalSearch />

          <div className="flex items-center gap-2 lg:gap-6">
            <div className="relative" ref={bellRef}>
              <button 
                onClick={() => setIsNotificationsOpen(!isNotificationsOpen)}
                className="relative p-2.5 text-slate-400 hover:bg-white/5 hover:text-white rounded-xl transition-all group"
              >
                <Bell className="h-5 w-5" />
                {pendingSupportRequests > 0 ? (
                  <span className="absolute -right-0.5 -top-0.5 grid h-5 min-w-5 place-items-center rounded-full border-2 border-[#0a0a0c] bg-rose-500 px-1 text-[10px] font-black text-white">1</span>
                ) : globalNotification ? (
                  <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-blue-500 border-2 border-[#0a0a0c] shadow-[0_0_10px_rgba(59,130,246,0.5)]"></span>
                ) : null}
              </button>

              <PopoverLayer
                anchor={bellRef}
                open={isNotificationsOpen}
                onClose={() => setIsNotificationsOpen(false)}
                align="end"
                width={320}
                minHeight={0}
                maxHeight={420}
                className="bg-[#071a33]/90 backdrop-blur-3xl border border-white/5 rounded-[24px] shadow-[0_20px_50px_rgba(0,0,0,0.5)] animate-in fade-in zoom-in-95 duration-300 origin-top-right"
              >
                <div className="overflow-y-auto p-4">
                    <div className="flex items-center justify-between mb-4 border-b border-white/5 pb-2">
                      <p className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Broadcast Metrics</p>
                      <button 
                        onClick={() => setGlobalNotification(null)}
                        className="text-[10px] font-bold text-blue-500/60 hover:text-blue-500 transition-colors uppercase"
                      >
                        Clear
                      </button>
                    </div>
                    
                    {pendingSupportRequests > 0 && currentGuildId && (
                      <Link
                        href={`/dashboard/guild/${currentGuildId}/help`}
                        onClick={() => setIsNotificationsOpen(false)}
                        className="mb-3 block rounded-2xl border border-rose-500/20 bg-rose-500/[0.07] p-4 transition hover:bg-rose-500/10"
                      >
                        <div className="flex items-center gap-2"><LifeBuoy className="h-4 w-4 text-rose-300" /><span className="text-[10px] font-black uppercase tracking-widest text-rose-300">Admin-Anfrage</span></div>
                        <p className="mt-2 text-xs font-semibold text-slate-200">Ein Supporter möchte dir bei deinem Server helfen.</p>
                        <p className="mt-1 text-[10px] text-slate-500">Nur du als Serverinhaber kannst annehmen oder ablehnen.</p>
                      </Link>
                    )}

                    {globalNotification ? (
                      <div className="bg-blue-500/5 border border-blue-500/10 rounded-2xl p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <Sparkles className="h-3 w-3 text-blue-500" />
                          <span className="text-[10px] font-black uppercase text-blue-500 tracking-widest">System Broadcast</span>
                        </div>
                        <p className="text-xs font-medium text-slate-300 leading-relaxed">
                          {globalNotification}
                        </p>
                      </div>
                    ) : pendingSupportRequests === 0 ? (
                      <div className="py-8 flex flex-col items-center justify-center text-center">
                        <div className="h-10 w-10 rounded-full bg-slate-800 flex items-center justify-center mb-3">
                          <Bell className="h-5 w-5 text-slate-600" />
                        </div>
                        <p className="text-xs font-bold text-slate-500">No active broadcasts</p>
                        <p className="text-[10px] font-medium text-slate-600 mt-1 uppercase tracking-widest">Everything is operating normally</p>
                      </div>
                    ) : null}
                </div>
              </PopoverLayer>
            </div>
            <div className="h-8 w-[1px] bg-white/5 hidden sm:block"></div>

            {/* Sprachumschalter — direkt neben dem Profil. Der Import
                stand schon lange hier, gerendert wurde er nie: im
                Dashboard gab es also keine Möglichkeit, die Sprache zu
                wechseln, obwohl der Umschalter und das Wörterbuch da
                sind. Auf schmalen Bildschirmen zeigt der Knopf nur die
                Flagge, damit Glocke, Profil und Suche Platz behalten. */}
            <LanguageSwitcher />

            {/* Profil Dropdown (unchanged) */}
            <div className="relative" ref={profileRef}>
              <button
                onClick={() => setIsProfilOpen(!isProfilOpen)}
                className="flex items-center gap-3.5 p-1.5 rounded-2xl hover:bg-white/5 transition-all group border border-transparent hover:border-white/10"
              >
                <div className="h-9 w-9 rounded-full bg-blue-500/10 flex items-center justify-center overflow-hidden border border-blue-500/20 ring-2 ring-transparent group-hover:ring-blue-500/30 transition-all">
                  {session?.user?.image ? (
                    <img src={session.user.image} alt="User Avatar" className="h-full w-full object-cover opacity-80" />
                  ) : (
                    <User className="h-5 w-5 text-blue-500/50" />
                  )}
                </div>
                <div className="hidden sm:flex flex-col items-start leading-none gap-1">
                  <span className="text-xs font-bold text-slate-200 group-hover:text-white transition-colors">
                    {session?.user?.name?.split(' ')[0] || "Admin"}
                  </span>
                  <span
                    className="text-[9px] font-black uppercase tracking-widest"
                    style={{
                      color: teamAccess?.is_owner
                        ? "#fbbf24"
                        : teamAccess?.roles?.[0]?.color ?? "#63666f",
                    }}
                  >
                    {teamAccess?.is_owner
                      ? "Owner"
                      : teamAccess?.roles?.[0]?.label ?? "Member"}
                  </span>
                </div>
                <ChevronDown
                  className={cn("h-4 w-4 text-slate-600 transition-transform hidden sm:block", isProfilOpen && "rotate-180")}
                />
              </button>

              <PopoverLayer
                anchor={profileRef}
                open={isProfilOpen}
                onClose={() => setIsProfilOpen(false)}
                align="end"
                width={224}
                minHeight={0}
                maxHeight={420}
                className="bg-[#071a33]/90 backdrop-blur-3xl border border-white/5 rounded-[24px] shadow-[0_20px_50px_rgba(0,0,0,0.5)] animate-in fade-in zoom-in-95 duration-300 origin-top-right"
              >
                <div className="overflow-y-auto p-2">
                    <div className="px-4 py-3 border-b border-white/5 mb-2">
                      <p className="text-[9px] font-black text-slate-500 uppercase tracking-[0.2em] mb-1">Authenticated As</p>
                      <p className="text-sm font-bold text-white truncate">{session?.user?.name || "Administrator"}</p>
                      {(premium?.aktiv ||
                        teamAccess?.is_owner ||
                        (teamAccess?.roles?.length ?? 0) > 0) && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {/* Premium zuerst: es ist das, was sich
                              ändern kann. Eine Team-Rolle hat man
                              oder hat man nicht. */}
                          {premium?.aktiv && (
                            <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-amber-400/10 text-amber-400 border border-amber-400/20">
                              {premium.probewoche
                                ? "Premium · Probewoche"
                                : premium.tester
                                  ? "Premium · Tester"
                                  : "Premium"}
                            </span>
                          )}
                          {teamAccess?.is_owner ? (
                            <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-amber-400/10 text-amber-400 border border-amber-400/20">
                              Owner
                            </span>
                          ) : (
                            teamAccess?.roles.map((role) => (
                              <span
                                key={role.key}
                                className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md border"
                                style={{
                                  color: role.color,
                                  borderColor: `${role.color}40`,
                                  backgroundColor: `${role.color}15`,
                                }}
                              >
                                {role.label}
                              </span>
                            ))
                          )}
                        </div>
                      )}
                    </div>

                    <a
                      href={supportInvite}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-xs font-bold text-slate-400 hover:bg-white/5 hover:text-white transition-all group/item"
                    >
                      <LifeBuoy className="h-4 w-4 text-slate-600 group-hover/item:text-blue-500 transition-colors" />
                      Support Server
                    </a>

                    <button
                      onClick={() => signOut({ callbackUrl: '/' })}
                      className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-xs font-black uppercase tracking-widest text-blue-500/80 hover:bg-blue-500/10 hover:text-blue-500 transition-all group/item"
                    >
                      <LogOut className="h-4 w-4" />
                      Deauthorize
                    </button>
                </div>
              </PopoverLayer>
            </div>
          </div>
        </header>

        {/* Content Area */}
        <main className="flex-1 p-3 sm:p-6 lg:p-10 animate-in fade-in duration-700 relative z-10">
          <div className="max-w-[1600px] mx-auto">
            {maintenance && (
              <div className="mb-6 flex items-center gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-5 py-4">
                <Shield className="h-5 w-5 shrink-0 text-amber-400" />
                <p className="text-sm font-medium text-amber-200">
                  <span className="font-black uppercase tracking-widest text-xs">Maintenance mode</span>
                  {" — "}
                  bot commands are frozen for everyone except the bot owners. Configuration changes are still saved.
                </p>
              </div>
            )}
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
