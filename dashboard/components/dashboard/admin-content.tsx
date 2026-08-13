"use client";

import React, { useEffect, useMemo, useState, useRef } from "react";
import {
  Shield, Users, Server, Activity, Database, Cpu, Globe, Lock, Settings,
  RefreshCw, Ban, UserX, Clock, VolumeX, Send, Megaphone, Wrench, AlertTriangle,
  Hash, Volume2, FolderPlus, Pencil, Trash2, Copy,
  Unlock, Timer, MessageSquareX, Bell, BellOff, SearchCheck, Bot, UserCog, UserSearch,
  Webhook, Link, ScrollText, BarChart4, ClipboardList, Terminal, Gem, Gauge, Bug,
  AtSign, Sparkles, Inbox
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { AdminStats, AdminConfig } from "@/types/api";
import { toast } from "sonner";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";
import { Select } from "@/components/ui/select";
import { FeatureFlagsPanel } from "@/components/dashboard/feature-flags-panel";
import { SystemHealthPanel } from "@/components/dashboard/system-health-panel";
import { TeamPanel } from "@/components/dashboard/team-panel";
import { PremiumAdmin } from "@/components/dashboard/premium-admin";
import { SpeedrunAdmin } from "@/components/dashboard/speedrun-admin";
import { TesterPanel } from "@/components/dashboard/tester-panel";
import { ApplicationsAdmin } from "@/components/dashboard/applications-admin";
import { TemplatesAdmin } from "@/components/dashboard/templates-admin";
import { DataAge } from "@/components/ui/data-age";
import { StatValue } from "@/components/ui/stat-value";
import { OwnerAccessPanel } from "@/components/dashboard/owner-access-panel";
import { useSession } from "next-auth/react";
import { ReportsPanel } from "@/components/dashboard/reports-panel";
import { AuditPanel } from "@/components/dashboard/audit-panel";
import { ApprovalsPanel } from "@/components/dashboard/approvals-panel";
import { BotSettingsPanel } from "@/components/dashboard/bot-settings-panel";
import { BroadcastPanel } from "@/components/dashboard/broadcast-panel";
import { BackupsPanel } from "@/components/dashboard/backups-panel";
import { WarningsPanel } from "@/components/dashboard/warnings-panel";
import { CommandStatsPanel } from "@/components/dashboard/command-stats-panel";
import { PingReactionsPanel } from "@/components/dashboard/ping-reactions-panel";
import { DashboardUsersPanel } from "@/components/dashboard/dashboard-users-panel";
import { UserLookupPanel } from "@/components/dashboard/user-lookup-panel";
import { ServersPanel } from "@/components/dashboard/servers-panel";


type TabId = "members" | "channels" | "server" | "scans" | "broadcast" | "system" | "features" | "health" | "team" | "access" | "reports" | "audit" | "approvals" | "botsettings" | "backups" | "warnings" | "usage" | "dashusers" | "servers" | "premium" | "speedrun" | "tester" | "pingreactions" | "templates" | "userlookup" | "webapply";
type MemberAction = "ban" | "kick" | "mute" | "unmute";

type QuickAction = {
  action: string;
  label: string;
  desc: string;
  icon: any;
  tab: Exclude<TabId, "members" | "broadcast" | "system"> | "members";
  needs?: Array<"channel" | "name" | "amount" | "seconds">;
};

const tabs: Array<{ id: TabId; label: string; icon: any }> = [
  { id: "members", label: "Members", icon: Users },
  { id: "channels", label: "Channels", icon: Hash },
  { id: "server", label: "Server", icon: Server },
  { id: "scans", label: "Scans", icon: SearchCheck },
  { id: "broadcast", label: "Broadcast", icon: Megaphone },
  { id: "system", label: "System", icon: Wrench },
  { id: "features", label: "Features", icon: Settings },
  { id: "health", label: "Health", icon: Activity },
  { id: "team", label: "Team", icon: Users },
  { id: "dashusers", label: "Dashboard Users", icon: UserCog },
  { id: "userlookup", label: "Nutzer suchen", icon: UserSearch },
  { id: "servers", label: "Servers", icon: Globe },
  { id: "warnings", label: "Warnungen", icon: AlertTriangle },
  { id: "usage", label: "Nutzung", icon: Terminal },
  { id: "reports", label: "Berichte", icon: BarChart4 },
  { id: "audit", label: "Protokoll", icon: ScrollText },
  { id: "approvals", label: "Freigaben", icon: ClipboardList },
  { id: "backups", label: "Sicherungen", icon: Database },
  { id: "pingreactions", label: "Ping-Reaktionen", icon: AtSign },
  { id: "botsettings", label: "Bot-Einstellungen", icon: Wrench },
  { id: "access", label: "Zugriff", icon: Lock },
  { id: "premium", label: "Premium", icon: Gem },
  { id: "speedrun", label: "Speedrun", icon: Gauge },
  { id: "tester", label: "Tester", icon: Bug },
  { id: "webapply", label: "Bewerbungen", icon: Inbox },
  { id: "templates", label: "Vorlagen", icon: Sparkles },
];

/**
 * The tab bar, grouped.
 *
 * Twenty tabs in one flex-wrap row spilled over three lines of
 * identical-looking buttons, so finding "Backups" meant reading all
 * twenty. Grouping them by what they are for turns that into picking a
 * section first.
 *
 * Every tab appears exactly once; a tab missing from here would vanish
 * from the UI entirely, which is why a test counts them.
 */
const TAB_GROUPS: Array<{ name: string; ids: TabId[] }> = [
  { name: "Server", ids: ["members", "channels", "server", "scans", "broadcast"] },
  { name: "Betrieb", ids: ["health", "system", "usage", "warnings", "reports", "audit"] },
  { name: "Zugriff", ids: ["team", "webapply", "dashusers", "userlookup", "access", "approvals"] },
  { name: "Verwaltung", ids: ["features", "botsettings", "backups", "pingreactions", "servers", "premium", "speedrun", "tester", "templates"] },
];

const memberActions: Array<{ action: MemberAction; label: string; desc: string; icon: any }> = [
  { action: "mute", label: "Mute", desc: "Timeout a member for a selected duration.", icon: Clock },
  { action: "unmute", label: "Unmute", desc: "Remove a member timeout.", icon: VolumeX },
  { action: "kick", label: "Kick", desc: "Remove a member from the server.", icon: UserX },
  { action: "ban", label: "Ban", desc: "Ban a user from the server.", icon: Ban },
];

const quickActions: QuickAction[] = [
  { tab: "channels", action: "create_text_channel", label: "Create Text Channel", desc: "Create a text channel with the given name.", icon: Hash, needs: ["name"] },
  { tab: "channels", action: "create_voice_channel", label: "Create Voice Channel", desc: "Create a voice channel with the given name.", icon: Volume2, needs: ["name"] },
  { tab: "channels", action: "create_category", label: "Create Category", desc: "Create a category with the given name.", icon: FolderPlus, needs: ["name"] },
  { tab: "channels", action: "rename_channel", label: "Rename Channel", desc: "Rename the selected channel.", icon: Pencil, needs: ["channel", "name"] },
  { tab: "channels", action: "delete_channel", label: "Delete Channel", desc: "Delete the selected channel.", icon: Trash2, needs: ["channel"] },
  { tab: "channels", action: "clone_channel", label: "Clone Channel", desc: "Clone selected channel and permissions.", icon: Copy, needs: ["channel"] },
  { tab: "channels", action: "lock_channel", label: "Lock Channel", desc: "Disable @everyone sending messages.", icon: Lock, needs: ["channel"] },
  { tab: "channels", action: "unlock_channel", label: "Unlock Channel", desc: "Restore @everyone send messages.", icon: Unlock, needs: ["channel"] },
  { tab: "channels", action: "slowmode", label: "Set Slowmode", desc: "Set slowmode seconds in selected channel.", icon: Timer, needs: ["channel", "seconds"] },
  { tab: "channels", action: "purge", label: "Purge Messages", desc: "Delete recent messages in selected channel.", icon: MessageSquareX, needs: ["channel", "amount"] },

  { tab: "server", action: "server_name", label: "Rename Server", desc: "Change server name.", icon: Pencil, needs: ["name"] },
  { tab: "server", action: "verification_level_low", label: "Verification Low", desc: "Set verification level to low.", icon: Shield },
  { tab: "server", action: "verification_level_medium", label: "Verification Medium", desc: "Set verification level to medium.", icon: Shield },
  { tab: "server", action: "default_notifications_mentions", label: "Notifications Mentions", desc: "Default notifications: only mentions.", icon: BellOff },
  { tab: "server", action: "default_notifications_all", label: "Notifications All", desc: "Default notifications: all messages.", icon: Bell },

  { tab: "scans", action: "scan_admin_roles", label: "Scan Admin Roles", desc: "List roles with administrator.", icon: Shield },
  { tab: "scans", action: "scan_dangerous_roles", label: "Scan Dangerous Roles", desc: "List roles with risky permissions.", icon: AlertTriangle },
  { tab: "scans", action: "list_bots", label: "List Bots", desc: "List cached bots in the guild.", icon: Bot },
  { tab: "scans", action: "list_staff", label: "List Staff", desc: "List members with staff-like permissions.", icon: UserCog },
  { tab: "scans", action: "server_stats", label: "Server Stats", desc: "Show member/role/channel counts.", icon: Activity },
  { tab: "scans", action: "scan_public_channels", label: "Public Channels", desc: "List public text channels.", icon: Hash },
  { tab: "scans", action: "scan_webhooks", label: "Scan Webhooks", desc: "Find webhooks in text channels.", icon: Webhook },
  { tab: "scans", action: "scan_invites", label: "Scan Invites", desc: "List active invite codes.", icon: Link },
  { tab: "scans", action: "audit_summary", label: "Audit Summary", desc: "Show recent audit log entries.", icon: ScrollText },
];
/** Tabs that render on their own, without the input sidebar. */
const FULL_WIDTH_TABS = new Set<TabId>([
  "features", "health", "team", "access",
  "reports", "audit", "approvals", "botsettings", "backups", "warnings", "usage",
  "dashusers", "userlookup", "servers", "premium", "speedrun", "tester", "templates",
  "webapply",
]);

/** Beschriftung über einem Eingabefeld. */
const LBL = "block text-[10px] font-black uppercase tracking-widest text-slate-600";

function TextInput({ label, value, setValue, placeholder, type = "text" }: { label: string; value: string; setValue: (value: string) => void; placeholder?: string; type?: string }) {
  return (
    <label className="block space-y-2">
      <span className={LBL}>{label}</span>
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        type={type}
        placeholder={placeholder || label}
        className="w-full rounded-xl border border-slate-800 bg-[#0a0a0c] px-4 py-3 text-[14px] text-white placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
      />
    </label>
  );
}

export function AdminContent() {
  const { data: session } = useSession();
  // Own access, used to hide tabs the user has no permission for.
  const [access, setAccess] = useState<{
    is_owner: boolean;
    permissions: string[];
    roles: Array<{ key: string; label: string }>;
  } | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [guilds, setGuilds] = useState<any[]>([]);
  const [channels, setChannels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // When the figures on screen were fetched. Drives the age badges;
  // without it they would have nothing to count from.
  const [lastLoaded, setLastLoaded] = useState<number | null>(null);

  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState("");
  // What the server last confirmed, so an edit in progress is
  // recognisable and "Verwerfen" has something to go back to.
  const savedNotification = useRef("");
  const [activeTab, setActiveTab] = useState<TabId>("members");
  const [result, setResult] = useState("");

  const [guildId, setGuildId] = useState("");
  const [userId, setUserId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("10");
  const [seconds, setSeconds] = useState("5");
  const [duration, setDuration] = useState("60");
  const [reason, setReason] = useState("Dashboard admin action");
  const [memberAction, setMemberAction] = useState<MemberAction>("mute");

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [statsData, configData, guildData] = await Promise.all([api.getAdminStats(), api.getAdminConfig(), api.listGuilds()]);
      setStats(statsData);
      setConfig(configData);
      // Only adopt the server's text when the box is untouched. This
      // poll runs every 30 seconds, so typing a longer notice used to
      // have the text yanked out from under the cursor mid-sentence.
      setNotification((current) =>
        current === savedNotification.current
          ? configData.global_notification || ""
          : current
      );
      savedNotification.current = configData.global_notification || "";
      setGuilds(guildData || []);
      if (!guildId && guildData?.[0]?.id) setGuildId(String(guildData[0].id));
      // Only on success. Stamping this in `finally` would let a failed
      // refresh reset the age to "gerade eben" while the figures on
      // screen are the old ones -- exactly the case the badge exists to
      // reveal.
      setLastLoaded(Date.now());
    } catch (err) {
      console.error("Failed to fetch admin data:", err);
      toast.error("Failed to load real-time data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(true), 30000);
    return () => clearInterval(interval);
  }, []);

  // Open the tab named in the URL hash, e.g. /dashboard/admin#health.
  // The global search links here, and it keeps the tab on a page reload.
  useEffect(() => {
    const applyHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (hash && tabs.some((t) => t.id === hash)) {
        setActiveTab(hash as TabId);
      }
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  // Load own permissions so tabs the user cannot use are hidden.
  useEffect(() => {
    const userId = (session?.user as any)?.id;
    if (!userId) return;
    api
      .getOwnAccess(userId)
      .then(setAccess)
      .catch(() => setAccess(null));
  }, [session?.user]);

  useEffect(() => {
    if (!guildId) return;
    async function loadGuildMeta() {
      try {
        const channelData = await api.getChannels(guildId);
        setChannels(channelData || []);
      } catch (err) {
        setChannels([]);
      }
    }
    loadGuildMeta();
  }, [guildId]);

  const guildOptions = guilds.map((guild) => ({ value: String(guild.id), label: `${guild.name} (${guild.id})` }));
  const channelOptions = channels.map((channel) => ({ value: String(channel.id), label: `#${channel.name}` }));

  const statItems = [
    { name: "Gesamte Nutzer", value: stats?.total_users || "0", icon: Users, color: "text-blue-500" },
    { name: "Active Servers", value: stats?.active_servers || "0", icon: Server, color: "text-emerald-500" },
    { name: "API Latency", value: stats?.api_latency || "0ms", icon: Activity, color: "text-amber-500" },
    { name: "Database Size", value: stats?.db_size || "0 MB", icon: Database, color: "text-purple-500" },
  ];

  // Which permission each tab needs. Tabs without an entry are always shown.
  const TAB_PERMISSION: Partial<Record<TabId, string>> = {
    members: "members.view",
    channels: "channels.manage",
    server: "server.manage",
    scans: "security.scan",
    broadcast: "broadcast.send",
    system: "maintenance.toggle",
    features: "features.view",
    health: "health.view",
    team: "team.view",
    dashusers: "team.view",
    servers: "guild.view",
    warnings: "members.view",
    usage: "metrics.view",
    reports: "reports.view",
    audit: "audit.view",
    approvals: "approvals.view",
    backups: "health.view",
    botsettings: "maintenance.toggle",
    tester: "tester.access",
    webapply: "approvals.resolve",
    // Lesen darf jede Team-Rolle; aendern gated der Proxy separat
    // ueber maintenance.toggle.
    pingreactions: "dashboard.access",
  };

  const visibleTabs = useMemo(() => {
    // Before the permissions arrive, show everything: the API rejects
    // anything the user may not do anyway.
    if (!access) return tabs;
    if (access.is_owner) return tabs;

    // Tester sehen genau einen Reiter -- ihren.
    //
    // Ohne diese Zeile käme jeder Reiter durch, der in TAB_PERMISSION
    // keinen Eintrag hat: die Schleife unten lässt solche mit
    // `return true` stehen. Ein Tester hätte damit Reiter gesehen, die
    // ihn nichts angehen, und beim Klick lauter Fehlermeldungen
    // bekommen. Die Rolle ist bewusst eng: ausprobieren, nicht
    // verwalten.
    const testerOnly =
      access.permissions.includes("tester.access") &&
      !access.permissions.includes("team.view");
    if (testerOnly) return tabs.filter((tab) => tab.id === "tester");

    return tabs.filter((tab) => {
      // Owner/admin management is only for owners and admins, never for
      // people who merely hold a team role.
      if (tab.id === "access") return false;
      // Die Vorlagen-Verwaltung ebenso. Sie zeigt jeden Zugangscode im
      // Klartext, auch den von privaten Vorlagen fremder Server. Der
      // Proxy laesst dorthin nur globale Admins durch -- ohne diese
      // Zeile stuende der Reiter trotzdem in der Leiste und gaebe beim
      // Klick nur eine Fehlermeldung.
      if (tab.id === "templates") return false;
      const required = TAB_PERMISSION[tab.id];
      if (!required) return true;
      return access.permissions.includes(required);
    });
  }, [access]);

  // If the active tab disappeared, fall back to the first one available.
  useEffect(() => {
    if (visibleTabs.length && !visibleTabs.some((t) => t.id === activeTab)) {
      setActiveTab(visibleTabs[0].id);
    }
  }, [visibleTabs, activeTab]);

  // The tabs shown for the open group, in render order. The proximity
  // effect needs the same order and the same count as the DOM, so it is
  // derived once here instead of being rebuilt inside the JSX.
  const shownTabs = useMemo(
    () =>
      TAB_GROUPS.filter((group) => group.ids.includes(activeTab))
        .flatMap((group) => group.ids)
        .map((id) => visibleTabs.find((tab) => tab.id === id))
        .filter(Boolean) as typeof visibleTabs,
    [activeTab, visibleTabs]
  );


  const currentActions = useMemo(() => quickActions.filter((action) => action.tab === activeTab), [activeTab]);
  const currentNeeds = useMemo(() => new Set(currentActions.flatMap((action) => action.needs || [])), [currentActions]);

  const basePayload = () => ({ guild_id: guildId, user_id: userId.trim(), channel_id: channelId, name: name.trim(), amount: Number(amount) || 10, seconds: Number(seconds) || 5, duration_minutes: Number(duration) || 60, reason: reason.trim() });

  const requireGuild = () => {
    if (!guildId) {
      toast.error("Please select a server first.");
      return false;
    }
    return true;
  };

  const runMemberModeration = async () => {
    if (!requireGuild()) return;
    if (!/^\d{15,25}$/.test(userId.trim())) return toast.error("Please enter a valid User ID.");
    if (!reason.trim()) return toast.error("Please enter a reason.");
    setSaving(true);
    const promise = api.runAdminMemberAction({ ...basePayload(), action: memberAction });
    toast.promise(promise, { loading: `Running ${memberAction}...`, success: (data) => data.result, error: (err) => err.message || "Action failed." });
    try { const data = await promise; setResult(data.result); } finally { setSaving(false); }
  };

  const runQuickAction = async (action: QuickAction) => {
    if (!requireGuild()) return;
    if (action.needs?.includes("channel") && !channelId) return toast.error("Please select a channel.");
    if (action.needs?.includes("name") && !name.trim()) return toast.error("Please enter a name.");
    setSaving(true);
    const promise = api.runAdminQuickAction({ ...basePayload(), action: action.action });
    toast.promise(promise, { loading: `Running ${action.label}...`, success: (data) => data.result, error: (err) => err.message || "Action failed." });
    try { const data = await promise; setResult(data.result); } finally { setSaving(false); }
  };

  const handleToggleMaintenance = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const newStatus = !config.maintenance_mode;
      await api.updateAdminConfig({ maintenance_mode: newStatus });
      setConfig({ ...config, maintenance_mode: newStatus });
      toast.success(`Maintenance mode ${newStatus ? "enabled" : "disabled"}`);
    } catch { toast.error("Failed to update maintenance mode"); } finally { setSaving(false); }
  };

  const handleBroadcast = async () => {
    setSaving(true);
    try {
      await api.updateAdminConfig({ global_notification: notification });
      if (config) setConfig({ ...config, global_notification: notification });
      savedNotification.current = notification;
      toast.success("Dashboard-Hinweis gespeichert.");
    } catch { toast.error("Failed to update broadcast message"); } finally { setSaving(false); }
  };

  // The notice is the only free-text field on this page, and it sits at
  // the bottom of the System tab -- easy to type into and walk away
  // from. Refuse to leave while it differs from what was saved.
  const noticeDirty = notification === savedNotification.current ? 0 : 1;
  const noticeGuard = useSaveGuard(noticeDirty, "admin-notice-save-bar");

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <RefreshCw className="h-6 w-6 animate-spin text-indigo-400 opacity-50" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/*
        Der Kopf.

        Er war eine Glaskarte mit Farbverlauf, 64px-Symbolkachel,
        4xl-Ueberschrift in Versalien und einem Knopf, auf dem
        "Real-time Mode" stand -- obwohl die Daten alle 30 Sekunden
        geholt werden. Das war keine Beschreibung, sondern ein
        Versprechen.

        Jetzt: eine Zeile. Titel, Untertitel, ein Knopf, der sagt,
        was er tut.
      */}
      <div className="flex flex-wrap items-center gap-4">
        <Shield className="h-6 w-6 shrink-0 text-indigo-400" />
        <div className="min-w-0 flex-1">
          <h1 className="text-[24px] font-bold tracking-tight text-white">
            Admin-Bereich
          </h1>
          <p className="mt-0.5 text-[14px] text-slate-500">
            Server wählen, dann Moderation und Verwaltung erledigen.
          </p>
        </div>

        <button
          type="button"
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-800 bg-[#131318] px-4 py-2 text-[13px] text-slate-300 transition-colors hover:border-slate-700 hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
          {refreshing ? "Lädt …" : "Aktualisieren"}
          <DataAge since={lastLoaded} />
        </button>
      </div>

      {/*
        Die Zahlen.

        Vier Glaskarten mit Symbolrahmen, die beim Überfahren
        wuchsen, und einer Reveal-Animation je Karte. Auf einer Seite,
        die man täglich öffnet, ist das jedes Mal dieselbe Show.
        Jetzt eine Zeile, die man überfliegt.
      */}
      <div className="flex flex-wrap gap-x-8 gap-y-3 rounded-2xl border border-slate-800 bg-[#131318] px-5 py-4">
        {statItems.map((stat) => (
          <div key={stat.name} className="flex items-center gap-2.5">
            <stat.icon className="h-4 w-4 shrink-0 text-slate-600" />
            <div>
              <span className="text-[17px] font-semibold tabular-nums text-white">
                <StatValue value={stat.value} />
              </span>{" "}
              <span className="text-[13px] text-slate-500">{stat.name}</span>
            </div>
          </div>
        ))}
      </div>

      {/*
        Die Bereiche.

        Vorher: eine Leiste mit Versalien und 0.12em Sperrung, darunter
        die Reiter als gefüllte Knöpfe mit Schlagschatten und einem
        Näherungseffekt, der sie beim Zeigen verschiebt. Zwei
        Navigationsebenen, beide laut.

        Jetzt: die Gruppe als schlichte Zeile, die Reiter darunter als
        Text mit Unterstrich für den aktiven. Der Näherungseffekt ist
        weg -- Knöpfe, die vor dem Zeiger ausweichen, sind ein Effekt,
        kein Hinweis.
      */}
      <div className="rounded-2xl border border-slate-800 bg-[#131318]">
        <div className="flex flex-wrap gap-1 border-b border-slate-800 p-2">
          {TAB_GROUPS.map((group) => {
            const count = group.ids.filter((id) =>
              visibleTabs.some((tab) => tab.id === id),
            ).length;
            if (count === 0) return null;

            const open = group.ids.includes(activeTab);
            return (
              <button
                key={group.name}
                type="button"
                onClick={() => {
                  const first = group.ids.find((id) =>
                    visibleTabs.some((tab) => tab.id === id),
                  );
                  if (first) {
                    setActiveTab(first);
                    window.history.replaceState(null, "", `#${first}`);
                  }
                }}
                aria-current={open ? "true" : undefined}
                className={cn(
                  "rounded-lg px-3.5 py-2 text-[13px] transition-colors",
                  open
                    ? "bg-white/[0.06] font-semibold text-white"
                    : "text-slate-500 hover:text-slate-300",
                )}
              >
                {group.name}
                <span className="ml-1.5 text-[11px] text-slate-600">{count}</span>
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap gap-x-1 gap-y-0.5 p-2">
          {shownTabs.map((tab) => {
            const active = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id);
                  window.history.replaceState(null, "", `#${tab.id}`);
                }}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] transition-colors",
                  active
                    ? "bg-white/[0.06] font-semibold text-white"
                    : "text-slate-500 hover:bg-white/[0.03] hover:text-slate-300",
                )}
              >
                <Icon
                  className={cn(
                    "h-3.5 w-3.5 shrink-0",
                    active ? "text-indigo-400" : "text-slate-600",
                  )}
                />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Features and Health are full-width: they have no input sidebar. */}
      {activeTab === "features" && <FeatureFlagsPanel />}
      {activeTab === "health" && <SystemHealthPanel />}
      {activeTab === "team" && <TeamPanel />}
      {activeTab === "premium" && <PremiumAdmin />}
      {activeTab === "speedrun" && <SpeedrunAdmin />}
      {activeTab === "tester" && <TesterPanel />}
      {activeTab === "webapply" && <ApplicationsAdmin />}
      {activeTab === "access" && <OwnerAccessPanel currentUserId={(session?.user as any)?.id} />}
      {activeTab === "usage" && <CommandStatsPanel />}
      {activeTab === "pingreactions" && <PingReactionsPanel />}
      {activeTab === "templates" && <TemplatesAdmin />}
      {activeTab === "dashusers" && <DashboardUsersPanel currentUserId={(session?.user as any)?.id} />}
      {activeTab === "userlookup" && <UserLookupPanel />}
      {activeTab === "servers" && <ServersPanel currentUserId={(session?.user as any)?.id} />}
      {activeTab === "reports" && <ReportsPanel />}
      {activeTab === "audit" && <AuditPanel />}
      {activeTab === "approvals" && <ApprovalsPanel currentUserId={(session?.user as any)?.id} />}
      {activeTab === "backups" && <BackupsPanel guilds={guilds} />}
      {activeTab === "botsettings" && <BotSettingsPanel />}
      {activeTab === "warnings" && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-800 bg-[#131318] p-5">
            <h3 className="flex items-center gap-2 text-[15px] font-bold text-white">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
              Warnungen
            </h3>
            <p className="mt-1 text-[13px] text-slate-500">
              Wer wurde von wem und warum verwarnt.
            </p>
            <div className="mt-4 max-w-md space-y-1.5">
              <span className={LBL}>Server</span>
              <Select
                value={guildId}
                onValueChange={setGuildId}
                options={guildOptions}
                placeholder="Server wählen"
              />
            </div>
          </div>
          <WarningsPanel guildId={guildId} />
        </div>
      )}

      {!FULL_WIDTH_TABS.has(activeTab) && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
          {/* Die Eingabespalte. War eine Glaskarte mit 2rem-Rundung
              und Versal-Beschriftungen; jetzt dieselbe Karte wie
              überall sonst. */}
          <aside className="h-fit space-y-3 rounded-2xl border border-slate-800 bg-[#131318] p-5 xl:col-span-1">
            <h3 className="text-[15px] font-bold text-white">Eingaben</h3>

            <div className="space-y-1.5">
              <span className={LBL}>Server</span>
              <Select
                value={guildId}
                onValueChange={setGuildId}
                options={guildOptions}
                placeholder="Server wählen"
              />
            </div>

            {activeTab === "members" && (
              <TextInput
                label="Nutzer-ID"
                value={userId}
                setValue={setUserId}
                placeholder="Nur die ID"
              />
            )}
            {currentNeeds.has("channel") && (
              <div className="space-y-1.5">
                <span className={LBL}>Kanal</span>
                <Select
                  value={channelId}
                  onValueChange={setChannelId}
                  options={channelOptions}
                  placeholder="Kanal wählen"
                />
              </div>
            )}
            {currentNeeds.has("name") && (
              <TextInput label="Name" value={name} setValue={setName} />
            )}
            {currentNeeds.has("amount") && (
              <TextInput label="Anzahl" value={amount} setValue={setAmount} type="number" />
            )}
            {currentNeeds.has("seconds") && (
              <TextInput label="Sekunden" value={seconds} setValue={setSeconds} type="number" />
            )}
            {activeTab === "members" && (
              <TextInput
                label="Timeout in Minuten"
                value={duration}
                setValue={setDuration}
                type="number"
              />
            )}
            {(activeTab === "members" ||
              ["channels", "server"].includes(activeTab)) && (
              <label className="block space-y-1.5">
                <span className={LBL}>Grund</span>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  className="w-full resize-none rounded-xl border border-slate-800 bg-[#0a0a0c] px-4 py-3 text-[14px] text-white transition-colors focus:border-slate-700 focus:outline-none"
                />
              </label>
            )}

            {result && (
              <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 p-3.5 text-[13px] leading-relaxed text-emerald-300">
                {result}
              </div>
            )}

            <p className="flex gap-2 border-t border-slate-800 pt-3 text-[12px] leading-relaxed text-slate-500">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" />
              Erst den Server wählen. Für Kick, Bann, Mute und Unmute
              genügen Nutzer-ID, Dauer und Grund.
            </p>
          </aside>

          <main className="space-y-4 xl:col-span-3">
            {activeTab === "members" && (
              <section className="space-y-3">
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  {memberActions.map((card) => {
                    const active = memberAction === card.action;
                    return (
                      <button
                        key={card.action}
                        type="button"
                        onClick={() => setMemberAction(card.action)}
                        className={cn(
                          "rounded-xl border p-4 text-left transition-colors",
                          active
                            ? "border-indigo-500/40 bg-indigo-500/10"
                            : "border-slate-800 bg-[#0f0f13] hover:border-slate-700",
                        )}
                      >
                        <card.icon
                          className={cn(
                            "mb-2.5 h-[18px] w-[18px]",
                            active ? "text-indigo-400" : "text-slate-600",
                          )}
                        />
                        <p className="text-[14px] font-semibold text-white">
                          {card.label}
                        </p>
                        <p className="mt-0.5 text-[12px] leading-relaxed text-slate-500">
                          {card.desc}
                        </p>
                      </button>
                    );
                  })}
                </div>
                <button
                  type="button"
                  onClick={runMemberModeration}
                  disabled={saving}
                  className="w-full rounded-xl bg-[#5865f2] py-3 text-[14px] font-semibold text-white transition-colors hover:bg-[#4752c4] disabled:opacity-50"
                >
                  {memberActions.find((a) => a.action === memberAction)?.label ??
                    "Ausführen"}{" "}
                  ausführen
                </button>
              </section>
            )}

            {["members", "channels", "server", "scans"].includes(activeTab) && (
              <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {currentActions.map((action) => (
                  <button
                    key={action.action}
                    type="button"
                    onClick={() => runQuickAction(action)}
                    disabled={saving}
                    className="rounded-xl border border-slate-800 bg-[#0f0f13] p-4 text-left transition-colors hover:border-slate-700 disabled:opacity-50"
                  >
                    <action.icon className="mb-2.5 h-[18px] w-[18px] text-slate-600" />
                    <h4 className="text-[14px] font-semibold text-white">
                      {action.label}
                    </h4>
                    <p className="mt-1 text-[12px] leading-relaxed text-slate-500">
                      {action.desc}
                    </p>
                    {action.needs?.length ? (
                      <p className="mt-2.5 text-[11px] text-slate-600">
                        Braucht: {action.needs.join(", ")}
                      </p>
                    ) : null}
                  </button>
                ))}
              </section>
            )}

            {activeTab === "broadcast" && <BroadcastPanel guilds={guilds} />}

            {activeTab === "system" && (
              <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                <div className="rounded-2xl border border-slate-800 bg-[#131318] p-5 lg:col-span-2">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <h3 className="flex items-center gap-2 text-[15px] font-bold text-white">
                      <Activity className="h-4 w-4 text-indigo-400" />
                      Systemzustand
                    </h3>
                    <span className="text-[12px] text-slate-600">
                      alle 30 Sekunden
                    </span>
                  </div>
                  <div className="space-y-2">
                    {stats?.nodes.map((node) => {
                      const Icon =
                        node.icon === "Globe"
                          ? Globe
                          : node.icon === "Database"
                            ? Database
                            : node.icon === "Cpu"
                              ? Cpu
                              : Lock;
                      const healthy = node.status === "Healthy";
                      return (
                        <div
                          key={node.name}
                          className="flex items-center gap-3 rounded-xl border border-slate-800 bg-[#0f0f13] px-4 py-3"
                        >
                          <Icon className="h-4 w-4 shrink-0 text-slate-600" />
                          <div className="min-w-0 flex-1">
                            <p className="text-[14px] font-semibold text-white">
                              {node.name}
                            </p>
                            <p className="mt-0.5 text-[12px] text-slate-500">
                              Auslastung: {node.load}
                            </p>
                          </div>
                          <span
                            className={cn(
                              "shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-semibold",
                              healthy
                                ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-400"
                                : "border-amber-500/25 bg-amber-500/10 text-amber-400",
                            )}
                          >
                            {healthy ? "In Ordnung" : node.status}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-4 rounded-2xl border border-slate-800 bg-[#131318] p-5">
                  <h3 className="flex items-center gap-2 text-[15px] font-bold text-white">
                    <Settings className="h-4 w-4 text-indigo-400" />
                    Steuerung
                  </h3>

                  <button
                    type="button"
                    onClick={handleToggleMaintenance}
                    disabled={saving}
                    className={cn(
                      "w-full rounded-xl border px-4 py-3 text-left text-[14px] transition-colors",
                      config?.maintenance_mode
                        ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
                        : "border-slate-800 bg-[#0f0f13] text-slate-300 hover:border-slate-700",
                    )}
                  >
                    {config?.maintenance_mode
                      ? "Wartungsmodus ist an"
                      : "Normalbetrieb"}
                  </button>

                  {/* Der Hinweis im Dashboard. Er stand einmal unter
                      "Global Broadcast" -- was er nicht ist: er
                      erreicht nie Discord, nur wer das Dashboard
                      öffnet. */}
                  <div className="space-y-2.5 border-t border-slate-800 pt-4">
                    <h4 className="text-[14px] font-semibold text-white">
                      Dashboard-Hinweis
                    </h4>
                    <p className="text-[12px] leading-relaxed text-slate-500">
                      Steht oben im Dashboard. Geht <b>nicht</b> an
                      Discord — dafür ist der Broadcast-Bereich da.
                    </p>
                    <textarea
                      value={notification}
                      onChange={(e) => setNotification(e.target.value)}
                      rows={3}
                      placeholder="Leer lassen, um den Hinweis zu entfernen"
                      className="w-full resize-none rounded-xl border border-slate-800 bg-[#0a0a0c] px-4 py-3 text-[14px] text-slate-200 placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={handleBroadcast}
                      disabled={saving || !noticeDirty}
                      className="w-full rounded-xl border border-slate-800 py-2.5 text-[13px] text-slate-300 transition-colors hover:border-slate-700 hover:text-white disabled:opacity-50"
                    >
                      Hinweis speichern
                    </button>
                  </div>
                </div>
              </section>
            )}
          </main>
        </div>
      )}

      <StickySaveBar
        id="admin-notice-save-bar"
        count={noticeDirty}
        busy={saving}
        shake={noticeGuard.shake}
        onDiscard={() => setNotification(savedNotification.current)}
        onSave={handleBroadcast}
      />
    </div>
  );
}
