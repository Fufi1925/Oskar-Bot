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
  AlertTriangle, CheckCircle2, ChevronDown, Eye, Loader2, Lock, Mail,
  MessageSquare, RefreshCw, Save, Send, Shield, ShieldCheck, UserMinus, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker, RolePicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import {
  Loading, StickySaveBar, usePanel, useSaveGuard,
} from "@/components/dashboard/save-bar";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

function Field({ label, hint, children }: any) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>}
    </div>
  );
}

function Card({ icon: Icon, title, subtitle, children, onReload }: any) {
  return (
    <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
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

const KNOWN = ["{server}", "{user}", "{user.name}", "{role}", "{member_count}"];

function fill(text: string, role: string, server: string) {
  return String(text ?? "")
    .replace(/\{server\}/g, server)
    .replace(/\{user\.name\}/g, "Lena")
    .replace(/\{user\}/g, "@Lena")
    .replace(/\{role\}/g, role)
    .replace(/\{member_count\}/g, "1.204");
}

function unknownPlaceholders(text: string): string[] {
  const found = String(text ?? "").match(/\{[a-z_.]+\}/g) || [];
  return Array.from(new Set(found.filter((f) => !KNOWN.includes(f))));
}

/** A text box that shows what the result will look like. */
function TextField({ label, hint, value, onChange, rows = 3, role, server, max }: any) {
  const bad = unknownPlaceholders(value);
  return (
    <Field label={label} hint={hint}>
      {rows === 1 ? (
        <input
          className={INPUT}
          value={value ?? ""}
          maxLength={max}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <textarea
          className={cn(INPUT, "resize-y min-h-[80px]")}
          rows={rows}
          value={value ?? ""}
          maxLength={max}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {bad.length > 0 && (
        <p className="text-[11px] text-amber-300/80">
          {bad.join(", ")} gibt es nicht — bleibt so stehen, wie du es getippt hast.
        </p>
      )}
      {String(value ?? "").trim() && (
        <div className="rounded-xl bg-[#0a1628] border border-slate-800 px-3.5 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-1">
            Vorschau
          </p>
          <p className="text-[13px] text-slate-200 whitespace-pre-wrap leading-relaxed">
            {fill(value, role, server)}
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
          mono && "font-mono"
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
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

const METHODS = [
  {
    id: "button",
    label: "Nur Knopf",
    desc: "Ein Klick reicht. Am bequemsten, hält aber Bots kaum auf.",
  },
  {
    id: "captcha",
    label: "Nur CAPTCHA",
    desc: "Code per DM lösen. Sicherer, aber wer DMs zu hat, kommt nicht rein.",
  },
  {
    id: "both",
    label: "Beides anbieten",
    desc: "Die Person wählt selbst.",
  },
];

export function VerifyPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getVerify(guildId), [guildId]);
  const p = usePanel(load);
  const [advanced, setAdvanced] = useState(false);
  const [openMember, setOpenMember] = useState<string | null>(null);

  // Flash the bar red instead of a browser dialog: the dialog cannot
  // be styled, and half the time the browser suppresses it anyway.
  const guard = useSaveGuard(p.dirty, "verify-save-bar");

  if (p.loading) return <Loading />;

  const roleName = p.data?.role_info?.name
    ? `@${p.data.role_info.name}`
    : "@Verifiziert";
  const serverName = p.data?.channel_info?.name ? "deinem Server" : "deinem Server";
  const method = p.value("verification_method") || "both";

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
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
            <p className="text-lg font-black text-white">
              {p.data?.configured ? "Bereit" : "Unvollständig"}
            </p>
            <p className="text-[11px] text-slate-500">Status</p>
          </div>
          <div className="bg-[#0d1b31] border border-slate-800 rounded-2xl px-4 py-3">
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

        <Field label="Wie soll verifiziert werden?">
          <div className="grid sm:grid-cols-3 gap-2">
            {METHODS.map((o) => (
              <button
                key={o.id}
                onClick={() => p.set("verification_method", o.id)}
                className={cn(
                  "text-left rounded-2xl border p-4 transition-all",
                  method === o.id
                    ? "bg-primary/10 border-primary/40"
                    : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                )}
              >
                <p className="text-sm font-bold text-white">{o.label}</p>
                <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                  {o.desc}
                </p>
              </button>
            ))}
          </div>
        </Field>

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
              className="px-2 py-1 rounded-lg bg-[#0d1b31] border border-slate-800 text-[11px] font-mono text-slate-400"
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

        <div className="grid sm:grid-cols-2 gap-4">
          {(method === "button" || method === "both") && (
            <Field label="Knopf: Verifizieren" hint="Höchstens 80 Zeichen.">
              <input
                className={INPUT}
                maxLength={80}
                value={p.value("button_label") ?? ""}
                onChange={(e) => p.set("button_label", e.target.value)}
              />
            </Field>
          )}
          {(method === "captcha" || method === "both") && (
            <Field label="Knopf: CAPTCHA" hint="Höchstens 80 Zeichen.">
              <input
                className={INPUT}
                maxLength={80}
                value={p.value("captcha_label") ?? ""}
                onChange={(e) => p.set("captcha_label", e.target.value)}
              />
            </Field>
          )}
        </div>

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

        {(method === "captcha" || method === "both") && (
          <Field
            label="Antwortmöglichkeiten beim CAPTCHA"
            hint="Statt den Code abzutippen, wählt die Person aus einer Liste. Weniger Auswahl heißt: leichter zu raten."
          >
            <div className="grid grid-cols-4 sm:grid-cols-7 gap-2">
              {[2, 3, 4, 5, 6, 7, 8].map((n) => (
                <button
                  key={n}
                  onClick={() => p.set("captcha_choices", n)}
                  className={cn(
                    "rounded-xl border py-2.5 text-sm font-bold transition-all",
                    (p.value("captcha_choices") ?? 5) === n
                      ? "bg-primary/10 border-primary/40 text-white"
                      : "bg-[#0d1b31] border-slate-800 text-slate-400 hover:border-slate-700"
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-slate-600">
              Bei {p.value("captcha_choices") ?? 5} Möglichkeiten liegt eine
              blinde Vermutung bei{" "}
              {Math.round(100 / (p.value("captcha_choices") ?? 5))}%. Ein
              falscher Versuch beendet den Vorgang.
            </p>
          </Field>
        )}

        {(method === "captcha" || method === "both") && (
          <div className="rounded-xl bg-white/[0.02] border border-white/5 p-3.5">
            <p className="text-[11px] text-slate-500 leading-relaxed">
              <b className="text-slate-400">Zum CAPTCHA:</b> Das Bild geht
              zwangsläufig per DM raus — sonst könnten andere mitlesen. Wer
              keine DMs annimmt, kann diesen Weg nicht nutzen. Stell
              &bdquo;Beides anbieten&ldquo; ein, damit solche Leute trotzdem
              reinkommen.
            </p>
          </div>
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
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden">
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
              advanced && "rotate-180"
            )}
          />
        </button>

        {advanced && (
          <div className="px-6 pb-6 space-y-5 border-t border-slate-800 pt-5">
            <Field
              label="Log-Kanal"
              hint="Jede Verifizierung wird hier protokolliert. Leer = kein Log."
            >
              <ChannelPicker
                guildId={guildId}
                value={p.value("log_channel_id") || ""}
                onChange={(id) => p.set("log_channel_id", id)}
                placeholder="Kein Log"
                channelTypes={["0", "5"]}
              />
            </Field>

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
                onCheckedChange={(v: boolean) => p.set("remove_unverified_role", v)}
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
                  "Verifizierung ausschalten? Deine Texte bleiben gespeichert."
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
                      ? "bg-[#0a1628] border-primary/40"
                      : "bg-[#0d1b31] border-slate-800"
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
                        m.left ? "text-slate-500 italic" : "text-white"
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
                        open && "rotate-180"
                      )}
                    />
                  </button>

                  {open && (
                    <div className="px-4 pb-4 pt-1 space-y-3 border-t border-slate-800/70">
                      <div className="grid sm:grid-cols-2 gap-x-4 gap-y-2 pt-3">
                        <Detail label="Discord-Name" value={m.name || "unbekannt"} />
                        <Detail label="Anzeigename" value={m.display_name || "—"} />
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
                              `${label} die Verifiziert-Rolle wieder abnehmen?`
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
