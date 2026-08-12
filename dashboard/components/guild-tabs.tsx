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

/**
 * The tab bar above a guild's settings.
 *
 * It used to be 32 tabs in one flat scrolling row, in no order anybody
 * could name: Anti-Nuke next to Tickets next to Invites, Logging near
 * the end, Emergency between Birthdays and the Admin Dashboard. Finding
 * anything meant dragging sideways and reading every label.
 *
 * Now they are grouped by what they are for, the group you are in is
 * open by default, and there is a search box -- with 30-odd tabs,
 * typing three letters beats scrolling every time.
 *
 * Also fixed here: Tracking had a page but no tab at all, so the only
 * way in was to type the URL. And Birthdays is gone, along with the
 * feature.
 */

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/lib/i18n/LanguageContext";

/** Exactly what useLanguage() hands back, so the key union survives. */
type TranslateFn = ReturnType<typeof useLanguage>["t"];
import { cn } from "@/lib/utils";
import { useProximity } from "@/components/ui/proximity";
import {
  Activity,
  BarChart4,
  Music,
  Upload,
  UserCog,
  Badge,
  Bot,
  Calculator,
  ChevronDown,
  FileText,
  Gauge,
  Headphones,
  Gem,
  Gift,
  Hash,
  Layers,
  Link as LinkIcon,
  Link2,
  Lock,
  Mail,
  MessageSquare,
  Mic,
  Moon,
  PenLine,
  Pin,
  Search,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  SmilePlus,
  ClipboardList,
  DoorOpen,
  Sparkles,
  Sword,
  Ticket,
  UserCheck,
  Users,
  Volume2,
  X,
  Youtube,
  Zap,
} from "lucide-react";

interface Tab {
  name: string;
  slug: string;
  icon: any;
  /** Shown as a small badge. Only "beta" so far. */
  tag?: "beta";
  /** Extra words the search should match, for people who look for the
   *  English name or an older label. */
  also?: string[];
}

interface Group {
  name: string;
  icon: any;
  tabs: Tab[];
}

/**
 * The groups, in the order somebody sets a server up: protect it first,
 * then greet people, then the fun, then the plumbing.
 */
function buildGroups(t: TranslateFn): Group[] {
  return [
    {
      name: "Schutz",
      icon: Sword,
      tabs: [
        { name: "Anti-Nuke", slug: "antinuke", icon: Sword, also: ["nuke", "raid"] },
        { name: t("automod"), slug: "automod", icon: ShieldCheck, also: ["spam", "caps", "links", "automod"] },
        { name: "Verifizierung", slug: "verification", icon: Shield, also: ["verify", "captcha"] },
        { name: "Notfall", slug: "emergency", icon: ShieldAlert, also: ["lockdown", "emergency", "panik"] },
        { name: "Jail", slug: "jail", icon: Lock, also: ["isolation", "knast"] },
        { name: "Nachtmodus", slug: "nightmode", icon: Moon, also: ["nightmode", "schliessen"] },
      ],
    },
    {
      name: "Mitglieder",
      icon: SmilePlus,
      tabs: [
        { name: "Begrüßung", slug: "welcome", icon: SmilePlus, also: ["welcome", "willkommen"] },
        { name: "Abschied", slug: "leave", icon: DoorOpen, also: ["leave", "goodbye", "abschied", "tschuess", "verlassen"] },
        { name: "Beitritts-DM", slug: "joindm", icon: Mail, also: ["joindm", "dm"] },
        { name: "Auto-Rolle", slug: "autorole", icon: Bot, also: ["autorole"] },
        { name: "Reaktions-Rollen", slug: "reactionroles", icon: Activity, also: ["reactionroles", "reaction"] },
        { name: "Eigene Rollen", slug: "customroles", icon: Sparkles, also: ["customroles"] },
        { name: "Vanity-Rollen", slug: "vanityroles", icon: Link2, also: ["vanity", "status"] },
        { name: "Nickname", slug: "nickname", icon: Badge, also: ["nickname", "prefix", "suffix"] },
        { name: "Level-System", slug: "leveling", icon: BarChart4, also: ["leveling", "xp", "rang"] },
      ],
    },
    {
      name: "Aktivität",
      icon: Gift,
      tabs: [
        { name: "Giveaways", slug: "giveaways", icon: Gift, also: ["gewinnspiel", "giveaway"] },
        { name: "Counting", slug: "counting", icon: Calculator, also: ["zählen", "counting"] },
        { name: "Booster", slug: "booster", icon: Gem, also: ["boost", "nitro"] },
        { name: "Benachrichtigungen", slug: "notify", icon: Youtube, also: ["youtube", "notify", "live", "video"] },
        { name: "Auto-Reaktion", slug: "autoreact", icon: Zap, also: ["autoreact", "emoji"] },
        { name: "Autoresponder", slug: "autoresponder", icon: MessageSquare, also: ["autoresponder", "antwort"] },
        {
          name: "Anonymer Chat",
          slug: "anonchat",
          icon: Lock,
          tag: "beta",
          also: ["anonym", "anonchat"],
        },
      ],
    },
    {
      name: "Sprache",
      icon: Mic,
      tabs: [
        { name: "Join to Create", slug: "j2c", icon: Mic, also: ["j2c", "sprachkanal", "voice"] },
        { name: "Sprach-Rolle", slug: "invcrole", icon: Volume2, also: ["invcrole", "voice"] },
      ],
    },
    {
      name: "Werkzeuge",
      icon: Ticket,
      tabs: [
        { name: t("tickets"), slug: "tickets", icon: Ticket, also: ["ticket", "support"] },
        { name: "Bewerbungen", slug: "applications", icon: ClipboardList, also: ["bewerbung", "application", "apply", "team", "moderator"] },
        { name: "Eigene Nachricht", slug: "compose", icon: PenLine, also: ["compose", "embed"] },
        { name: "Sticky-Nachricht", slug: "sticky", icon: Pin, also: ["sticky"] },
        { name: "Einladungen", slug: "invites", icon: LinkIcon, also: ["invites", "einladung"] },
        { name: "Einladungs-Log", slug: "tracking", icon: Hash, also: ["tracking", "invite tracking"] },
        { name: "No Prefix", slug: "noprefix", icon: UserCheck, also: ["noprefix"] },
      ],
    },
    {
      // Dieselbe Gruppe wie in der Seitenleiste. Beide Navigationen
      // muessen dieselben Namen benutzen -- sonst heisst "Schutz"
      // an zwei Stellen etwas anderes.
      name: "Templates",
      icon: Sparkles,
      tabs: [
        {
          name: "Speedrun",
          slug: "speedrun",
          icon: Gauge,
          tag: "beta",
          also: ["speedrun", "setup", "vorlage", "template", "aufsetzen"],
        },
        {
          name: "Vorlage hochladen",
          slug: "template-upload",
          icon: Upload,
          tag: "beta",
          also: [
            "template", "vorlage", "upload", "hochladen", "scan", "teilen",
            "export", "sichern",
          ],
        },
        {
          name: "Community-Vorlagen",
          slug: "templates",
          icon: Sparkles,
          tag: "beta",
          also: [
            "template", "templates", "vorlage", "vorlagen", "community",
            "import", "uebernehmen", "aufsetzen",
          ],
        },
      ],
    },
    {
      name: "Verwaltung",
      icon: Settings,
      tabs: [
        // The tab was called "Protokollierung" until now, so both
        // spellings stay searchable -- renaming it must not hide it
        // from anybody who learned the old name.
        {
          name: "Teamliste",
          slug: "teamlist",
          icon: Users,
          also: [
            "team", "teamliste", "staff", "mitarbeiter", "rollen", "liste",
            "moderatoren", "supporter", "wer ist wer",
          ],
        },
        {
          name: "Team-Update",
          slug: "teamupdate",
          icon: UserCog,
          tag: "beta",
          also: [
            "team", "uprank", "downrank", "teamkick", "teamwarn",
            "teamanfang", "befoerderung", "beförderung", "rang",
            "rueckstufung", "rückstufung", "verwarnung", "rollen",
            "aufnahme", "unterschrift",
          ],
        },
        { name: "Logs", slug: "logging", icon: FileText,
          also: ["logging", "logs", "audit", "protokoll", "protokollierung"] },
        { name: "Server-Werkzeuge", slug: "admin-dashboard", icon: Shield, also: ["admin", "scan", "audit"] },
        {
          name: "Musik",
          slug: "music",
          icon: Music,
          also: [
            "musik", "music", "playlist", "song", "lied", "player", "247",
            "24/7", "dauerbetrieb", "lautstaerke", "lautstärke", "volume",
            "sprachkanal", "voice",
          ],
        },
        {
          name: "Support-Warteraum",
          slug: "supportqueue",
          icon: Headphones,
          tag: "beta",
          also: [
            "support", "warteraum", "warteschlange", "queue", "voice",
            "sprachkanal", "ansage", "wartemusik",
          ],
        },
        { name: "Einstellungen", slug: "settings", icon: Settings, also: ["settings", "prefix"] },
      ],
    },
  ];
}

/**
 * One wrapping row of tabs, with the proximity effect.
 *
 * A row of its own rather than one shared instance across all of them:
 * the hook measures against a single container, and these rows are in
 * separate collapsible groups. Sharing one would measure every tab
 * against whichever group happened to register first.
 */
function TabRow({
  tabs,
  guildId,
  current,
  className,
}: {
  tabs: Tab[];
  guildId: string;
  current: string;
  className?: string;
}) {
  // Your LineSidebar settings: radius 85, smoothing 120, smooth
  // falloff, no index and no marker. `axis: "both"` is the one
  // addition -- these tabs wrap, and every tab in a line shares an
  // offsetTop, so vertical distance alone would light a whole line.
  const proximity = useProximity({
    radius: 85,
    smoothing: 120,
    falloff: "smooth",
    axis: "both",
    activeIndex: tabs.findIndex((tab) => tab.slug === current),
  });

  const { setCount } = proximity;
  React.useEffect(() => {
    setCount(tabs.length);
  }, [tabs.length, setCount]);

  return (
    // `relative` so this box is the buttons' offsetParent, which is what
    // the hook measures them against.
    <div className={cn("flex gap-2 flex-wrap relative", className)} {...proximity.containerProps}>
      {tabs.map((tab, index) => (
        <TabLink
          key={tab.slug}
          tab={tab}
          guildId={guildId}
          active={tab.slug === current}
          itemProps={proximity.itemProps(index)}
        />
      ))}
    </div>
  );
}

function TabLink({
  tab,
  guildId,
  active,
  itemProps,
}: {
  tab: Tab;
  guildId: string;
  active: boolean;
  itemProps?: { ref: (el: HTMLElement | null) => void };
}) {
  return (
    <Link
      href={`/dashboard/guild/${guildId}/${tab.slug}`}
      className="shrink-0 prox-tab"
      {...itemProps}
    >
      <div
        className={cn(
          "flex items-center gap-2 px-4 py-3 sm:py-2.5 rounded-xl text-[11px] font-black uppercase tracking-wider transition-colors whitespace-nowrap border",
          active
            ? "bg-primary text-white border-white/10 shadow-lg shadow-primary/25"
            : "text-slate-400 bg-slate-900/40 border-slate-800/40 hover:bg-slate-800/60 hover:text-white hover:border-slate-700/50"
        )}
      >
        <tab.icon className={cn("h-3.5 w-3.5", active ? "" : "opacity-50")} />
        {tab.name}
        {tab.tag === "beta" && (
          <span
            title="Beta: neu und noch nicht lange im Einsatz. Kann sich noch ändern."
            className={cn(
              "px-1.5 py-0.5 rounded text-[9px] font-black tracking-widest",
              active
                ? "bg-white/20 text-white"
                : "bg-amber-400/15 text-amber-300/90"
            )}
          >
            BETA
          </span>
        )}
      </div>
    </Link>
  );
}

export function GuildTabs({ guildId }: { guildId: string }) {
  const pathname = usePathname();
  const { t } = useLanguage();
  const groups = React.useMemo(() => buildGroups(t), [t]);

  const [query, setQuery] = React.useState("");
  const [openGroup, setOpenGroup] = React.useState<string | null>(null);

  const overviewHref = `/dashboard/guild/${guildId}`;
  const current = pathname.startsWith(overviewHref)
    ? pathname.slice(overviewHref.length).replace(/^\//, "")
    : "";

  // Whichever group holds the open tab starts expanded, so landing on a
  // page never leaves you looking at a collapsed bar wondering where
  // you are.
  const activeGroup = React.useMemo(() => {
    for (const group of groups) {
      if (group.tabs.some((tab) => tab.slug === current)) return group.name;
    }
    return null;
  }, [groups, current]);

  React.useEffect(() => {
    setOpenGroup(activeGroup);
  }, [activeGroup]);

  const needle = query.trim().toLowerCase();
  const matches = React.useMemo(() => {
    if (!needle) return null;
    const found: Tab[] = [];
    for (const group of groups) {
      for (const tab of group.tabs) {
        const haystack = [tab.name, tab.slug, ...(tab.also || [])]
          .join(" ")
          .toLowerCase();
        if (haystack.includes(needle)) found.push(tab);
      }
    }
    return found;
  }, [groups, needle]);

  return (
    <div className="mb-8 space-y-3">
      {/* ── Overview + search ─────────────────────────── */}
      <div className="flex gap-2 flex-wrap items-center">
        <Link href={overviewHref} className="shrink-0">
          <div
            className={cn(
              "flex items-center gap-2 px-5 py-3 sm:py-2.5 rounded-xl text-[11px] font-black uppercase tracking-wider transition-colors border",
              current === ""
                ? "bg-primary text-white border-white/10 shadow-lg shadow-primary/25"
                : "text-slate-400 bg-slate-900/40 border-slate-800/40 hover:bg-slate-800/60 hover:text-white"
            )}
          >
            <Layers className="h-3.5 w-3.5" />
            Übersicht
          </div>
        </Link>

        <label className="relative w-full sm:flex-1 sm:w-auto sm:min-w-[200px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Einstellung suchen…"
            className="w-full bg-[#131318]/60 border border-slate-800/40 rounded-xl pl-10 pr-9 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
              title="Suche leeren"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </label>
      </div>

      {/* ── Search results ────────────────────────────── */}
      {matches !== null ? (
        <div className="bg-[#131318]/40 border border-slate-800/40 rounded-[20px] p-3 border-glow-card glow-r-20">
          {matches.length === 0 ? (
            <p className="text-sm text-slate-500 py-4 text-center">
              Nichts gefunden für &bdquo;{query}&ldquo;.
            </p>
          ) : (
            <TabRow tabs={matches} guildId={guildId} current={current} />
          )}
        </div>
      ) : (
        /* ── Groups ──────────────────────────────────── */
        <div className="space-y-2">
          {groups.map((group) => {
            const open = openGroup === group.name;
            const holdsActive = group.tabs.some((tab) => tab.slug === current);
            return (
              <div
                key={group.name}
                className={cn(
                  "rounded-[20px] border transition-colors",
                  holdsActive
                    ? "bg-[#131318]/60 border-primary/25"
                    : "bg-[#131318]/40 border-slate-800/40"
                )}
              >
                <button
                  onClick={() => setOpenGroup(open ? null : group.name)}
                  className="w-full flex items-center gap-3 px-4 sm:px-5 py-3.5 sm:py-3"
                >
                  <group.icon
                    className={cn(
                      "h-4 w-4 shrink-0",
                      holdsActive ? "text-primary" : "text-slate-500"
                    )}
                  />
                  <span
                    className={cn(
                      "text-[11px] font-black uppercase tracking-widest",
                      holdsActive ? "text-white" : "text-slate-400"
                    )}
                  >
                    {group.name}
                  </span>
                  <span className="text-[10px] font-bold text-slate-600">
                    {group.tabs.length}
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 text-slate-600 ml-auto shrink-0 transition-transform",
                      open && "rotate-180"
                    )}
                  />
                </button>

                {open && (
                  <TabRow
                    tabs={group.tabs}
                    guildId={guildId}
                    current={current}
                    className="px-3 pb-3"
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
