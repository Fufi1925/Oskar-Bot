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
  LayoutDashboard, ScrollText, Server, ShieldCheck, ShieldAlert, Ticket, BarChart4, FileText, Settings,
  Menu, X, Bell, User, Search, ChevronRight, Star, Sparkles, LogOut,
  Lock, PenLine, Gem, Pin, Moon, Calculator, Youtube, Cake,
  LifeBuoy, ChevronDown, Bot, Shield, UserCheck, Badge, Gauge, Headphones,
  Music, Upload, Users, UserCog
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
            { name: "Honeypot", href: `/dashboard/guild/${currentGuildId}/honeypot`, icon: ShieldAlert },
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
            { name: "Speedrun (Beta)", href: `/dashboard/guild/${currentGuildId}/speedrun`, icon: Gauge },
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
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar - now using flex column */}
      <aside
        className={cn(
          // Sitzt am Rand statt zu schweben: eine 2.5rem-Rundung mit
          // Schlagschatten sieht aus wie eine Karte auf einer Karte.
          "fixed left-0 top-0 bottom-0 z-50 w-64 transform transition-transform duration-300 lg:translate-x-0",
          "border-r border-slate-800 bg-[#0c0c0f] overflow-hidden flex flex-col",
          isSidebarOpen ? "translate-x-0" : "-translate-x-[110%]"
        )}
      >
        {/* Header */}
        <div className="flex h-16 items-center px-6 mt-4 flex-shrink-0">
          <div className="flex items-center gap-3 group">
            <Bot className="h-5 w-5 text-indigo-400" />
            <div className="flex flex-col">
              <h1 className="text-[16px] font-bold tracking-tight text-white leading-none">
                {process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot"}
              </h1>
              <span className="mt-1 text-[11px] text-slate-500">Dashboard</span>
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
          // pr-10 rather than px-4 on both sides: the rows slide right
          // by up to 37px, and a scroll container clips at its padding
          // box. With 16px of room they were cut off; 40px clears the
          // full travel with 3px to spare. 44px would be too much --
          // "Zurück zur Serverliste" starts wrapping. Worked out in
          // repro/prox_shift_budget.py.
          className="mt-8 pl-4 pr-10 space-y-6 overflow-y-auto flex-1 no-scrollbar relative z-10 pb-3"
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
                  <p className="px-3 text-[11px] font-semibold text-slate-600 mb-1.5">
                    {item.name}
                  </p>
                  <div className="space-y-1">
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
                            "flex items-center gap-3 px-3 py-2 rounded-lg transition-colors group text-[13px]",
                            isActive
                              ? "bg-white/[0.06] text-white font-semibold"
                              : "text-slate-400 hover:bg-white/[0.03] hover:text-slate-200"
                          )}
                        >
                          <subItem.icon
                            className={cn(
                              "h-4 w-4 shrink-0 transition-colors",
                              isActive
                                ? "text-indigo-400"
                                : "text-slate-600 group-hover:text-slate-400"
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
            const isPremium = item.href === "/dashboard/premium";
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
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors group text-[14px]",
                  isPremium
                    ? isActive
                      ? "bg-amber-400/10 text-amber-200 font-semibold"
                      : "text-amber-300/80 hover:bg-amber-400/[0.07] hover:text-amber-200"
                    : isActive
                    ? "bg-white/[0.06] text-white font-semibold"
                    : "text-slate-400 hover:bg-white/[0.03] hover:text-slate-200"
                )}
              >
                {/* No leading line and no 01/02/03 gutter, both from the
                    original LineSidebar. The numbers were the loudest
                    thing in a sidebar that is read by label, and the
                    line was a second signal for what the movement
                    already says. The shift alone carries the effect. */}
                <item.icon
                  className={cn(
                    "h-[18px] w-[18px] shrink-0 transition-colors",
                    isPremium
                      ? "text-amber-400"
                      : isActive
                      ? "text-indigo-400"
                      : "text-slate-600 group-hover:text-slate-400"
                  )}
                />
                {/* Der Reiter heißt in der Navigation "Speedrun (Beta)".
                    Das Wort in Klammern mitzuschleppen macht die Zeile
                    lang und die Klammer laut; als kleines Zeichen sagt
                    es dasselbe und stört nicht beim Lesen. */}
                <span className="min-w-0 truncate">
                  {item.name.replace(" (Beta)", "")}
                </span>
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
          <div className="px-4 py-2 flex-shrink-0">
            <div className="h-px bg-white/5 w-3/4 mx-auto rounded-full mb-2" />
            <Link
              href={backLinkItem.href || "/dashboard/guilds"}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors group text-[14px]",
                pathname === backLinkItem.href
                  ? "bg-white/[0.06] text-white font-semibold"
                  : "text-slate-400 hover:bg-white/[0.03] hover:text-slate-200"
              )}
            >
              <BackLinkIcon
                className={cn(
                  "h-[18px] w-[18px] shrink-0 transition-colors",
                  pathname === backLinkItem.href
                    ? "text-indigo-400"
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
      <div className="lg:pl-64 flex flex-col min-h-screen relative z-10">
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
                  <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-blue-500 border-2 border-[#0a0a0c] shadow-[0_0_10px_rgba(59,130,246,0.5)]"></span>
                )}
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
              </PopoverLayer>
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
