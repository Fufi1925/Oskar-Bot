"use client";

import React, { useEffect, useMemo, useState, useRef } from "react";
import {
  Shield, Users, Server, Activity, Database, Cpu, Globe, Lock, Settings,
  RefreshCw, Ban, UserX, Clock, VolumeX, Send, Megaphone, Wrench, AlertTriangle,
  Hash, Volume2, FolderPlus, Pencil, Trash2, Copy,
  Unlock, Timer, MessageSquareX, Bell, BellOff, SearchCheck, Bot, UserCog, UserSearch,
  Webhook, Link, ScrollText, BarChart4, ClipboardList, Terminal, Gem, Gauge, Bug,
  AtSign, Sparkles, Inbox, Cookie, BotMessageSquare
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
import { OverviewCharts } from "@/components/dashboard/overview-charts";
import { CookieConsentsPanel } from "@/components/dashboard/cookie-consents-panel";
import { TrustedBotsPanel } from "@/components/dashboard/trusted-bots-panel";


type TabId = "members" | "channels" | "server" | "scans" | "broadcast" | "system" | "features" | "health" | "team" | "access" | "reports" | "audit" | "approvals" | "botsettings" | "backups" | "warnings" | "usage" | "dashusers" | "servers" | "premium" | "speedrun" | "tester" | "pingreactions" | "templates" | "userlookup" | "webapply" | "cookies" | "trustedbots";
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
  { id: "members", label: "Mitglieder", icon: Users },
  { id: "channels", label: "Kanäle", icon: Hash },
  { id: "server", label: "Server", icon: Server },
  { id: "scans", label: "Scans", icon: SearchCheck },
  { id: "broadcast", label: "Rundruf", icon: Megaphone },
  { id: "system", label: "System", icon: Wrench },
  { id: "features", label: "Funktionen", icon: Settings },
  { id: "health", label: "Zustand", icon: Activity },
  { id: "team", label: "Team", icon: Users },
  { id: "dashusers", label: "Dashboard-Nutzer", icon: UserCog },
  { id: "userlookup", label: "Nutzer suchen", icon: UserSearch },
  { id: "servers", label: "Alle Server", icon: Globe },
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
  { id: "cookies", label: "Cookie-Hinweis", icon: Cookie },
  { id: "trustedbots", label: "Vertraute Bots", icon: BotMessageSquare },
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
  { name: "Verwaltung", ids: ["features", "botsettings", "backups", "pingreactions", "servers", "premium", "speedrun", "tester", "templates", "cookies", "trustedbots"] },
];

/**
 * Welches Recht eine Aktion braucht.
 *
 * Die Werte sind nicht ausgedacht: sie stehen genauso in
 * `app/api/bot/[...path]/route.ts` (`permissionFor`). Zwei Listen,
 * die dasselbe bedeuten, laufen auseinander -- deshalb steht hier
 * eine Notiz statt einer zweiten Wahrheit.
 *
 * Ohne diese Angabe zeigte die Oberfläche jedem alles: ein
 * Trial-Moderator, der nur verwarnen darf, sah „Kicken“ und
 * „Bannen“ und bekam beim Klick eine Fehlermeldung. Im Screenshot
 * nachgemessen, nicht vermutet.
 */
const AKTION_RECHT: Record<string, string> = {
  mute: "moderation.mute",
  unmute: "moderation.mute",
  kick: "moderation.kick",
  ban: "moderation.ban",
  purge: "moderation.purge",
  nickname: "members.manage",
  clear_nickname: "members.manage",
  add_role: "members.manage",
  remove_role: "members.manage",
  member_info: "members.view",
  create_role: "roles.manage",
  delete_role: "roles.manage",
  rename_role: "roles.manage",
  color_role: "roles.manage",
  toggle_role_hoist: "roles.manage",
  toggle_role_mentionable: "roles.manage",
  create_text_channel: "channels.manage",
  create_voice_channel: "channels.manage",
  create_category: "channels.manage",
  rename_channel: "channels.manage",
  delete_channel: "channels.manage",
  clone_channel: "channels.manage",
  lock_channel: "channels.manage",
  unlock_channel: "channels.manage",
  slowmode: "channels.manage",
  server_name: "server.manage",
  verification_level_low: "server.manage",
  verification_level_medium: "server.manage",
  default_notifications_mentions: "server.manage",
  default_notifications_all: "server.manage",
};

/**
 * Das Recht zu einer Aktion, inklusive der Sammelregel des Proxys:
 * alles, was mit `scan_`/`list_` anfängt, verlangt `security.scan`.
 */
function rechtFuer(action: string): string | null {
  if (AKTION_RECHT[action]) return AKTION_RECHT[action];
  if (
    action.startsWith("scan_") ||
    action.startsWith("list_") ||
    action === "audit_summary" ||
    action === "server_stats"
  ) {
    return "security.scan";
  }
  return null;
}

const memberActions: Array<{ action: MemberAction; label: string; desc: string; icon: any }> = [
  { action: "mute", label: "Stummschalten", desc: "Sperrt einen Nutzer für die gewählte Dauer.", icon: Clock },
  { action: "unmute", label: "Entstummen", desc: "Hebt die Zeitsperre wieder auf.", icon: VolumeX },
  { action: "kick", label: "Kicken", desc: "Wirft jemanden vom Server — er darf zurück.", icon: UserX },
  { action: "ban", label: "Bannen", desc: "Sperrt jemanden dauerhaft aus.", icon: Ban },
];

const quickActions: QuickAction[] = [
  { tab: "channels", action: "create_text_channel", label: "Textkanal anlegen", desc: "Legt einen Textkanal mit dem Namen an.", icon: Hash, needs: ["name"] },
  { tab: "channels", action: "create_voice_channel", label: "Sprachkanal anlegen", desc: "Legt einen Sprachkanal mit dem Namen an.", icon: Volume2, needs: ["name"] },
  { tab: "channels", action: "create_category", label: "Kategorie anlegen", desc: "Legt eine Kategorie mit dem Namen an.", icon: FolderPlus, needs: ["name"] },
  { tab: "channels", action: "rename_channel", label: "Kanal umbenennen", desc: "Benennt den gewählten Kanal um.", icon: Pencil, needs: ["channel", "name"] },
  { tab: "channels", action: "delete_channel", label: "Kanal löschen", desc: "Löscht den gewählten Kanal endgültig.", icon: Trash2, needs: ["channel"] },
  { tab: "channels", action: "clone_channel", label: "Kanal klonen", desc: "Kopiert Kanal samt Rechten.", icon: Copy, needs: ["channel"] },
  { tab: "channels", action: "lock_channel", label: "Kanal sperren", desc: "Niemand außer dem Team darf noch schreiben.", icon: Lock, needs: ["channel"] },
  { tab: "channels", action: "unlock_channel", label: "Kanal entsperren", desc: "Alle dürfen wieder schreiben.", icon: Unlock, needs: ["channel"] },
  { tab: "channels", action: "slowmode", label: "Langsam-Modus", desc: "Wartezeit zwischen zwei Nachrichten.", icon: Timer, needs: ["channel", "seconds"] },
  { tab: "channels", action: "purge", label: "Nachrichten löschen", desc: "Räumt die letzten Nachrichten weg.", icon: MessageSquareX, needs: ["channel", "amount"] },

  { tab: "server", action: "server_name", label: "Server umbenennen", desc: "Ändert den Namen des Servers.", icon: Pencil, needs: ["name"] },
  { tab: "server", action: "verification_level_low", label: "Sicherheit niedrig", desc: "Setzt die Sicherheitsstufe auf niedrig.", icon: Shield },
  { tab: "server", action: "verification_level_medium", label: "Sicherheit mittel", desc: "Setzt die Sicherheitsstufe auf mittel.", icon: Shield },
  { tab: "server", action: "default_notifications_mentions", label: "Nur bei Erwähnung", desc: "Standard-Hinweise nur bei Erwähnungen.", icon: BellOff },
  { tab: "server", action: "default_notifications_all", label: "Bei allem", desc: "Standard-Hinweise bei jeder Nachricht.", icon: Bell },

  { tab: "scans", action: "scan_admin_roles", label: "Admin-Rollen prüfen", desc: "Zeigt alle Rollen mit Administrator.", icon: Shield },
  { tab: "scans", action: "scan_dangerous_roles", label: "Riskante Rollen", desc: "Zeigt Rollen mit gefährlichen Rechten.", icon: AlertTriangle },
  { tab: "scans", action: "list_bots", label: "Bots auflisten", desc: "Zeigt alle Bots auf dem Server.", icon: Bot },
  { tab: "scans", action: "list_staff", label: "Team auflisten", desc: "Zeigt alle mit Team-Rechten.", icon: UserCog },
  { tab: "scans", action: "server_stats", label: "Server-Zahlen", desc: "Mitglieder, Rollen und Kanäle gezählt.", icon: Activity },
  { tab: "scans", action: "scan_public_channels", label: "Offene Kanäle", desc: "Zeigt alle öffentlichen Textkanäle.", icon: Hash },
  { tab: "scans", action: "scan_webhooks", label: "Webhooks prüfen", desc: "Sucht Webhooks in allen Textkanälen.", icon: Webhook },
  { tab: "scans", action: "scan_invites", label: "Einladungen prüfen", desc: "Zeigt alle gültigen Einladungslinks.", icon: Link },
  { tab: "scans", action: "audit_summary", label: "Protokoll-Auszug", desc: "Die letzten Einträge aus dem Discord-Protokoll.", icon: ScrollText },
];
/** Tabs that render on their own, without the input sidebar. */
const FULL_WIDTH_TABS = new Set<TabId>([
  "features", "health", "team", "access",
  "reports", "audit", "approvals", "botsettings", "backups", "warnings", "usage",
  "dashusers", "userlookup", "servers", "premium", "speedrun", "tester", "templates",
  "webapply", "cookies", "trustedbots",
]);

/** Beschriftung über einem Eingabefeld. */
const LBL = "block text-[10px] font-black uppercase tracking-widest text-slate-600";

/**
 * Wie die Pflichtfelder heißen, wenn man sie jemandem zeigt.
 *
 * `needs` trägt die technischen Schlüssel — die stehen so im
 * Formular-Zustand und dürfen nicht übersetzt werden. Unter der Karte
 * stand deshalb wörtlich „Braucht: channel, amount“ auf einer sonst
 * deutschen Seite.
 */
const BRAUCHT: Record<NonNullable<QuickAction["needs"]>[number], string> = {
  channel: "Kanal",
  name: "Name",
  amount: "Anzahl",
  seconds: "Sekunden",
};

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
  // Dieser Text landet im Discord-Auditlog und steht dort dauerhaft
  // neben dem Bann. Er stand auf Englisch da -- auf einem deutschen
  // Server liest sich das wie ein fremder Eingriff.
  const [reason, setReason] = useState("Über das Dashboard");
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
      toast.error("Die Zahlen ließen sich nicht laden.");
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
    // Deutsch, wie der Rest der Seite. Drei dieser vier Zeilen
    // standen auf Englisch da -- direkt neben "Server wählen, dann
    // Moderation und Verwaltung erledigen."
    { name: "Nutzer gesamt", value: stats?.total_users || "0", icon: Users, color: "text-blue-500" },
    { name: "Aktive Server", value: stats?.active_servers || "0", icon: Server, color: "text-emerald-500" },
    { name: "Antwortzeit", value: stats?.api_latency || "0ms", icon: Activity, color: "text-amber-500" },
    { name: "Datenbank", value: stats?.db_size || "0 MB", icon: Database, color: "text-purple-500" },
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
    // Diese drei hatten hier gar keinen Eintrag -- und ein Reiter ohne
    // Eintrag wird JEDEM gezeigt, auch einem Trial-Moderator. Beim
    // Klick kam dann die Fehlermeldung des Proxys. Nachgemessen: 39
    // von 41 Rollen sahen "Nutzer suchen", obwohl der Proxy dort
    // team.view verlangt.
    //
    // Die Werte sind nicht ausgedacht, sondern das, was der Proxy
    // wirklich prueft:
    //   userlookup -> die /access-Routen verlangen team.view (GET)
    //   premium    -> /premium/keys verlangt eine Team-Rolle
    //   speedrun   -> die eingreifendste Aktion ueberhaupt: sie legt
    //                 Dutzende Rollen und Kanaele an
    userlookup: "team.view",
    premium: "premium.manage",
    speedrun: "server.manage",
    // Lesen darf jede Team-Rolle; aendern gated der Proxy separat
    // ueber maintenance.toggle.
    pingreactions: "dashboard.access",
    // Die Cookie-Bestaetigungen. Die Liste nennt Discord-Konten und
    // Zeitpunkte, also dieselbe Schwelle wie bei den
    // Dashboard-Nutzern. Genau das prueft auch der Proxy (`scope ===
    // "cookies"`); stuende hier weniger, waere der Reiter sichtbar
    // und gaebe beim Klick nur eine Fehlermeldung.
    cookies: "team.view",
    // Die vertrauten Bots. Lesen darf jede Team-Rolle -- die Liste
    // steht ohnehin in jedem Server-Reiter. Aendern verlangt
    // maintenance.toggle, und genau das prueft auch der Proxy.
    trustedbots: "dashboard.access",
  };

  const visibleTabs = useMemo(() => {
    // Solange die Rechte nicht da sind: NICHTS zeigen.
    //
    // Hier stand „alles zeigen, die API weist ohnehin ab“. Das war aus
    // zwei Gründen falsch. Erstens sah jeder für einen Moment die
    // vollständige Leiste — einundzwanzig Reiter, von denen ihm die
    // meisten nichts sagen; klickte er schnell, bekam er eine
    // Fehlermeldung statt einer Antwort. Zweitens ist „die API weist
    // ab“ keine Begründung für eine Anzeige: was auf dem Bildschirm
    // steht, ist eine Aussage darüber, was jemand darf.
    //
    // Ein leerer Zustand ist die ehrlichere Zwischenstufe: er sagt
    // „wird geprüft“ statt „du darfst das alles“.
    if (!access) return [];
    if (access.is_owner) return tabs;

    // Wer gar keine Rolle hat, sieht keinen einzigen Reiter. Die Seite
    // selbst leitet solche Leute schon weg (`app/dashboard/admin/
    // page.tsx`), aber diese Prüfung darf sich nicht darauf verlassen:
    // Rollen können entzogen werden, während die Seite offen ist.
    if (!access.is_owner && (access.roles?.length ?? 0) === 0) return [];

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


  /**
   * Darf der Nutzer diese Aktion überhaupt?
   *
   * Owner dürfen alles. Solange die Rechte noch nicht da sind, wird
   * NICHTS gezeigt — sonst blitzt kurz die volle Liste auf, und wer
   * schnell klickt, bekommt eine Fehlermeldung statt einer Antwort.
   */
  const darf = React.useCallback(
    (action: string) => {
      if (!access) return false;
      if (access.is_owner) return true;
      const noetig = rechtFuer(action);
      if (!noetig) return true;
      return access.permissions.includes(noetig);
    },
    [access],
  );

  // Nur die Aktionen, die der Nutzer auch ausführen darf. Vorher
  // sah ein Trial-Moderator „Kicken“ und „Bannen“ — beides gab beim
  // Klick 403.
  const sichtbareMemberActions = useMemo(
    () => memberActions.filter((card) => darf(card.action)),
    [darf],
  );

  const currentActions = useMemo(
    () => quickActions.filter((action) => action.tab === activeTab && darf(action.action)),
    [activeTab, darf],
  );

  // Faellt die gewaehlte Moderations-Aktion weg, auf eine erlaubte
  // wechseln. Sonst steht auf dem Knopf „Bannen ausfuehren“, obwohl
  // die Karte dazu gar nicht mehr da ist -- und der Klick gibt 403.
  useEffect(() => {
    if (
      sichtbareMemberActions.length &&
      !sichtbareMemberActions.some((a) => a.action === memberAction)
    ) {
      setMemberAction(sichtbareMemberActions[0].action);
    }
  }, [sichtbareMemberActions, memberAction]);
  const currentNeeds = useMemo(() => new Set(currentActions.flatMap((action) => action.needs || [])), [currentActions]);

  const basePayload = () => ({ guild_id: guildId, user_id: userId.trim(), channel_id: channelId, name: name.trim(), amount: Number(amount) || 10, seconds: Number(seconds) || 5, duration_minutes: Number(duration) || 60, reason: reason.trim() });

  const requireGuild = () => {
    if (!guildId) {
      toast.error("Wähle zuerst einen Server.");
      return false;
    }
    return true;
  };

  const runMemberModeration = async () => {
    if (!requireGuild()) return;
    if (!/^\d{15,25}$/.test(userId.trim())) return toast.error("Das ist keine gültige Nutzer-ID.");
    if (!reason.trim()) return toast.error("Ohne Grund geht das nicht.");
    setSaving(true);
    const promise = api.runAdminMemberAction({ ...basePayload(), action: memberAction });
    toast.promise(promise, { loading: "Wird ausgeführt …", success: (data) => data.result, error: (err) => err.message || "Das hat nicht geklappt." });
    try { const data = await promise; setResult(data.result); } finally { setSaving(false); }
  };

  const runQuickAction = async (action: QuickAction) => {
    if (!requireGuild()) return;
    if (action.needs?.includes("channel") && !channelId) return toast.error("Wähle zuerst einen Kanal.");
    if (action.needs?.includes("name") && !name.trim()) return toast.error("Es fehlt noch ein Name.");
    setSaving(true);
    const promise = api.runAdminQuickAction({ ...basePayload(), action: action.action });
    toast.promise(promise, { loading: `${action.label} …`, success: (data) => data.result, error: (err) => err.message || "Das hat nicht geklappt." });
    try { const data = await promise; setResult(data.result); } finally { setSaving(false); }
  };

  const handleToggleMaintenance = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const newStatus = !config.maintenance_mode;
      await api.updateAdminConfig({ maintenance_mode: newStatus });
      setConfig({ ...config, maintenance_mode: newStatus });
      toast.success(newStatus ? "Wartungsmodus ist an." : "Wartungsmodus ist aus.");
    } catch { toast.error("Der Wartungsmodus ließ sich nicht umstellen."); } finally { setSaving(false); }
  };

  const handleBroadcast = async () => {
    setSaving(true);
    try {
      await api.updateAdminConfig({ global_notification: notification });
      if (config) setConfig({ ...config, global_notification: notification });
      savedNotification.current = notification;
      toast.success("Dashboard-Hinweis gespeichert.");
    } catch { toast.error("Der Hinweis ließ sich nicht speichern."); } finally { setSaving(false); }
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

  // Die Rechte sind noch unterwegs.
  //
  // Vorher wurde in diesem Moment die volle Reiterleiste gezeigt.
  // Jetzt steht hier, was tatsächlich passiert — das ist eine
  // Zehntelsekunde ehrlicher als einundzwanzig Reiter, die gleich
  // wieder verschwinden.
  if (!access) {
    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center gap-3">
        <RefreshCw className="h-5 w-5 animate-spin text-indigo-400 opacity-50" />
        <p className="text-[13px] text-slate-500">Berechtigungen werden geprüft …</p>
      </div>
    );
  }

  // Angemeldet, aber ohne jede Dashboard-Rolle.
  //
  // Normalerweise kommt hier niemand an: `app/dashboard/admin/page.tsx`
  // leitet solche Leute zurück. Wird eine Rolle aber entzogen, während
  // die Seite offen ist, steht der Betreffende genau hier — und soll
  // dann einen Satz lesen statt einer leeren Fläche.
  if (!access.is_owner && (access.roles?.length ?? 0) === 0) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border border-slate-800 bg-[#131318] px-6 py-10 text-center">
        <Lock className="mx-auto mb-3 h-7 w-7 text-slate-700" />
        <p className="text-[15px] text-slate-300">
          Für den Admin-Bereich fehlt dir eine Rolle.
        </p>
        <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">
          Deine eigenen Server kannst du weiterhin ganz normal verwalten —
          dieser Bereich ist nur für das Team des Bots.
        </p>
        <a
          href="/dashboard"
          className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#5865f2] px-5 py-2.5 text-[14px] font-semibold text-white transition-colors hover:bg-[#4752c4]"
        >
          Zurück zum Dashboard
        </a>
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
      <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-slate-800 bg-[#131318] px-5 py-4">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-indigo-500/25 bg-indigo-500/10">
          <Shield className="h-[18px] w-[18px] text-indigo-400" />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-bold tracking-tight text-white">
            Admin-Bereich
          </h1>
          <p className="mt-0.5 text-[13px] text-slate-500">
            Server wählen, dann Moderation und Verwaltung erledigen.
          </p>
        </div>

        <button
          type="button"
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-800 bg-[#0f0f13] px-4 py-2 text-[13px] text-slate-300 transition-colors hover:border-slate-700 hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
          {refreshing ? "Lädt …" : "Aktualisieren"}
          <DataAge since={lastLoaded} />
        </button>
      </div>

      {/*
        Die Zahlen.

        Erst waren es vier Glaskarten mit wachsenden Symbolen und
        einer Einblend-Animation je Karte -- auf einer Seite, die man
        täglich öffnet, jedes Mal dieselbe Show. Dann eine einzige
        Textzeile, und die war zu wenig: vier Zahlen dicht
        nebeneinander lesen sich als ein Satz, nicht als vier Angaben.

        Jetzt vier ruhige Felder mit eigener Fläche. Die Farbe steckt
        nur im Symbol -- sie ordnet zu, ohne dass etwas leuchtet.
      */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {statItems.map((stat) => (
          <div
            key={stat.name}
            className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-[#131318] px-4 py-3.5"
          >
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/[0.04]">
              <stat.icon className={cn("h-4 w-4", stat.color)} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-[19px] font-bold leading-none tabular-nums text-white">
                <StatValue value={stat.value} />
              </p>
              <p className="mt-1.5 truncate text-[12px] text-slate-500">
                {stat.name}
              </p>
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
      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]">
        {/* Die Gruppen. Sie tragen die Unterscheidung als Linie
            darunter, nicht als Fläche: sonst sähen Gruppe und Reiter
            gleich aus, und zwei gleich aussehende Zeilen übereinander
            lesen sich nicht als Ebene und Unterebene. */}
        <div className="flex flex-wrap gap-x-1 border-b border-slate-800 px-2 pt-1.5">
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
                  "-mb-px border-b-2 px-3.5 pb-2.5 pt-1.5 text-[13px] transition-colors",
                  open
                    ? "border-indigo-500 font-semibold text-white"
                    : "border-transparent text-slate-500 hover:text-slate-300",
                )}
              >
                {group.name}
                <span
                  className={cn(
                    "ml-1.5 text-[11px]",
                    open ? "text-indigo-400/70" : "text-slate-600",
                  )}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Die Reiter der offenen Gruppe. Fläche statt Linie -- die
            zweite Ebene ist die, in der man wählt. */}
        <div className="flex flex-wrap gap-1 bg-[#0f0f13] p-2">
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
                  "flex items-center gap-2 rounded-lg border px-3 py-2 text-[13px] transition-colors",
                  active
                    ? "border-indigo-500/30 bg-indigo-500/10 font-semibold text-white"
                    : "border-transparent text-slate-500 hover:bg-white/[0.03] hover:text-slate-300",
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
      {/* Nutzung: erst der Verlauf über alle Server, dann die
          Aufschlüsselung nach Befehl. Die Reihenfolge ist die der
          Fragen -- "läuft es?" kommt vor "welcher Befehl?". */}
      {activeTab === "usage" && (
        <div className="space-y-4">
          <OverviewCharts />
          <CommandStatsPanel />
        </div>
      )}
      {activeTab === "pingreactions" && <PingReactionsPanel />}
      {activeTab === "cookies" && <CookieConsentsPanel />}
      {activeTab === "trustedbots" && <TrustedBotsPanel />}
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
                {/* Keine einzige erlaubte Aktion: dann auch keinen
                    toten Knopf. Ein Satz sagt mehr als ein grauer
                    Balken, den man nicht drücken kann. */}
                {sichtbareMemberActions.length === 0 ? (
                  <div className="rounded-2xl border border-slate-800 bg-[#131318] px-6 py-8 text-center">
                    <p className="text-[14px] text-slate-300">
                      Deine Rolle erlaubt hier keine Aktion.
                    </p>
                    <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">
                      Zum Stummschalten, Kicken oder Bannen fehlt dir die
                      Berechtigung. Ein Owner kann sie dir geben.
                    </p>
                  </div>
                ) : (
                  <>
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  {sichtbareMemberActions.map((card) => {
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
                </>
                )}
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
                        Braucht: {action.needs.map((n) => BRAUCHT[n]).join(", ")}
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
