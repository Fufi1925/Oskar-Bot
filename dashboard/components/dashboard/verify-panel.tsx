"use client";

/**
 * Verification.
 *
 * Rebuilt because the old form could set five things and nothing else:
 * a channel, a role, a log channel, the method and an on/off switch.
 * Every word the bot said was hard-coded English inside the cog, and
 * there was no way to stop it sending direct messages.
 *
 * The layout follows what was asked for: the texts you actually want to
 * change sit at the top, everything else lives behind "Erweitert" so
 * the common case stays a short page.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Eye,
  Loader2,
  Lock,
  Mail,
  MessageSquare,
  Plus,
  RefreshCw,
  Save,
  Send,
  Server,
  Shield,
  ShieldCheck,
  Trash2,
  UserMinus,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
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
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

function Field({ label, hint, children }: any) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && (
        <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>
      )}
    </div>
  );
}

function Card({ icon: Icon, title, subtitle, children, onReload }: any) {
  return (
    <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3 min-w-0">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white">{title}</p>
            {subtitle && (
              <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {onReload && (
          <button
            onClick={onReload}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] shrink-0"
          >
            <RefreshCw className="h-4 w-4 text-primary" />
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function Warnings({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
      <div className="text-[12px] text-amber-200/80 leading-relaxed">
        <span className="font-bold">Das läuft so nicht rund:</span>
        <br />
        {items.map((w, i) => (
          <span key={i}>
            • {w}
            <br />
          </span>
        ))}
      </div>
    </div>
  );
}

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
  return Array.from(new Set(found.filter((f) => !KNOWN.includes(f))));
}

/** A text box that shows what the result will look like. */
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
      {/* Alle Verify-Texte laufen durch dieses eine Feld -- Ueberschrift,
          Beschreibung, Fusszeile, die Meldung danach. Die Emoji-Auswahl
          hier einzubauen deckt sie deshalb alle auf einmal ab, statt
          fuenfmal dasselbe zu wiederholen. */}
      <EmojiText
        value={value ?? ""}
        onChange={onChange}
        rows={rows === 1 ? undefined : rows}
        limit={max ?? 2000}
        className={rows === 1 ? undefined : "min-h-[80px]"}
        onLimitReached={(cap: number) =>
          toast.error(`Hier passen höchstens ${cap} Zeichen hinein.`)
        }
      />
      {bad.length > 0 && (
        <p className="text-[11px] text-amber-300/80">
          {bad.join(", ")} gibt es nicht — bleibt so stehen, wie du es getippt
          hast.
        </p>
      )}
      {String(value ?? "").trim() && (
        <div className="rounded-xl bg-[#0e0e12] border border-slate-800 px-3.5 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-1">
            Vorschau
          </p>
          <p className="text-[13px] text-slate-200 whitespace-pre-wrap leading-relaxed">
            <DiscordEmojiText text={fill(value, role, server)} />
          </p>
        </div>
      )}
    </Field>
  );
}

function Detail({ label, value, mono }: any) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] uppercase tracking-widest text-slate-600">
        {label}
      </p>
      <p
        className={cn(
          "text-[12px] text-slate-200 truncate",
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
  const [advanced, setAdvanced] = useState(false);
  const [openMember, setOpenMember] = useState<string | null>(null);
  const [blacklistId, setBlacklistId] = useState("");

  // Flash the bar red instead of a browser dialog: the dialog cannot
  // be styled, and half the time the browser suppresses it anyway.
  const guard = useSaveGuard(p.dirty, "verify-save-bar");

  if (p.loading) return <Loading />;

  const roleName = p.data?.role_info?.name
    ? `@${p.data.role_info.name}`
    : "@Verifiziert";
  const serverName = p.data?.channel_info?.name
    ? "deinem Server"
    : "deinem Server";
  const blockedGuilds: string[] = p.value("blacklisted_guild_ids") || [];

  const addBlockedGuild = () => {
    const id = blacklistId.trim();
    if (!/^\d{17,20}$/.test(id)) {
      toast.error("Bitte gib eine gültige Discord-Server-ID ein.");
      return;
    }
    if (!blockedGuilds.includes(id))
      p.set("blacklisted_guild_ids", [...blockedGuilds, id]);
    setBlacklistId("");
  };

  const save = () => p.act(() => api.updateVerify(guildId, p.draft));

  return (
    <section className="space-y-5">
      <Warnings items={p.data?.warnings} />

      {/* ── Basics ─────────────────────────────────────────────── */}
      <Card
        icon={ShieldCheck}
        title="Verifizierung"
        subtitle="Neue Mitglieder müssen sich freischalten, bevor sie den Server sehen."
        onReload={p.reload}
      >
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">
              {p.data?.configured ? "Bereit" : "Unvollständig"}
            </p>
            <p className="text-[11px] text-slate-500">Status</p>
          </div>
          <div className="bg-[#0e0e12] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
              {p.data?.verified_count ?? 0}
            </p>
            <p className="text-[11px] text-slate-500">Bisher verifiziert</p>
          </div>
        </div>

        <InlineToggle
          checked={p.value("enabled")}
          onCheckedChange={(v: boolean) => p.set("enabled", v)}
          label="Verifizierung aktiv"
        />

        <Field
          label="Kanal"
          hint="Hier steht das Panel. Der Bot braucht dort Schreibrechte."
        >
          <ChannelPicker
            guildId={guildId}
            value={p.value("verification_channel_id") || ""}
            onChange={(id) => p.set("verification_channel_id", id)}
            placeholder="Kanal wählen"
            channelTypes={["0", "5"]}
          />
        </Field>

        <Field
          label="Rolle nach dem Verifizieren"
          hint="Die Bot-Rolle muss in den Servereinstellungen über dieser stehen."
        >
          <RolePicker
            guildId={guildId}
            value={p.value("verified_role_id") || ""}
            onChange={(id) => p.set("verified_role_id", id)}
            placeholder="Rolle wählen"
          />
        </Field>

        <div className="rounded-2xl border border-blue-400/20 bg-blue-500/[0.07] p-4">
          <div className="flex gap-3">
            <Shield className="mt-0.5 h-5 w-5 shrink-0 text-blue-300" />
            <div>
              <p className="text-sm font-bold text-white">
                One-Click über Discord OAuth2
              </p>
              <p className="mt-1 text-[12px] leading-relaxed text-slate-400">
                Die Person klickt einmal und erlaubt ausschließlich das Lesen
                ihrer Discord-Identität und Servermitgliedschaften. CAPTCHA,
                Passwortzugriff und dauerhaft gespeicherte OAuth-Tokens gibt es
                nicht.
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* ── Texts ──────────────────────────────────────────────── */}
      <Card
        icon={MessageSquare}
        title="Texte"
        subtitle="Was im Panel steht. Platzhalter werden beim Senden ersetzt."
      >
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(p.data?.placeholders || {}).map(([token, desc]) => (
            <span
              key={token}
              title={String(desc)}
              className="px-2 py-1 rounded-lg bg-[#0e0e12] border border-slate-800 text-[11px] font-mono text-slate-400"
            >
              {token}
            </span>
          ))}
        </div>

        <TextField
          label="Überschrift"
          rows={1}
          max={200}
          role={roleName}
          server={serverName}
          value={p.value("panel_title")}
          onChange={(v: string) => p.set("panel_title", v)}
        />

        <TextField
          label="Text"
          rows={4}
          max={3800}
          role={roleName}
          server={serverName}
          value={p.value("panel_text")}
          onChange={(v: string) => p.set("panel_text", v)}
        />

        <TextField
          label="Fußzeile"
          rows={2}
          max={3800}
          role={roleName}
          server={serverName}
          hint="Steht unter dem Text, meist der Hinweis auf die Rolle."
          value={p.value("panel_footer")}
          onChange={(v: string) => p.set("panel_footer", v)}
        />

        <Field
          label="Knopf: Mit Discord verifizieren"
          hint="Höchstens 80 Zeichen."
        >
          <EmojiText
            value={p.value("button_label") ?? ""}
            onChange={(next: string) => p.set("button_label", next)}
            limit={80}
            onLimitReached={(cap: number) =>
              toast.error(
                `Eine Knopfbeschriftung darf höchstens ${cap} Zeichen haben.`,
              )
            }
          />
        </Field>

        <TextField
          label="Meldung nach dem Verifizieren"
          rows={3}
          max={3800}
          role={roleName}
          server={serverName}
          hint="Sieht nur die Person selbst, direkt nach dem Klick."
          value={p.value("success_text")}
          onChange={(v: string) => p.set("success_text", v)}
        />
      </Card>

      {/* ── Direct messages ────────────────────────────────────── */}
      <Card
        icon={Mail}
        title="Private Nachrichten"
        subtitle="Was der Bot den Leuten direkt schreibt."
      >
        <InlineToggle
          checked={p.value("dm_on_success")}
          onCheckedChange={(v: boolean) => p.set("dm_on_success", v)}
          label="DM nach erfolgreicher Verifizierung"
          hint="Aus: die Person sieht nur die kurze Meldung im Kanal."
        />

        {p.value("dm_on_success") && (
          <TextField
            label="Text der Erfolgs-DM"
            rows={3}
            max={3800}
            role={roleName}
            server={serverName}
            hint="Wer seine DMs zu hat, bekommt sie nicht — das ist kein Fehler und blockiert die Verifizierung nicht."
            value={p.value("dm_success_text")}
            onChange={(v: string) => p.set("dm_success_text", v)}
          />
        )}
      </Card>

      {/* ── Per-server membership blacklist ───────────────────── */}
      <Card
        icon={Server}
        title="Server-Blacklist"
        subtitle="Lehne Personen ab, die Mitglied eines von dir gesperrten Discord-Servers sind."
      >
        <InlineToggle
          checked={p.value("server_blacklist_enabled")}
          onCheckedChange={(v: boolean) => p.set("server_blacklist_enabled", v)}
          label="Server-Blacklist verwenden"
          hint="Die Liste gilt ausschließlich für diesen Server."
        />

        {p.value("server_blacklist_enabled") && (
          <>
            <Field
              label="Gesperrten Server hinzufügen"
              hint="Servereinstellungen → Erweitert → Entwicklermodus aktivieren, dann den Server rechtsklicken und die ID kopieren."
            >
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  className={INPUT}
                  inputMode="numeric"
                  placeholder="Discord-Server-ID"
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
                  className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-bold text-white hover:bg-blue-500"
                >
                  <Plus className="h-4 w-4" /> Hinzufügen
                </button>
              </div>
            </Field>

            <div className="space-y-2">
              {blockedGuilds.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-800 px-4 py-7 text-center text-sm text-slate-500">
                  Noch kein Discord-Server gesperrt.
                </div>
              ) : (
                blockedGuilds.map((id) => (
                  <div
                    key={id}
                    className="flex items-center gap-3 rounded-xl border border-slate-800 bg-[#0e0e12] p-3"
                  >
                    <div className="grid h-9 w-9 place-items-center rounded-lg bg-rose-500/10">
                      <Server className="h-4 w-4 text-rose-300" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-white">
                        Gesperrter Server
                      </p>
                      <p className="truncate font-mono text-[11px] text-slate-500">
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
                      className="rounded-lg p-2 text-slate-500 hover:bg-rose-500/10 hover:text-rose-300"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))
              )}
            </div>

            <Field
              label="Log-Kanal bei Ablehnung"
              hint="Website, DM und dieser Server-Log werden bei einem Treffer benachrichtigt."
            >
              <ChannelPicker
                guildId={guildId}
                value={p.value("blacklist_log_channel_id") || ""}
                onChange={(id) => p.set("blacklist_log_channel_id", id)}
                placeholder="Log-Kanal wählen"
                channelTypes={["0", "5"]}
              />
            </Field>

            <InlineToggle
              checked={p.value("blacklist_custom_message")}
              onCheckedChange={(v: boolean) =>
                p.set("blacklist_custom_message", v)
              }
              label="Eigene Ablehnungsnachricht"
              hint="Diese Nachricht erscheint in der DM. Die öffentliche University-Seite zeigt weiterhin einen klaren Ablehnungsstatus."
            />
            {p.value("blacklist_custom_message") && (
              <div className="space-y-4 rounded-2xl border border-slate-800 bg-black/10 p-4">
                <TextField
                  label="Überschrift"
                  rows={1}
                  max={200}
                  role={roleName}
                  server={serverName}
                  value={p.value("blacklist_title")}
                  onChange={(v: string) => p.set("blacklist_title", v)}
                />
                <TextField
                  label="Ablehnungstext"
                  rows={4}
                  max={3800}
                  role={roleName}
                  server={serverName}
                  hint="Mit {blocked_server} zeigst du den gefundenen Server an."
                  value={p.value("blacklist_text")}
                  onChange={(v: string) => p.set("blacklist_text", v)}
                />
              </div>
            )}
          </>
        )}
      </Card>

      {/* ── Panel actions ──────────────────────────────────────── */}
      <Card
        icon={Send}
        title="Panel"
        subtitle="Die Nachricht mit den Knöpfen im Kanal."
      >
        {p.dirty > 0 && (
          <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5">
            <p className="text-[12px] text-amber-200/80">
              Du hast ungespeicherte Änderungen. Erst speichern, sonst wird das
              Panel mit den alten Texten gepostet.
            </p>
          </div>
        )}

        <button
          onClick={() => p.act(() => api.postVerifyPanel(guildId))}
          disabled={p.busy || !p.data?.configured}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
        >
          <Send className="h-3.5 w-3.5" />
          {p.data?.panel_posted ? "Panel auffrischen" : "Panel posten"}
        </button>

        <button
          onClick={() => p.act(() => api.previewVerifyPanel(guildId, p.draft))}
          disabled={p.busy || !p.data?.verification_channel_id}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white disabled:opacity-40 transition-all"
        >
          <Eye className="h-3.5 w-3.5" />
          Vorschau senden (Knöpfe ohne Funktion)
        </button>
      </Card>

      {/* ── Advanced ───────────────────────────────────────────── */}
      <div className="bg-[#131318] border border-slate-800 rounded-3xl overflow-hidden">
        <button
          onClick={() => setAdvanced((a) => !a)}
          className="w-full flex items-center justify-between px-6 py-5"
        >
          <div className="flex gap-3 items-center min-w-0">
            <div className="h-10 w-10 rounded-2xl bg-white/[0.04] grid place-items-center shrink-0">
              <Lock className="h-5 w-5 text-slate-400" />
            </div>
            <div className="text-left min-w-0">
              <p className="font-black text-white">Erweitert</p>
              <p className="text-[12px] text-slate-500 mt-0.5">
                Log-Kanal, Wartezimmer-Rolle, Mindestalter. Braucht man selten.
              </p>
            </div>
          </div>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-slate-500 shrink-0 transition-transform",
              advanced && "rotate-180",
            )}
          />
        </button>

        {advanced && (
          <div className="px-6 pb-6 space-y-5 border-t border-slate-800 pt-5">
            {/* Der Log-Kanal liegt jetzt gesammelt unter Bot-Logs.
                Ihn hier stehen zu lassen hiesse zwei Felder fuer
                denselben Wert -- und eines zeigt nach dem Speichern
                am anderen Ort etwas Veraltetes. */}
            <LogUmgezogen
              guildId={guildId}
              logKey="verification"
              was="Wer sich verifiziert hat"
            />

            <Field
              label="Unverifiziert-Rolle"
              hint="Wenn dein Server neue Mitglieder erst mit einer Sperr-Rolle empfängt, kann der Bot sie nach dem Verifizieren wieder abnehmen."
            >
              <RolePicker
                guildId={guildId}
                value={p.value("unverified_role_id") || ""}
                onChange={(id) => p.set("unverified_role_id", id)}
                placeholder="Keine"
              />
            </Field>

            {p.value("unverified_role_id") && (
              <InlineToggle
                checked={p.value("remove_unverified_role")}
                onCheckedChange={(v: boolean) =>
                  p.set("remove_unverified_role", v)
                }
                label="Diese Rolle nach dem Verifizieren abnehmen"
              />
            )}

            <Field
              label="Mindestalter des Kontos (Tage)"
              hint="0 = aus. Hält frisch erstellte Wegwerf-Konten draußen. Wer darunter liegt, bekommt eine Erklärung statt einer Rolle."
            >
              <input
                type="number"
                min={0}
                max={365}
                className={INPUT}
                value={p.value("min_account_age_days") ?? 0}
                onChange={(e) =>
                  p.set("min_account_age_days", Number(e.target.value))
                }
              />
            </Field>

            <InlineToggle
              checked={p.value("delete_messages")}
              onCheckedChange={(v: boolean) => p.set("delete_messages", v)}
              label="Fremde Nachrichten im Kanal löschen"
              hint="Hält den Verifizierungs-Kanal sauber. Braucht „Nachrichten verwalten“."
            />

            {p.value("delete_messages") && (
              <InlineToggle
                checked={p.value("dm_on_delete")}
                onCheckedChange={(v: boolean) => p.set("dm_on_delete", v)}
                label="Dabei eine DM schicken"
                hint="Aus: die Nachricht verschwindet kommentarlos. Auf großen Servern angenehmer."
              />
            )}

            <button
              onClick={() =>
                p.act(
                  () => api.resetVerify(guildId),
                  "Verifizierung ausschalten? Deine Texte bleiben gespeichert.",
                )
              }
              disabled={p.busy}
              className="w-full py-3 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-xs font-black uppercase tracking-widest text-red-300 hover:bg-red-500/10 disabled:opacity-40 transition-all"
            >
              Ausschalten
            </button>
          </div>
        )}
      </div>

      {/* ── Recent ─────────────────────────────────────────────── */}
      {(p.data?.recent?.length ?? 0) > 0 && (
        <Card
          icon={Shield}
          title="Zuletzt verifiziert"
          subtitle="Die letzten zehn Freischaltungen."
        >
          <div className="space-y-2">
            {p.data.recent.map((entry: any, i: number) => {
              const m = entry.member || {};
              const key = `${entry.user_id}-${i}`;
              const open = openMember === key;
              const label = m.display_name || m.name || "Nicht mehr im Server";

              return (
                <div
                  key={key}
                  className={cn(
                    "rounded-xl border transition-colors",
                    open
                      ? "bg-[#0e0e12] border-primary/40"
                      : "bg-[#0e0e12] border-slate-800",
                  )}
                >
                  <button
                    onClick={() => setOpenMember(open ? null : key)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-left"
                  >
                    {m.avatar ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={m.avatar}
                        alt=""
                        className="h-7 w-7 rounded-full shrink-0"
                      />
                    ) : (
                      <div className="h-7 w-7 rounded-full bg-slate-800 grid place-items-center shrink-0">
                        <Shield className="h-3.5 w-3.5 text-slate-600" />
                      </div>
                    )}

                    <span
                      className={cn(
                        "text-[13px] truncate flex-1 min-w-0",
                        m.left ? "text-slate-500 italic" : "text-white",
                      )}
                    >
                      {label}
                    </span>

                    <span className="text-[11px] text-slate-500 shrink-0 hidden sm:block">
                      {entry.method}
                    </span>
                    <ChevronDown
                      className={cn(
                        "h-3.5 w-3.5 text-slate-600 shrink-0 transition-transform",
                        open && "rotate-180",
                      )}
                    />
                  </button>

                  {open && (
                    <div className="px-4 pb-4 pt-1 space-y-3 border-t border-slate-800/70">
                      <div className="grid sm:grid-cols-2 gap-x-4 gap-y-2 pt-3">
                        <Detail
                          label="Discord-Name"
                          value={m.name || "unbekannt"}
                        />
                        <Detail
                          label="Anzeigename"
                          value={m.display_name || "—"}
                        />
                        {/* Shown as text, not a number: JavaScript rounds
                            a 19-digit id and the last digits change. */}
                        <Detail label="ID" value={entry.user_id} mono />
                        <Detail label="Methode" value={entry.method} />
                        <Detail label="Wann" value={formatWhen(entry.at)} />
                        <Detail
                          label="Status"
                          value={m.left ? "Server verlassen" : "Auf dem Server"}
                        />
                      </div>

                      {!m.left && (
                        <button
                          onClick={() =>
                            p.act(
                              () => api.unverifyMember(guildId, entry.user_id),
                              `${label} die Verifiziert-Rolle wieder abnehmen?`,
                            )
                          }
                          disabled={p.busy}
                          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-[11px] font-black uppercase tracking-widest text-red-300 hover:bg-red-500/10 disabled:opacity-40 transition-all"
                        >
                          <UserMinus className="h-3.5 w-3.5" />
                          Rolle wieder abnehmen
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <StickySaveBar
        id="verify-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={save}
      />
    </section>
  );
}
