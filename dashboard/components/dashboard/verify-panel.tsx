"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Clock3,
  Eye,
  FileText,
  History,
  Info,
  ListChecks,
  Link2,
  Mail,
  MessageSquareText,
  Plus,
  RefreshCw,
  Send,
  Server,
  Settings2,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UserMinus,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker } from "@/components/dashboard/pickers";
import {
  InlineToggle,
  SwitchToggle,
} from "@/components/dashboard/form-elements";
import {
  Loading,
  StickySaveBar,
  usePanel,
  useSaveGuard,
} from "@/components/dashboard/save-bar";
import { EmojiText } from "@/components/dashboard/emoji-field";
import { DiscordEmojiText } from "@/components/dashboard/discord-emoji";
import { LogUmgezogen } from "@/components/dashboard/log-umgezogen";

const INPUT =
  "w-full rounded-xl border border-slate-800 bg-[#0b0e16] px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-blue-500/60 focus:ring-4 focus:ring-blue-500/10";

const TABS = [
  { id: "setup", label: "Einrichtung", icon: ListChecks },
  { id: "blacklist", label: "Blacklist", icon: Server },
  { id: "messages", label: "Nachrichten", icon: MessageSquareText },
  { id: "advanced", label: "Erweitert", icon: SlidersHorizontal },
  { id: "history", label: "Verlauf", icon: History },
] as const;

type TabId = (typeof TABS)[number]["id"];

const KNOWN = [
  "{server}",
  "{user}",
  "{user.name}",
  "{role}",
  "{member_count}",
  "{blocked_server}",
];

function fill(text: string, role: string, server: string) {
  return String(text ?? "")
    .replace(/\{server\}/g, server)
    .replace(/\{user\.name\}/g, "Lena")
    .replace(/\{user\}/g, "@Lena")
    .replace(/\{role\}/g, role)
    .replace(/\{member_count\}/g, "1.204")
    .replace(/\{blocked_server\}/g, "Beispielserver");
}

function unknownPlaceholders(text: string): string[] {
  const found = String(text ?? "").match(/\{[a-z_.]+\}/g) || [];
  return Array.from(new Set(found.filter((value) => !KNOWN.includes(value))));
}

function Field({ label, hint, required, children }: any) {
  return (
    <label className="block space-y-2.5">
      <span className="flex items-center gap-2 text-xs font-extrabold text-slate-300">
        {label}
        {required && (
          <span className="rounded-md bg-blue-500/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-blue-300">
            Pflicht
          </span>
        )}
      </span>
      {children}
      {hint && (
        <span className="block text-[11px] leading-relaxed text-slate-500">
          {hint}
        </span>
      )}
    </label>
  );
}

function Section({
  icon: Icon,
  title,
  subtitle,
  children,
  tone = "blue",
}: any) {
  const tones: Record<string, string> = {
    blue: "bg-blue-500/10 text-blue-300 ring-blue-500/20",
    rose: "bg-rose-500/10 text-rose-300 ring-rose-500/20",
    emerald: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/20",
    amber: "bg-amber-500/10 text-amber-300 ring-amber-500/20",
  };
  return (
    <section className="space-y-5 rounded-3xl border border-slate-800 bg-[#131318] p-4 sm:p-6">
      <header className="flex items-start gap-3">
        <div
          className={cn(
            "grid h-10 w-10 shrink-0 place-items-center rounded-xl ring-1",
            tones[tone] || tones.blue,
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 pt-0.5">
          <h2 className="font-bold text-white">{title}</h2>
          {subtitle && (
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              {subtitle}
            </p>
          )}
        </div>
      </header>
      <div className="space-y-5">{children}</div>
    </section>
  );
}

function TextField({
  label,
  hint,
  value,
  onChange,
  rows = 3,
  role,
  server,
  max,
}: any) {
  const bad = unknownPlaceholders(value);
  return (
    <Field label={label} hint={hint}>
      <EmojiText
        value={value ?? ""}
        onChange={onChange}
        rows={rows === 1 ? undefined : rows}
        limit={max ?? 2000}
        className={rows === 1 ? undefined : "min-h-[92px]"}
        onLimitReached={(cap: number) =>
          toast.error(`Hier passen höchstens ${cap} Zeichen hinein.`)
        }
      />
      {bad.length > 0 && (
        <span className="flex gap-2 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] p-2.5 text-[11px] text-amber-200/80">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          {bad.join(", ")} ist kein gültiger Platzhalter.
        </span>
      )}
    </Field>
  );
}

function Warnings({
  items,
  onGoSetup,
}: {
  items?: string[];
  onGoSetup: () => void;
}) {
  if (!items?.length) return null;
  return (
    <button
      type="button"
      onClick={onGoSetup}
      className="flex w-full gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/[0.07] p-4 text-left transition hover:bg-amber-500/10"
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
      <span className="min-w-0">
        <span className="block text-sm font-bold text-amber-100">
          {items.length} {items.length === 1 ? "Hinweis" : "Hinweise"} prüfen
        </span>
        <span className="mt-1 block text-xs leading-relaxed text-amber-200/65">
          {items[0]}
        </span>
      </span>
      <span className="ml-auto hidden shrink-0 text-xs font-bold text-amber-300 sm:block">
        Ansehen →
      </span>
    </button>
  );
}

function Detail({ label, value, mono }: any) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] font-bold uppercase tracking-widest text-slate-600">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 truncate text-xs text-slate-300",
          mono && "font-mono",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function formatWhen(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function VerifyPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getVerify(guildId), [guildId]);
  const p = usePanel(load);
  const [tab, setTab] = useState<TabId>("setup");
  const [blacklistId, setBlacklistId] = useState("");
  const [openMember, setOpenMember] = useState<string | null>(null);
  const guard = useSaveGuard(p.dirty, "verify-save-bar");

  if (p.loading) return <Loading />;

  const roleName = p.data?.role_infos?.length
    ? p.data.role_infos
        .filter((role: any) => role?.name)
        .map((role: any) => `@${role.name}`)
        .join(", ")
    : p.data?.role_info?.name
      ? `@${p.data.role_info.name}`
      : "@Verifiziert";
  const serverName = p.data?.guild_name || "deinem Server";
  const blockedGuilds: string[] = p.value("blacklisted_guild_ids") || [];
  const verifiedRoleIds: string[] = (
    p.value("verified_role_ids")?.length
      ? p.value("verified_role_ids")
      : p.value("verified_role_id")
        ? [String(p.value("verified_role_id"))]
        : []
  ).map(String);
  const hasChannel = Boolean(p.value("verification_channel_id"));
  const hasRole = verifiedRoleIds.length > 0;
  const configured = hasChannel && hasRole;
  const active = Boolean(p.value("enabled"));
  const saveBlocked = p.value("server_blacklist_enabled")
    ? blockedGuilds.length === 0
      ? "Füge mindestens einen Server zur aktiven Blacklist hinzu."
      : !p.value("blacklist_log_channel_id")
        ? "Wähle einen Log-Kanal für Blacklist-Ablehnungen."
        : null
    : null;

  const save = () => p.act(() => api.updateVerify(guildId, p.draft));
  const toggleActive = (value: boolean) => {
    if (value && !configured) {
      setTab("setup");
      toast.error("Wähle zuerst einen Verifizierungs-Kanal und eine Rolle.");
      return;
    }
    p.set("enabled", value);
  };
  const setVerifiedRole = (index: number, id: string | null) => {
    const next = [...verifiedRoleIds];
    id = id || "";
    if (
      id &&
      next.some((roleId, roleIndex) => roleId === id && roleIndex !== index)
    ) {
      toast.error("Diese Rolle wurde bereits ausgewählt.");
      return;
    }
    next[index] = id;
    const compact = next.filter(Boolean).slice(0, 3);
    p.set("verified_role_ids", compact);
    p.set("verified_role_id", compact[0] || null);
  };
  const addBlockedGuild = () => {
    const id = blacklistId.trim();
    if (!/^\d{17,20}$/.test(id)) {
      toast.error("Bitte gib eine gültige Discord-Server-ID ein.");
      return;
    }
    if (blockedGuilds.includes(id)) {
      toast.info("Dieser Server steht bereits auf der Blacklist.");
      return;
    }
    p.set("blacklisted_guild_ids", [...blockedGuilds, id]);
    setBlacklistId("");
  };

  const switchTab = (next: TabId) => {
    setTab(next);
    window.requestAnimationFrame(() =>
      document
        .getElementById("verify-workspace")
        ?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  return (
    <section className="space-y-5 pb-4">
      <div className="rounded-3xl border border-slate-800 bg-[#131318] p-4 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-primary/15">
            <ShieldCheck className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-black text-white">Verifizierung</h1>
              <span className="rounded-lg bg-primary/10 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-primary">
                OAuth2
              </span>
            </div>
            <p className="mt-1 text-[12px] text-slate-400">
              Kanal, Rollen und Server-Blacklist verwalten.
            </p>
          </div>
          <SwitchToggle
            checked={active}
            onCheckedChange={toggleActive}
            label="Verifizierung aktivieren oder pausieren"
          />
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-slate-800 bg-[#0e0e12] px-4 py-3">
            <p
              className={cn(
                "text-sm font-black",
                configured ? "text-emerald-300" : "text-amber-300",
              )}
            >
              {configured ? "Bereit" : "Unvollständig"}
            </p>
            <p className="mt-1 text-[10px] text-slate-500">Konfiguration</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-[#0e0e12] px-4 py-3">
            <p className="text-sm font-black text-white">
              {p.data?.verified_count ?? 0}
            </p>
            <p className="mt-1 text-[10px] text-slate-500">
              Verifizierte Nutzer
            </p>
          </div>
        </div>
      </div>

      <Warnings items={p.data?.warnings} onGoSetup={() => switchTab("setup")} />

      {/* Mobile-friendly section navigation. */}
      <nav className="overflow-x-auto rounded-2xl border border-slate-800 bg-[#0e1119] p-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex min-w-max gap-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              type="button"
              key={id}
              onClick={() => switchTab(id)}
              className={cn(
                "flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-xs font-bold transition sm:px-4",
                tab === id
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-900/30"
                  : "text-slate-500 hover:bg-white/[0.04] hover:text-slate-200",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
              {id === "blacklist" && blockedGuilds.length > 0 && (
                <span
                  className={cn(
                    "rounded-full px-1.5 text-[9px]",
                    tab === id ? "bg-white/15" : "bg-slate-800 text-slate-400",
                  )}
                >
                  {blockedGuilds.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </nav>

      <div
        id="verify-workspace"
        className="grid scroll-mt-5 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_360px]"
      >
        <div className="min-w-0 space-y-5">
          {tab === "setup" && (
            <>
              <Section
                icon={Settings2}
                title="Grundkonfiguration"
                subtitle="Kanal und Rolle auswählen – den Rest übernimmt University Bot."
              >
                <Field
                  label="Verifizierungs-Kanal"
                  required
                  hint="Dort wird das öffentliche OAuth2-Panel gepostet."
                >
                  <ChannelPicker
                    guildId={guildId}
                    value={p.value("verification_channel_id") || ""}
                    onChange={(id) => p.set("verification_channel_id", id)}
                    placeholder="Kanal auswählen"
                    channelTypes={["0", "5"]}
                  />
                </Field>

                <div className="space-y-3">
                  <div>
                    <p className="text-xs font-extrabold text-slate-300">
                      Verifiziert-Rollen{" "}
                      <span className="ml-1 text-[10px] font-medium text-slate-600">
                        bis zu 3
                      </span>
                    </p>
                    <p className="mt-1 text-[11px] text-slate-500">
                      Alle ausgewählten Rollen werden nach erfolgreicher Prüfung
                      vergeben.
                    </p>
                  </div>
                  <div className="grid gap-3 md:grid-cols-3">
                    {[0, 1, 2].map((index) => (
                      <Field
                        key={index}
                        label={
                          index === 0 ? "Hauptrolle" : `Zusatzrolle ${index}`
                        }
                        required={index === 0}
                      >
                        <RolePicker
                          guildId={guildId}
                          value={verifiedRoleIds[index] || ""}
                          onChange={(id) => setVerifiedRole(index, id)}
                          placeholder={
                            index === 0 ? "Rolle auswählen" : "Optional"
                          }
                        />
                      </Field>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-black/10 p-4">
                  <Field
                    label="Unverifiziert-Rolle entfernen"
                    hint="Optional: Eine Wartezimmer-Rolle nach erfolgreicher Verifizierung abnehmen."
                  >
                    <RolePicker
                      guildId={guildId}
                      value={p.value("unverified_role_id") || ""}
                      onChange={(id) => p.set("unverified_role_id", id)}
                      placeholder="Keine Rolle"
                    />
                  </Field>
                  {p.value("unverified_role_id") && (
                    <div className="mt-3">
                      <InlineToggle
                        checked={p.value("remove_unverified_role")}
                        onCheckedChange={(value: boolean) =>
                          p.set("remove_unverified_role", value)
                        }
                        label="Nach erfolgreicher Verifizierung entfernen"
                      />
                    </div>
                  )}
                </div>

                <div className="flex flex-col gap-4 rounded-xl border border-blue-500/20 bg-blue-500/[0.06] p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-start gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-500/10 text-blue-400">
                      <Link2 className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">User Pull</p>
                      <p className="mt-1 text-xs leading-5 text-slate-400">
                        Zukünftige OAuth2-Verifizierungen mit einem eigenen
                        Zielserver verbinden.
                      </p>
                    </div>
                  </div>
                  <Link
                    href={`/dashboard/guild/${guildId}/verification/pull`}
                    className="inline-flex min-h-10 shrink-0 items-center justify-center rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-500"
                  >
                    Einrichten
                  </Link>
                </div>

                <div className="grid gap-2 sm:grid-cols-3">
                  {[
                    [hasChannel, "1", "Kanal gewählt"],
                    [hasRole, "2", "Rolle gewählt"],
                    [active, "3", "System aktiviert"],
                  ].map(([done, number, label]) => (
                    <div
                      key={String(number)}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border p-3",
                        done
                          ? "border-emerald-500/20 bg-emerald-500/[0.06]"
                          : "border-slate-800 bg-black/10",
                      )}
                    >
                      <span
                        className={cn(
                          "grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-black",
                          done
                            ? "bg-emerald-500 text-white"
                            : "bg-slate-800 text-slate-500",
                        )}
                      >
                        {done ? <Check className="h-4 w-4" /> : number}
                      </span>
                      <span
                        className={cn(
                          "text-xs font-semibold",
                          done ? "text-emerald-200" : "text-slate-500",
                        )}
                      >
                        {label}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            </>
          )}

          {tab === "blacklist" && (
            <Section
              icon={Server}
              title="Server-Blacklist"
              subtitle="Mitgliedschaften auf ausgewählten Discord-Servern führen automatisch zur Ablehnung."
              tone="rose"
            >
              <InlineToggle
                checked={p.value("server_blacklist_enabled")}
                onCheckedChange={(value: boolean) =>
                  p.set("server_blacklist_enabled", value)
                }
                label="Server-Blacklist aktivieren"
                hint="Diese Liste gilt nur für diesen Discord-Server."
              />

              {p.value("server_blacklist_enabled") ? (
                <>
                  <Field
                    label="Discord-Server hinzufügen"
                    hint="Aktiviere in Discord den Entwicklermodus, rechtsklicke den Server und kopiere seine ID."
                  >
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        className={INPUT}
                        inputMode="numeric"
                        placeholder="Server-ID einfügen"
                        value={blacklistId}
                        onChange={(event) =>
                          setBlacklistId(event.target.value.replace(/\D/g, ""))
                        }
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            addBlockedGuild();
                          }
                        }}
                      />
                      <button
                        type="button"
                        onClick={addBlockedGuild}
                        className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-blue-500"
                      >
                        <Plus className="h-4 w-4" /> Hinzufügen
                      </button>
                    </div>
                  </Field>

                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <p className="text-xs font-bold text-slate-300">
                        Gesperrte Server
                      </p>
                      <span className="text-[10px] text-slate-600">
                        {blockedGuilds.length} von 250
                      </span>
                    </div>
                    {blockedGuilds.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-slate-700 bg-black/10 px-4 py-9 text-center">
                        <Server className="mx-auto h-6 w-6 text-slate-700" />
                        <p className="mt-2 text-sm font-semibold text-slate-400">
                          Die Liste ist noch leer
                        </p>
                        <p className="mt-1 text-[11px] text-slate-600">
                          Füge oben die erste Discord-Server-ID ein.
                        </p>
                      </div>
                    ) : (
                      <div className="grid gap-2 sm:grid-cols-2">
                        {blockedGuilds.map((id, index) => (
                          <div
                            key={id}
                            className="group flex items-center gap-3 rounded-xl border border-slate-800 bg-[#0b0e16] p-3 transition hover:border-rose-500/25"
                          >
                            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-rose-500/10 text-xs font-black text-rose-300">
                              {index + 1}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="text-xs font-semibold text-white">
                                Gesperrter Server
                              </p>
                              <p className="truncate font-mono text-[10px] text-slate-600">
                                {id}
                              </p>
                            </div>
                            <button
                              type="button"
                              aria-label={`Server ${id} entfernen`}
                              onClick={() =>
                                p.set(
                                  "blacklisted_guild_ids",
                                  blockedGuilds.filter((item) => item !== id),
                                )
                              }
                              className="rounded-lg p-2 text-slate-600 transition hover:bg-rose-500/10 hover:text-rose-300"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <Field
                    label="Log-Kanal bei Ablehnung"
                    required
                    hint="Blacklist-Ablehnungen werden auf der Website, per DM und in diesem Kanal gemeldet."
                  >
                    <ChannelPicker
                      guildId={guildId}
                      value={p.value("blacklist_log_channel_id") || ""}
                      onChange={(id) => p.set("blacklist_log_channel_id", id)}
                      placeholder="Log-Kanal auswählen"
                      channelTypes={["0", "5"]}
                    />
                  </Field>

                  <InlineToggle
                    checked={p.value("blacklist_custom_message")}
                    onCheckedChange={(value: boolean) =>
                      p.set("blacklist_custom_message", value)
                    }
                    label="Eigene Ablehnungs-DM verwenden"
                    hint="Ohne eigene Nachricht verwendet University Bot einen klaren Standardtext."
                  />

                  {p.value("blacklist_custom_message") && (
                    <div className="space-y-5 rounded-xl border border-slate-800 bg-black/10 p-4">
                      <TextField
                        label="Überschrift"
                        rows={1}
                        max={200}
                        role={roleName}
                        server={serverName}
                        value={p.value("blacklist_title")}
                        onChange={(value: string) =>
                          p.set("blacklist_title", value)
                        }
                      />
                      <TextField
                        label="Ablehnungstext"
                        rows={4}
                        max={3800}
                        role={roleName}
                        server={serverName}
                        hint="{blocked_server} wird durch den gefundenen Server ersetzt."
                        value={p.value("blacklist_text")}
                        onChange={(value: string) =>
                          p.set("blacklist_text", value)
                        }
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className="flex gap-3 rounded-xl border border-slate-800 bg-black/10 p-4">
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
                  <p className="text-xs text-slate-500">
                    Die Server-Blacklist ist ausgeschaltet. OAuth2 bleibt aktiv.
                  </p>
                </div>
              )}
            </Section>
          )}

          {tab === "messages" && (
            <>
              <Section
                icon={FileText}
                title="Verifizierungs-Panel"
                subtitle="Diese Nachricht sehen neue Mitglieder im Discord-Kanal."
              >
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(p.data?.placeholders || {}).map(
                    ([token, description]) => (
                      <span
                        key={token}
                        title={String(description)}
                        className="rounded-lg border border-slate-800 bg-[#0b0e16] px-2 py-1 font-mono text-[10px] text-slate-400"
                      >
                        {token}
                      </span>
                    ),
                  )}
                </div>
                <TextField
                  label="Überschrift"
                  rows={1}
                  max={200}
                  role={roleName}
                  server={serverName}
                  value={p.value("panel_title")}
                  onChange={(value: string) => p.set("panel_title", value)}
                />
                <TextField
                  label="Beschreibung"
                  rows={4}
                  max={3800}
                  role={roleName}
                  server={serverName}
                  value={p.value("panel_text")}
                  onChange={(value: string) => p.set("panel_text", value)}
                />
                <TextField
                  label="Fußzeile"
                  rows={2}
                  max={3800}
                  role={roleName}
                  server={serverName}
                  value={p.value("panel_footer")}
                  onChange={(value: string) => p.set("panel_footer", value)}
                />
                <Field
                  label="Beschriftung des OAuth-Knopfs"
                  hint="Höchstens 80 Zeichen."
                >
                  <EmojiText
                    value={p.value("button_label") ?? ""}
                    onChange={(value: string) => p.set("button_label", value)}
                    limit={80}
                    onLimitReached={() =>
                      toast.error(
                        "Die Knopfbeschriftung darf höchstens 80 Zeichen haben.",
                      )
                    }
                  />
                </Field>
              </Section>

              <Section
                icon={Mail}
                title="Private Nachrichten"
                subtitle="Optionale Nachricht nach einer erfolgreichen Verifizierung."
                tone="emerald"
              >
                <InlineToggle
                  checked={p.value("dm_on_success")}
                  onCheckedChange={(value: boolean) =>
                    p.set("dm_on_success", value)
                  }
                  label="Erfolgs-DM senden"
                  hint="Geschlossene DMs verhindern die Rollenvergabe nicht."
                />
                {p.value("dm_on_success") && (
                  <TextField
                    label="Text der Erfolgs-DM"
                    rows={4}
                    max={3800}
                    role={roleName}
                    server={serverName}
                    value={p.value("dm_success_text")}
                    onChange={(value: string) =>
                      p.set("dm_success_text", value)
                    }
                  />
                )}
              </Section>
            </>
          )}

          {tab === "advanced" && (
            <>
              <Section
                icon={Clock3}
                title="Zusätzliche Sicherheitsregeln"
                subtitle="Optional – die One-Click-Verifizierung funktioniert auch ohne diese Einstellungen."
                tone="amber"
              >
                <Field
                  label="Mindestalter des Discord-Kontos"
                  hint="0 deaktiviert die Prüfung. Jüngere Konten werden verständlich abgelehnt."
                >
                  <div className="relative">
                    <input
                      type="number"
                      min={0}
                      max={365}
                      className={cn(INPUT, "pr-16")}
                      value={p.value("min_account_age_days") ?? 0}
                      onChange={(event) =>
                        p.set(
                          "min_account_age_days",
                          Number(event.target.value),
                        )
                      }
                    />
                    <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-xs text-slate-600">
                      Tage
                    </span>
                  </div>
                </Field>
              </Section>

              <Section
                icon={Shield}
                title="Kanal sauber halten"
                subtitle="Verhindert Unterhaltungen zwischen dem Verifizierungs-Panel."
                tone="blue"
              >
                <InlineToggle
                  checked={p.value("delete_messages")}
                  onCheckedChange={(value: boolean) =>
                    p.set("delete_messages", value)
                  }
                  label="Mitgliedernachrichten automatisch löschen"
                  hint="Administratoren und Moderatoren bleiben ausgenommen."
                />
                {p.value("delete_messages") && (
                  <InlineToggle
                    checked={p.value("dm_on_delete")}
                    onCheckedChange={(value: boolean) =>
                      p.set("dm_on_delete", value)
                    }
                    label="Person per DM darüber informieren"
                  />
                )}
              </Section>

              <Section
                icon={FileText}
                title="Verifizierungs-Logs"
                subtitle="Die zentrale Bot-Logs-Seite verwaltet erfolgreiche Verifizierungen."
              >
                <LogUmgezogen
                  guildId={guildId}
                  logKey="verification"
                  was="Wer sich erfolgreich verifiziert hat"
                />
              </Section>

              <button
                type="button"
                onClick={() =>
                  p.act(
                    () => api.resetVerify(guildId),
                    "Verifizierung wirklich ausschalten? Deine Texte und Einstellungen bleiben gespeichert.",
                  )
                }
                disabled={p.busy}
                className="w-full rounded-xl border border-rose-500/20 bg-rose-500/[0.06] px-5 py-3.5 text-xs font-black uppercase tracking-widest text-rose-300 transition hover:bg-rose-500/10 disabled:opacity-40"
              >
                Verifizierung vollständig ausschalten
              </button>
            </>
          )}

          {tab === "history" && (
            <Section
              icon={History}
              title="Verifizierungs-Verlauf"
              subtitle="Die letzten zehn erfolgreichen Freischaltungen."
            >
              {(p.data?.recent?.length ?? 0) === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-700 bg-black/10 px-4 py-12 text-center">
                  <History className="mx-auto h-7 w-7 text-slate-700" />
                  <p className="mt-3 text-sm font-semibold text-slate-400">
                    Noch keine Verifizierungen
                  </p>
                  <p className="mt-1 text-[11px] text-slate-600">
                    Sobald jemand den OAuth-Flow abschließt, erscheint die
                    Person hier.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {p.data.recent.map((entry: any, index: number) => {
                    const member = entry.member || {};
                    const key = `${entry.user_id}-${index}`;
                    const open = openMember === key;
                    const label =
                      member.display_name ||
                      member.name ||
                      "Nicht mehr im Server";
                    return (
                      <div
                        key={key}
                        className={cn(
                          "overflow-hidden rounded-xl border bg-[#0b0e16] transition",
                          open ? "border-blue-500/30" : "border-slate-800",
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => setOpenMember(open ? null : key)}
                          className="flex w-full items-center gap-3 p-3.5 text-left"
                        >
                          {member.avatar ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={member.avatar}
                              alt=""
                              className="h-9 w-9 shrink-0 rounded-full"
                            />
                          ) : (
                            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-800">
                              <Shield className="h-4 w-4 text-slate-600" />
                            </div>
                          )}
                          <div className="min-w-0 flex-1">
                            <p
                              className={cn(
                                "truncate text-sm font-semibold",
                                member.left
                                  ? "italic text-slate-500"
                                  : "text-white",
                              )}
                            >
                              {label}
                            </p>
                            <p className="mt-0.5 text-[10px] text-slate-600">
                              {formatWhen(entry.at)}
                            </p>
                          </div>
                          <span className="hidden rounded-lg bg-blue-500/10 px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-blue-300 sm:block">
                            OAuth
                          </span>
                          <ChevronDown
                            className={cn(
                              "h-4 w-4 text-slate-600 transition-transform",
                              open && "rotate-180",
                            )}
                          />
                        </button>
                        {open && (
                          <div className="space-y-4 border-t border-slate-800 p-4">
                            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                              <Detail
                                label="Discord-Name"
                                value={member.name || "unbekannt"}
                              />
                              <Detail
                                label="Anzeigename"
                                value={member.display_name || "—"}
                              />
                              <Detail
                                label="Discord-ID"
                                value={entry.user_id}
                                mono
                              />
                              <Detail label="Methode" value="Discord OAuth2" />
                              <Detail
                                label="Zeitpunkt"
                                value={formatWhen(entry.at)}
                              />
                              <Detail
                                label="Status"
                                value={
                                  member.left
                                    ? "Server verlassen"
                                    : "Auf dem Server"
                                }
                              />
                            </div>
                            {!member.left && (
                              <button
                                type="button"
                                onClick={() =>
                                  p.act(
                                    () =>
                                      api.unverifyMember(
                                        guildId,
                                        entry.user_id,
                                      ),
                                    `${label} die Verifiziert-Rolle wieder abnehmen?`,
                                  )
                                }
                                disabled={p.busy}
                                className="flex w-full items-center justify-center gap-2 rounded-xl border border-rose-500/20 bg-rose-500/[0.06] py-2.5 text-[10px] font-black uppercase tracking-widest text-rose-300 transition hover:bg-rose-500/10 disabled:opacity-40"
                              >
                                <UserMinus className="h-3.5 w-3.5" /> Rolle
                                wieder abnehmen
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </Section>
          )}
        </div>

        {/* Persistent live preview and actions on desktop. */}
        <aside className="space-y-4 xl:sticky xl:top-5">
          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-[#11141d]">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2">
                <Eye className="h-4 w-4 text-blue-300" />
                <p className="text-xs font-bold text-white">Live-Vorschau</p>
              </div>
              <span className="text-[9px] font-bold uppercase tracking-widest text-slate-600">
                Discord
              </span>
            </div>
            <div className="bg-[#090b10] p-4">
              <div className="rounded-lg border-l-4 border-blue-500 bg-[#111318] p-4 shadow-xl">
                <div className="mb-3 flex items-center gap-2.5">
                  <div className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600">
                    <ShieldCheck className="h-5 w-5 text-white" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-white">
                      University Bot{" "}
                      <span className="rounded bg-blue-500 px-1 py-0.5 text-[7px] font-black">
                        APP
                      </span>
                    </p>
                    <p className="text-[9px] text-slate-600">Heute um 12:00</p>
                  </div>
                </div>
                <p className="text-sm font-bold text-white">
                  <DiscordEmojiText
                    text={fill(
                      p.value("panel_title") || "Verifizierung",
                      roleName,
                      serverName,
                    )}
                  />
                </p>
                <p className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-slate-400">
                  <DiscordEmojiText
                    text={fill(
                      p.value("panel_text") ||
                        "Klicke unten, um dich sicher zu verifizieren.",
                      roleName,
                      serverName,
                    )}
                  />
                </p>
                {p.value("panel_footer") && (
                  <p className="mt-3 border-t border-white/[0.06] pt-3 text-[10px] leading-relaxed text-slate-500">
                    <DiscordEmojiText
                      text={fill(p.value("panel_footer"), roleName, serverName)}
                    />
                  </p>
                )}
                <div className="mt-4 grid grid-cols-[1fr_auto] gap-2">
                  <div className="flex items-center justify-center gap-2 rounded-md bg-[#5865f2] px-3 py-2.5 text-[11px] font-bold text-white">
                    <DiscordEmojiText text="<:ztick:1530375424922750977>" />
                    <DiscordEmojiText
                      text={p.value("button_label") || "Verifizieren"}
                    />
                  </div>
                  <div className="flex items-center justify-center gap-1.5 rounded-md bg-[#26272d] px-3 py-2.5 text-[10px] text-slate-500">
                    <DiscordEmojiText text="<:universitybot_mention:1530375331729510430>" />
                    {p.data?.verified_count ?? 0} Nutzer
                  </div>
                </div>
              </div>
              <div className="mt-3 rounded-lg border border-blue-500/10 bg-blue-500/[0.04] p-2 text-center text-[9px] font-bold uppercase tracking-widest text-blue-300">
                OAuth2
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-[#11141d] p-4">
            <p className="text-xs font-bold text-white">
              Panel veröffentlichen
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
              {p.data?.panel_posted
                ? "Das Panel ist bereits online. Nach Änderungen einfach aktualisieren."
                : "Poste das Panel nach dem Speichern in den gewählten Kanal."}
            </p>
            {p.dirty > 0 && (
              <div className="mt-3 flex gap-2 rounded-lg border border-amber-500/15 bg-amber-500/[0.05] p-2.5 text-[10px] text-amber-200/70">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> Vor dem
                Posten erst speichern.
              </div>
            )}
            <div className="mt-4 space-y-2">
              <button
                type="button"
                onClick={() => p.act(() => api.postVerifyPanel(guildId))}
                disabled={p.busy || !configured || p.dirty > 0}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-3 text-xs font-black text-white shadow-lg shadow-blue-900/25 transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-35"
              >
                <Send className="h-4 w-4" />{" "}
                {p.data?.panel_posted
                  ? "Panel aktualisieren"
                  : "Panel jetzt posten"}
              </button>
              <button
                type="button"
                onClick={() =>
                  p.act(() => api.previewVerifyPanel(guildId, p.draft))
                }
                disabled={p.busy || !hasChannel}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-700 bg-white/[0.025] py-3 text-xs font-bold text-slate-400 transition hover:border-slate-600 hover:text-white disabled:opacity-35"
              >
                <Eye className="h-4 w-4" /> Test-Vorschau senden
              </button>
              <button
                type="button"
                onClick={p.reload}
                disabled={p.busy}
                className="flex w-full items-center justify-center gap-2 py-2 text-[10px] font-bold text-slate-600 transition hover:text-slate-300 disabled:opacity-35"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Daten neu laden
              </button>
            </div>
          </div>
        </aside>
      </div>

      <StickySaveBar
        id="verify-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        blocked={saveBlocked}
        onDiscard={p.discard}
        onSave={save}
      />
    </section>
  );
}
