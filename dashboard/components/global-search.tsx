"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  Activity, BarChart4, Bot, ClipboardList, Command, Database, FileText, Hash,
  Layers, Link2, Lock, Mail, Mic, Search, Settings, Shield, ShieldCheck,
  SmilePlus, Sparkles, Ticket, UserCheck, Users, Volume2, Wrench, Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SearchTarget {
  label: string;
  href: string;
  icon: any;
  group: string;
  keywords: string;
  /** Needs a guild in the URL to be reachable. */
  guildScoped?: boolean;
}

// Everything the dashboard can navigate to. `{g}` is replaced with the
// current guild id.
const TARGETS: SearchTarget[] = [
  { label: "Dashboard", href: "/dashboard", icon: Layers, group: "General", keywords: "home start overview" },
  { label: "Servers", href: "/dashboard/guilds", icon: Bot, group: "General", keywords: "guilds server list" },
  { label: "Admin Panel", href: "/dashboard/admin", icon: Shield, group: "General", keywords: "admin control staff" },

  { label: "Server Overview", href: "/dashboard/guild/{g}", icon: Layers, group: "Server", keywords: "stats info", guildScoped: true },
  { label: "Anti-Nuke", href: "/dashboard/guild/{g}/antinuke", icon: ShieldCheck, group: "Security", keywords: "protection raid nuke whitelist", guildScoped: true },
  { label: "Automod", href: "/dashboard/guild/{g}/automod", icon: ShieldCheck, group: "Security", keywords: "spam caps links invites filter", guildScoped: true },
  { label: "Verification", href: "/dashboard/guild/{g}/verification", icon: UserCheck, group: "Security", keywords: "captcha verify gate", guildScoped: true },

  { label: "Welcome", href: "/dashboard/guild/{g}/welcome", icon: SmilePlus, group: "Engagement", keywords: "greet join message", guildScoped: true },
  { label: "Join DM", href: "/dashboard/guild/{g}/joindm", icon: Mail, group: "Engagement", keywords: "direct message private", guildScoped: true },
  { label: "Leveling", href: "/dashboard/guild/{g}/leveling", icon: BarChart4, group: "Engagement", keywords: "xp rank level rewards", guildScoped: true },
  { label: "Leaderboard", href: "/dashboard/guild/{g}/leveling/leaderboard", icon: BarChart4, group: "Engagement", keywords: "top ranking xp", guildScoped: true },
  { label: "Invites", href: "/dashboard/guild/{g}/invites", icon: Link2, group: "Engagement", keywords: "invite tracking leaderboard", guildScoped: true },
  { label: "Invite Tracking", href: "/dashboard/guild/{g}/tracking", icon: Link2, group: "Engagement", keywords: "track invites log", guildScoped: true },

  { label: "Auto Role", href: "/dashboard/guild/{g}/autorole", icon: Bot, group: "Roles", keywords: "automatic role join bots humans", guildScoped: true },
  { label: "Reaction Roles", href: "/dashboard/guild/{g}/reactionroles", icon: Zap, group: "Roles", keywords: "reaction emoji role menu", guildScoped: true },
  { label: "Vanity Roles", href: "/dashboard/guild/{g}/vanityroles", icon: Sparkles, group: "Roles", keywords: "status vanity url role", guildScoped: true },
  { label: "Custom Roles", href: "/dashboard/guild/{g}/customroles", icon: Sparkles, group: "Roles", keywords: "booster personal role", guildScoped: true },
  { label: "Voice Role", href: "/dashboard/guild/{g}/invcrole", icon: Volume2, group: "Roles", keywords: "voice channel role invc", guildScoped: true },

  { label: "Tickets", href: "/dashboard/guild/{g}/tickets", icon: Ticket, group: "Support", keywords: "support ticket panel", guildScoped: true },
  { label: "Join to Create", href: "/dashboard/guild/{g}/j2c", icon: Mic, group: "Voice", keywords: "temporary voice channel j2c", guildScoped: true },
  { label: "Auto Reactions", href: "/dashboard/guild/{g}/autoreact", icon: Zap, group: "Utility", keywords: "auto react emoji trigger", guildScoped: true },
  { label: "No Prefix", href: "/dashboard/guild/{g}/noprefix", icon: Command, group: "Utility", keywords: "no prefix users roles", guildScoped: true },
  { label: "Nicknames", href: "/dashboard/guild/{g}/nickname", icon: UserCheck, group: "Utility", keywords: "nickname prefix suffix", guildScoped: true },
  { label: "Logging", href: "/dashboard/guild/{g}/logging", icon: FileText, group: "Utility", keywords: "log events audit channel", guildScoped: true },
  { label: "Server Settings", href: "/dashboard/guild/{g}/settings", icon: Settings, group: "Utility", keywords: "prefix settings config", guildScoped: true },
];

// Tabs inside the admin panel. They are not real routes, so they carry a
// hash the admin page reads on load.
const ADMIN_TABS: SearchTarget[] = [
  { label: "Warnings", href: "/dashboard/admin#warnings", icon: Shield, group: "Admin", keywords: "warn punishment history" },
  { label: "Reports", href: "/dashboard/admin#reports", icon: BarChart4, group: "Admin", keywords: "analytics security score risk" },
  { label: "Audit Log", href: "/dashboard/admin#audit", icon: FileText, group: "Admin", keywords: "audit history actions timeline" },
  { label: "Approvals", href: "/dashboard/admin#approvals", icon: ClipboardList, group: "Admin", keywords: "queue approve two person" },
  { label: "Backups", href: "/dashboard/admin#backups", icon: Database, group: "Admin", keywords: "backup download restore database" },
  { label: "Bot Config", href: "/dashboard/admin#botsettings", icon: Wrench, group: "Admin", keywords: "settings channel stats config" },
  { label: "Team", href: "/dashboard/admin#team", icon: Users, group: "Admin", keywords: "roles staff permissions team" },
  { label: "Access", href: "/dashboard/admin#access", icon: Lock, group: "Admin", keywords: "owner admin access ids" },
  { label: "Features", href: "/dashboard/admin#features", icon: Settings, group: "Admin", keywords: "feature flags toggles rollout" },
  { label: "Health", href: "/dashboard/admin#health", icon: Activity, group: "Admin", keywords: "health shards lavalink status" },
];

/**
 * Command palette for the header search box, which was previously a
 * decorative input with no behaviour. Opens with Ctrl/Cmd+K.
 */
export function GlobalSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const guildId = useMemo(() => {
    const match = pathname.match(/\/dashboard\/guild\/([^/]+)/);
    return match ? match[1] : null;
  }, [pathname]);

  // Ctrl/Cmd + K focuses the box, Escape closes it.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
      if (event.key === "Escape") {
        setOpen(false);
        inputRef.current?.blur();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const results = useMemo(() => {
    const all = [...TARGETS, ...ADMIN_TABS];
    const needle = query.trim().toLowerCase();

    const usable = all.filter((t) => !t.guildScoped || guildId);
    if (!needle) return usable.slice(0, 8);

    return usable
      .filter(
        (t) =>
          t.label.toLowerCase().includes(needle) ||
          t.keywords.includes(needle) ||
          t.group.toLowerCase().includes(needle)
      )
      .slice(0, 10);
  }, [query, guildId]);

  useEffect(() => setCursor(0), [query]);

  const go = (target: SearchTarget) => {
    const href = target.href.replace("{g}", guildId ?? "");
    router.push(href);
    setOpen(false);
    setQuery("");
    inputRef.current?.blur();
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((c) => Math.min(c + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (event.key === "Enter" && results[cursor]) {
      event.preventDefault();
      go(results[cursor]);
    }
  };

  return (
    <div className="hidden md:flex items-center w-96 max-w-full relative group" ref={boxRef}>
      <Search className="absolute left-4 h-4 w-4 text-slate-500 group-focus-within:text-blue-500 transition-colors z-10" />
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder="Search pages...  Ctrl+K"
        className="w-full bg-white/[0.03] border border-white/5 rounded-2xl py-2.5 pl-12 pr-4 text-xs font-bold text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500/30 focus:bg-white/[0.05] transition-all placeholder:text-slate-600"
      />

      {open && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 max-h-96 overflow-y-auto bg-[#071a33]/95 backdrop-blur-3xl border border-white/10 rounded-2xl shadow-2xl shadow-black/50 z-50 py-2">
          {results.map((target, index) => (
            <button
              key={target.href + target.label}
              onClick={() => go(target)}
              onMouseEnter={() => setCursor(index)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors",
                index === cursor ? "bg-blue-500/10" : "hover:bg-white/[0.03]"
              )}
            >
              <target.icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  index === cursor ? "text-blue-500" : "text-slate-600"
                )}
              />
              <span className="text-sm font-bold text-slate-200 flex-1 truncate">
                {target.label}
              </span>
              <span className="text-[9px] font-black uppercase tracking-widest text-slate-600 shrink-0">
                {target.group}
              </span>
            </button>
          ))}

          {!guildId && (
            <p className="px-4 pt-2 pb-1 text-[10px] text-slate-600 border-t border-white/5 mt-2">
              Open a server to search its settings pages too.
            </p>
          )}
        </div>
      )}

      {open && results.length === 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-[#071a33]/95 backdrop-blur-3xl border border-white/10 rounded-2xl shadow-2xl z-50 p-6">
          <p className="text-xs text-slate-500 text-center">Nothing found for “{query}”.</p>
        </div>
      )}
    </div>
  );
}
