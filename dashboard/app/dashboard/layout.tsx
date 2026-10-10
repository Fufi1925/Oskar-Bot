/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 CloudTIX Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
 * ║   youtube  ──  https://youtube.com/@CloudTIX BotDevs                   ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

import { openLoginPanel } from "@/lib/login-panel";

import { BRAND_LOGO } from "@/lib/brand";
import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LanguageSwitcher } from "@/components/language-switcher";
import { GlobalSearch } from "@/components/global-search";
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
import { useSession, signOut } from "next-auth/react";
import { cn, isAdmin } from "@/lib/utils";
import { api } from "@/lib/api";
import { AdminConfig } from "@/types/api";
import { SUPPORT_INVITE } from "@/lib/legal";
import { guildModuleFromHref } from "@/lib/guild-modules";
import "@/components/dashboard/admin-workspace.css";
import "@/components/dashboard/workspace.css";
import { WorkspaceNavigation } from "@/components/dashboard/workspace-navigation";
import { WorkspaceDotField } from "@/components/dashboard/workspace-dot-field";
import { ThemeToggle } from "@/components/theme-toggle";
import { DiscordIdInspector } from "@/components/dashboard/discord-id-inspector";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  const [isProfilOpen, setIsProfilOpen] = useState(false);
  const closeSidebar = React.useCallback(() => setIsSidebarOpen(false), []);
  const pathname = usePathname();
  const isAdminRoute = pathname === "/dashboard/admin" || pathname.startsWith("/dashboard/admin/");
  const { language } = useLanguage();
  const guildMatch = pathname.match(/\/dashboard\/guild\/([^\/]+)/);
  const currentGuildId = guildMatch ? guildMatch[1] : null;
  const { data: session, status } = useSession();
  const sessionUserId = (session?.user as any)?.id as string | undefined;
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [globalNotification, setGlobalNotification] = useState<string | null>(null);
  const [pendingSupportRequests, setPendingSupportRequests] = useState(0);
  const [sidebarGuild, setSidebarGuild] = useState<{ name: string; icon: string | null } | null>(null);
  const [moduleStates, setModuleStates] = useState<Record<string, boolean>>({});
  const [dashboardAiAllowed, setDashboardAiAllowed] = useState(false);
  const [supportOperationsAllowed, setSupportOperationsAllowed] = useState(false);
  const moduleStateRevision = useRef(0);
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
      openLoginPanel();
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

  // The selected Discord server belongs in the navigation itself, as in the
  // reference: back to all servers first, then the server's real icon/name.
  React.useEffect(() => {
    if (!currentGuildId) {
      setSidebarGuild(null);
      return;
    }
    let active = true;
    api.getGuildDetails(currentGuildId)
      .then((guild: any) => {
        if (active) setSidebarGuild({ name: String(guild?.name || "Server"), icon: guild?.icon || null });
      })
      .catch(() => {
        if (active) setSidebarGuild({ name: "Server", icon: null });
      });
    return () => { active = false; };
  }, [currentGuildId]);

  React.useEffect(() => {
    if (!currentGuildId) {
      setDashboardAiAllowed(false);
      return;
    }
    let active = true;
    api.getDashboardAiAccess(currentGuildId)
      .then((data) => { if (active) setDashboardAiAllowed(Boolean(data.allowed)); })
      .catch(() => { if (active) setDashboardAiAllowed(false); });
    return () => { active = false; };
  }, [currentGuildId]);

  React.useEffect(() => {
    if (currentGuildId !== "1530378233579704370" || !sessionUserId) {
      setSupportOperationsAllowed(false);
      return;
    }
    let active = true;
    setSupportOperationsAllowed(false);
    api.getSupportOperationsAccess(currentGuildId)
      .then((data) => { if (active) setSupportOperationsAllowed(data.allowed === true); })
      .catch(() => { if (active) setSupportOperationsAllowed(false); });
    return () => { active = false; };
  }, [currentGuildId, sessionUserId]);

  // One bulk read drives every small status point. A local event keeps the
  // sidebar in sync immediately after the switch on the current page changes.
  React.useEffect(() => {
    if (!currentGuildId) {
      setModuleStates({});
      return;
    }
    let active = true;
    moduleStateRevision.current += 1;
    setModuleStates({});
    const requestedAt = moduleStateRevision.current;
    api.getGuildModuleStates(currentGuildId)
      .then((data) => {
        if (active && requestedAt === moduleStateRevision.current) {
          setModuleStates(data.modules || {});
        }
      })
      .catch(() => { if (active) setModuleStates({}); });

    const onState = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (String(detail?.guildId) !== String(currentGuildId) || !detail?.module) return;
      moduleStateRevision.current += 1;
      setModuleStates((states) => ({ ...states, [detail.module]: Boolean(detail.enabled) }));
    };
    window.addEventListener("guild-module-state", onState);
    return () => {
      active = false;
      window.removeEventListener("guild-module-state", onState);
    };
  }, [currentGuildId]);

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

  if (status === "loading" || status === "unauthenticated") {
    return (
      <div className="min-h-screen bg-[#0a0a0c] flex items-center justify-center">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <div className="h-12 w-12 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/20">
            <img src={BRAND_LOGO} alt="CloudTIX" className="h-full w-full rounded-xl object-cover" />
          </div>
          <p className="text-slate-400 font-bold tracking-widest uppercase text-xs">
            Anmeldung wird geprüft …
          </p>
        </div>
      </div>
    );
  }

  // Base sidebar items – will be filtered if we are inside a guild
  const allSidebarItems = currentGuildId
    ? [
        { name: "Übersicht", href: `/dashboard/guild/${currentGuildId}`, icon: LayoutDashboard },
        ...(currentGuildId === "1530378233579704370" && sessionUserId && supportOperationsAllowed
          ? [{ name: "Owner-Konsole", href: `/dashboard/guild/${currentGuildId}/owner-operations`, icon: ShieldCheck }]
          : []),
        ...(dashboardAiAllowed
          ? [{ name: "KI", href: `/dashboard/guild/${currentGuildId}/ai`, icon: Bot }]
          : []),
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
        { name: "Premium", href: "/dashboard/premium", icon: Gem, highlight: true },
        ...(isAdmin(session?.user?.id) || hasTeamRole
            ? [{ name: "Admin Panel", href: "/dashboard/admin", icon: Shield }]
            : []),
      ];

  // Keep every CloudTIX feature, but place the primary destinations above
  // the sections just like the reference navigation.
  const mainSidebarItems = currentGuildId
    ? [
        ...allSidebarItems.filter((item: any) => ["Übersicht", "Owner-Konsole", "KI", "Einstellungen"].includes(item.name)),
        ...allSidebarItems.filter((item: any) => item.name === "Hilfe"),
        ...allSidebarItems.filter((item: any) => Array.isArray(item.items)),
      ]
    : allSidebarItems;

  return (
    <div className={cn("user-dashboard-theme min-h-screen bg-[#0a0a0c] text-slate-200", isAdminRoute ? "cloudtix-admin-shell" : "cloudtix-workspace-shell", !isAdminRoute && navigationCollapsed && "is-nav-collapsed")}>
      <DiscordIdInspector />
      {/* Liquid Background Elements */}
      {/* Ein ruhiger Schein statt zwei pulsierender Flaechen. */}
      <div className="dashboard-background-decoration fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-15%] right-[-10%] h-[45%] w-[45%] rounded-full bg-indigo-600/[0.05] blur-[140px]" />
      </div>

      {!isAdminRoute && <WorkspaceDotField />}
      {!isAdminRoute && <WorkspaceNavigation
        items={mainSidebarItems}
        userId={sessionUserId || "guest"}
        collapsed={navigationCollapsed}
        onCollapsedChange={setNavigationCollapsed}
        guildId={currentGuildId}
        guild={sidebarGuild}
        moduleStates={moduleStates}
        mobileOpen={isSidebarOpen}
        onClose={closeSidebar}
        userName={session?.user?.name || "Dein Konto"}
        role={teamAccess?.is_owner ? "Owner" : teamAccess?.roles?.[0]?.label || "Mitglied"}
        premium={Boolean(premium?.aktiv)}
        supportInvite={supportInvite}
      />}

      {/* Main Content Area (unchanged) */}
      <div className={cn("relative z-10 flex min-h-screen flex-col bg-[#191a1f] lg:pl-[250px]", isAdminRoute ? "cloudtix-admin-frame" : "cloudtix-workspace-frame")}>
        {/* Top Navbar (unchanged) */}
        <header className="dashboard-topbar sticky top-2 z-30 mx-3 mb-4 mt-3 flex h-16 isolate items-center justify-between gap-2 rounded-[24px] border border-white/[.1] bg-[#090b12]/78 px-2.5 shadow-[0_22px_70px_rgba(0,0,0,.32)] backdrop-blur-3xl lg:top-4 lg:mx-6 lg:mb-6 lg:mt-4 lg:h-[72px] lg:rounded-[28px] lg:px-4">
          <div className="dashboard-header-decoration pointer-events-none absolute inset-x-16 top-0 h-px bg-gradient-to-r from-transparent via-blue-300/35 to-transparent" />
          <div className="dashboard-header-decoration pointer-events-none absolute -top-20 right-28 h-40 w-64 rounded-full bg-blue-600/[.08] blur-3xl" />
          <button
            className="relative grid h-10 w-10 shrink-0 place-items-center rounded-2xl border border-white/[.08] bg-white/[.045] text-slate-400 transition hover:bg-white/[.09] hover:text-white lg:hidden"
            aria-label={isAdminRoute ? "Admin-Navigation öffnen" : "Navigation öffnen"}
            aria-controls={isAdminRoute ? "cloudtix-admin-navigation" : "cloudtix-workspace-navigation"}
            aria-expanded={isAdminRoute ? undefined : isSidebarOpen}
            onClick={() => isAdminRoute ? window.dispatchEvent(new Event("cloudtix-admin-navigation-toggle")) : setIsSidebarOpen(true)}
          >
            <Menu className="h-6 w-6" />
          </button>

          {isAdminRoute ? <span className="cloudtix-admin-top-label"><Shield size={15} />Administration</span> : <Link href={currentGuildId ? `/dashboard/guild/${currentGuildId}` : "/dashboard"} className="cloudtix-workspace-top-label">{currentGuildId ? sidebarGuild?.name || "Serververwaltung" : "Dein Workspace"}</Link>}
          {!currentGuildId && <GlobalSearch />}

          <div className="relative ml-auto flex items-center gap-1.5 lg:gap-2">
            <div className="relative" ref={bellRef}>
              <button 
                onClick={() => setIsNotificationsOpen(!isNotificationsOpen)}
                className={cn(
                  "relative grid h-10 w-10 place-items-center rounded-2xl border transition-all",
                  isNotificationsOpen
                    ? "border-blue-400/25 bg-blue-500/12 text-blue-300"
                    : "border-white/[.08] bg-white/[.045] text-slate-400 hover:bg-white/[.09] hover:text-white"
                )}
                aria-label="Benachrichtigungen"
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
                className="rounded-[24px] border border-white/[.1] bg-[#090b12]/92 shadow-[0_24px_70px_rgba(0,0,0,.6)] backdrop-blur-3xl animate-in fade-in zoom-in-95 duration-200 origin-top-right"
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
            {/* Sprachumschalter — direkt neben dem Profil. Der Import
                stand schon lange hier, gerendert wurde er nie: im
                Dashboard gab es also keine Möglichkeit, die Sprache zu
                wechseln, obwohl der Umschalter und das Wörterbuch da
                sind. Auf schmalen Bildschirmen zeigt der Knopf nur die
                Flagge, damit Glocke, Profil und Suche Platz behalten. */}
            <LanguageSwitcher />
            <ThemeToggle embedded />

            {/* Profil Dropdown (unchanged) */}
            <div className="relative" ref={profileRef}>
              <button
                onClick={() => setIsProfilOpen(!isProfilOpen)}
                className={cn(
                  "flex h-10 items-center gap-2 rounded-2xl border px-1.5 pr-2.5 transition-all group",
                  isProfilOpen
                    ? "border-blue-400/25 bg-blue-500/10"
                    : "border-white/[.08] bg-white/[.045] hover:bg-white/[.09]"
                )}
                aria-label="Kontomenü"
              >
                <div className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-xl border border-blue-400/20 bg-blue-500/10 ring-1 ring-transparent transition-all group-hover:ring-blue-400/20">
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
                className="rounded-[24px] border border-white/[.1] bg-[#090b12]/92 shadow-[0_24px_70px_rgba(0,0,0,.6)] backdrop-blur-3xl animate-in fade-in zoom-in-95 duration-200 origin-top-right"
              >
                <div className="overflow-y-auto p-2">
                    <div className="px-4 py-3 border-b border-white/5 mb-2">
                      <p className="text-[9px] font-black text-slate-500 uppercase tracking-[0.2em] mb-1">Angemeldet als</p>
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
                      Abmelden
                    </button>
                </div>
              </PopoverLayer>
            </div>
          </div>
        </header>

        {/* Content Area */}
        <main className={cn("flex-1 p-3 sm:p-6 lg:p-10 animate-in fade-in duration-700 relative z-10", isAdminRoute ? "cloudtix-admin-main" : "cloudtix-workspace-main")}>
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
