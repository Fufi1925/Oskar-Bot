/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
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
import { useLanguage } from "@/lib/i18n/LanguageContext";
import {
  LayoutDashboard, Server, ShieldCheck, Ticket, BarChart4, FileText, Settings,
  Menu, X, Bell, User, Search, ChevronRight, Star, Sparkles, LogOut,
  Lock, PenLine, Gem, Pin, Moon, Calculator, Youtube, Cake,
  LifeBuoy, ChevronDown, Bot, Shield, UserCheck, Badge
} from "lucide-react";
import { useSession, signIn, signOut } from "next-auth/react";
import { cn, isAdmin } from "@/lib/utils";
import { api } from "@/lib/api";
import { AdminConfig } from "@/types/api";
import { SUPPORT_INVITE } from "@/lib/legal";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isProfilOpen, setIsProfilOpen] = useState(false);
  const pathname = usePathname();
  const { data: session, status } = useSession();
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [globalNotification, setGlobalNotification] = useState<string | null>(null);
  // Driven by the maintenance_mode config plus the maintenance_banner feature flag.
  const [maintenance, setMaintenance] = useState(false);
  // True when the user holds a dashboard team role, which unlocks the admin panel.
  const [hasTeamRole, setHasTeamRole] = useState(false);
  // Full team access info, used for the role badge in the sidebar footer.
  const [teamAccess, setTeamAccess] = useState<{
    is_owner: boolean;
    roles: Array<{ key: string; label: string; color: string; rank: number }>;
  } | null>(null);
  // Support link comes from the bot settings so it is configurable.
  // The initial value is the shared default, not a second hard-coded
  // copy -- it is what shows for the moment before the fetch lands.
  const [supportInvite, setSupportInvite] = useState(SUPPORT_INVITE);
  
  const bellRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (bellRef.current && !bellRef.current.contains(target)) {
        setIsNotificationsOpen(false);
      }
      if (profileRef.current && !profileRef.current.contains(target)) {
        setIsProfilOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Auto-close sidebar on mobile when navigating
  React.useEffect(() => {
    setIsSidebarOpen(false);
    setIsProfilOpen(false);
  }, [pathname]);

  React.useEffect(() => {
    if (status === "unauthenticated") {
      signIn("discord");
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
  const proximity = useProximity({ radius: 90, smoothing: 130 });

  if (status === "loading" || status === "unauthenticated") {
    return (
      <div className="min-h-screen bg-[#0b1f3a] flex items-center justify-center">
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

  const match = pathname.match(/\/dashboard\/guild\/([^\/]+)/);
  const currentGuildId = match ? match[1] : null;

  // Base sidebar items – will be filtered if we are inside a guild
  const allSidebarItems = currentGuildId
    ? [
        { name: "Übersicht", href: `/dashboard/guild/${currentGuildId}`, icon: LayoutDashboard },
        {
          // Same grouping as the tab bar. Two navigations that disagree
          // about where something lives is worse than one.
          name: "Schutz",
          items: [
            { name: "Anti-Nuke", href: `/dashboard/guild/${currentGuildId}/antinuke`, icon: ShieldCheck },
            { name: "Automod", href: `/dashboard/guild/${currentGuildId}/automod`, icon: ShieldCheck },
            { name: "Verifizierung", href: `/dashboard/guild/${currentGuildId}/verification`, icon: User },
            { name: "Notfall", href: `/dashboard/guild/${currentGuildId}/emergency`, icon: Shield },
            { name: "Jail", href: `/dashboard/guild/${currentGuildId}/jail`, icon: Lock },
            { name: "Nachtmodus", href: `/dashboard/guild/${currentGuildId}/nightmode`, icon: Moon },
          ],
        },
        {
          name: "Mitglieder",
          items: [
            { name: "Begrüßung", href: `/dashboard/guild/${currentGuildId}/welcome`, icon: Bell },
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
            { name: "Anonymer Chat (Beta)", href: `/dashboard/guild/${currentGuildId}/anonchat`, icon: Lock },
          ],
        },
        {
          name: "Sprache",
          items: [
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
          name: "Verwaltung",
          items: [
            { name: "Logs", href: `/dashboard/guild/${currentGuildId}/logging`, icon: LayoutDashboard },
            { name: "Server-Werkzeuge", href: `/dashboard/guild/${currentGuildId}/admin-dashboard`, icon: Shield },
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
    <div className="min-h-screen bg-[#071527] text-slate-200">
      {/* Liquid Background Elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-500/5 blur-[120px] rounded-full animate-pulse" />
        <div className="absolute bottom-[10%] left-[-5%] w-[30%] h-[30%] bg-indigo-500/5 blur-[100px] rounded-full animate-pulse [animation-delay:2s]" />
      </div>

      {/* Mobile Sidebar Overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar - now using flex column */}
      <aside
        className={cn(
          "fixed left-4 top-4 bottom-4 z-50 w-64 transform transition-all duration-500 ease-in-out lg:translate-x-0 glass border border-white/10 rounded-[2.5rem] shadow-2xl shadow-black/40 overflow-hidden flex flex-col",
          isSidebarOpen ? "translate-x-0" : "-translate-x-[110%]"
        )}
      >
        {/* Header */}
        <div className="flex h-16 items-center px-6 mt-4 flex-shrink-0">
          <div className="flex items-center gap-3 group">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-800 flex items-center justify-center shadow-lg shadow-blue-500/20 group-hover:scale-110 transition-transform border border-white/10">
              <Bot className="h-5 w-5 text-white" />
            </div>
            <div className="flex flex-col">
              <h1 className="text-lg font-bold tracking-tight text-white font-outfit leading-none">
                {process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot"}
              </h1>
              <span className="text-[9px] font-black uppercase tracking-[0.2em] text-blue-500/80 mt-1">
                Dashboard
              </span>
            </div>
          </div>
          <button
            className="ml-auto p-2 lg:hidden text-slate-400 hover:text-white"
            onClick={() => setIsSidebarOpen(false)}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Navigation */}
        <nav
          className="mt-8 px-4 space-y-6 overflow-y-auto flex-1 no-scrollbar relative z-10 pb-3"
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
                <div key={item.name} className="space-y-2">
                  <p className="px-4 text-[10px] font-black uppercase tracking-[0.3em] text-slate-600 mb-3">
                    {item.name}
                  </p>
                  <div className="space-y-1">
                    {item.items.map((subItem: any) => {
                      const isActive = pathname === subItem.href;
                      const subIndex = nextIndex();
                      return (
                        <Link
                          key={subItem.name}
                          href={subItem.href}
                          {...proximity.itemProps(subIndex)}
                          className={cn(
                            "prox-row prox-row-sm",
                            "flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-300 group text-[13px] font-bold",
                            isActive
                              ? "bg-blue-500/10 text-blue-500 border border-blue-500/20 shadow-[0_0_20px_rgba(59,130,246,0.1)]"
                              : "text-slate-400 hover:bg-white/[0.03] hover:text-slate-200"
                          )}
                        >
                          <span className="prox-marker" aria-hidden />
                          <subItem.icon
                            className={cn(
                              "h-4 w-4 transition-all duration-300",
                              isActive
                                ? "text-blue-500 scale-110"
                                : "text-slate-600 group-hover:text-slate-400"
                            )}
                          />
                          {subItem.name}
                          {isActive && (
                            <div className="ml-auto w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse shadow-[0_0_10px_rgba(59,130,246,0.5)]" />
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
            const isPremium = item.href === "/dashboard/premium";
            // Admin gets its own treatment: a steel plate rather than the
            // flat blue, but deliberately without Premium's pulse — this
            // one is clicked daily and a permanent animation would wear
            // thin. Keyed off the href, not the label, which is
            // translated.
            const isAdmin = item.href === "/dashboard/admin";
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
                className={cn(
                  "prox-row",
                  "flex items-center gap-4 px-4 py-3 rounded-2xl transition-all duration-300 group text-[14px] font-bold",
                  isPremium
                    ? cn(
                        "premium-link border border-amber-400/30",
                        isActive
                          ? "bg-amber-400/[0.14] text-amber-200"
                          : "bg-amber-400/[0.06] text-amber-200/90 hover:bg-amber-400/[0.12] hover:text-amber-100"
                      )
                    : isAdmin
                    ? cn(
                        "admin-link",
                        isActive ? "text-indigo-100" : "text-indigo-200/90 hover:text-white"
                      )
                    : isActive
                    ? "bg-blue-500/10 text-blue-500 border border-blue-500/20 shadow-[0_0_20px_rgba(59,130,246,0.1)]"
                    : "text-slate-400 hover:bg-white/[0.03] hover:text-slate-200"
                )}
              >
                {/* The leading line from LineSidebar. Decoration, so it
                    is hidden from screen readers -- the label already
                    says everything.

                    The original also numbers each row 01, 02, 03. Those
                    are gone: they are the loudest thing in a sidebar
                    that is meant to be read by label, and nobody
                    navigates by ordinal. The line alone carries the
                    effect. */}
                <span className="prox-marker" aria-hidden />
                {isAdmin ? (
                  // A filled tile rather than a bare glyph: that is what
                  // makes this row read as a destination at a glance.
                  <span className="admin-badge shrink-0">
                    <item.icon className="h-4 w-4 text-indigo-200" />
                  </span>
                ) : (
                  <item.icon
                    className={cn(
                      "h-5 w-5 transition-all duration-300",
                      isPremium
                        ? cn("text-amber-300 drop-shadow-[0_0_6px_rgba(250,166,26,0.55)]", isActive && "scale-110")
                        : isActive
                        ? "text-blue-500 scale-110"
                        : "text-slate-600 group-hover:text-slate-400"
                    )}
                  />
                )}
                {item.name}
                {isActive ? (
                  <ChevronRight
                    className={cn(
                      "ml-auto h-4 w-4",
                      isPremium ? "text-amber-300" : isAdmin ? "text-indigo-300" : "text-blue-500"
                    )}
                  />
                ) : (
                  <ChevronRight className="ml-auto h-4 w-4 opacity-0 group-hover:opacity-30 transition-opacity" />
                )}
              </Link>
            );
            });
          })()}
        </nav>

        {/* Fixed "Back to Server" link (only shown inside a guild) */}
        {backLinkItem && (
          <div className="px-4 py-2 flex-shrink-0">
            <div className="h-px bg-white/5 w-3/4 mx-auto rounded-full mb-2" />
            <Link
              href={backLinkItem.href || "/dashboard/guilds"}
              className={cn(
                "flex items-center gap-4 px-4 py-3 rounded-2xl transition-all duration-300 group text-[14px] font-bold",
                pathname === backLinkItem.href
                  ? "bg-blue-500/10 text-blue-500 border border-blue-500/20 shadow-[0_0_20px_rgba(59,130,246,0.1)]"
                  : "text-slate-400 hover:bg-white/[0.03] hover:text-slate-200"
              )}
            >
              <BackLinkIcon
                className={cn(
                  "h-5 w-5 transition-all duration-300",
                  pathname === backLinkItem.href
                    ? "text-blue-500 scale-110"
                    : "text-slate-600 group-hover:text-slate-400"
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
        <div className="flex-shrink-0 p-4 border-t border-white/5 glass-blue bg-blue-500/[0.02]">
          <div className="flex items-center gap-3 p-2 bg-white/[0.02] rounded-2xl border border-white/[0.05]">
            <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center ring-1 ring-white/10 overflow-hidden border border-blue-500/20">
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
          </div>
        </div>
      </aside>

      {/* Main Content Area (unchanged) */}
      <div className="lg:pl-72 flex flex-col min-h-screen relative z-10">
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
                {globalNotification && (
                  <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-blue-500 border-2 border-[#071527] shadow-[0_0_10px_rgba(59,130,246,0.5)]"></span>
                )}
              </button>

              {isNotificationsOpen && (
                <div className="absolute right-0 mt-3 w-80 bg-[#071a33]/90 backdrop-blur-3xl border border-white/5 rounded-[24px] shadow-[0_20px_50px_rgba(0,0,0,0.5)] p-4 z-20 animate-in fade-in zoom-in-95 duration-300 origin-top-right">
                    <div className="flex items-center justify-between mb-4 border-b border-white/5 pb-2">
                      <p className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Broadcast Metrics</p>
                      <button 
                        onClick={() => setGlobalNotification(null)}
                        className="text-[10px] font-bold text-blue-500/60 hover:text-blue-500 transition-colors uppercase"
                      >
                        Clear
                      </button>
                    </div>
                    
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
                    ) : (
                      <div className="py-8 flex flex-col items-center justify-center text-center">
                        <div className="h-10 w-10 rounded-full bg-slate-800 flex items-center justify-center mb-3">
                          <Bell className="h-5 w-5 text-slate-600" />
                        </div>
                        <p className="text-xs font-bold text-slate-500">No active broadcasts</p>
                        <p className="text-[10px] font-medium text-slate-600 mt-1 uppercase tracking-widest">Everything is operating normally</p>
                      </div>
                    )}
                  </div>
              )}
            </div>
            <div className="h-8 w-[1px] bg-white/5 hidden sm:block"></div>

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
                        : teamAccess?.roles?.[0]?.color ?? "#64748b",
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

              {isProfilOpen && (
                <div className="absolute right-0 mt-3 w-56 bg-[#071a33]/90 backdrop-blur-3xl border border-white/5 rounded-[24px] shadow-[0_20px_50px_rgba(0,0,0,0.5)] p-2 z-20 animate-in fade-in zoom-in-95 duration-300 origin-top-right">
                    <div className="px-4 py-3 border-b border-white/5 mb-2">
                      <p className="text-[9px] font-black text-slate-500 uppercase tracking-[0.2em] mb-1">Authenticated As</p>
                      <p className="text-sm font-bold text-white truncate">{session?.user?.name || "Administrator"}</p>
                      {(teamAccess?.is_owner || (teamAccess?.roles?.length ?? 0) > 0) && (
                        <div className="flex flex-wrap gap-1 mt-2">
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
              )}
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