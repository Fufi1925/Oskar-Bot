"use client";

/**
 * Join to Create, voice roles and custom role commands.
 *
 * All three replace hand-written forms that quietly disagreed with the
 * bot: the voice-role page showed an on/off switch the cog never read,
 * and the custom-roles page listed five fixed English slots while the
 * bot's real feature was free-form named commands.
 *
 * Every panel surfaces the `warnings` array the API returns. Most
 * "I set it and nothing happens" reports come down to a missing
 * permission or a role sitting above the bot, and the backend already
 * knows about both.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, Hash, Info, Loader2, Lock, Mic, Plus, RefreshCw, Save,
  Send, Trash2, Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ChannelPicker, RolePicker, MultiRolePicker, MultiChannelPicker,
} from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import {
  Loading, StickySaveBar, usePanel, useSaveGuard,
} from "@/components/dashboard/save-bar";

const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

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

function Warn({ children }: any) {
  return (
    <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
      <div className="text-[12px] text-amber-200/80 leading-relaxed">{children}</div>
    </div>
  );
}

function Warnings({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <Warn>
      <span className="font-bold">Das läuft nicht rund:</span>
      <br />
      {items.map((w, i) => (
        <span key={i}>
          • {w}
          <br />
        </span>
      ))}
    </Warn>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Voice roles
 * ══════════════════════════════════════════════════════════════════ */

export function VoiceRolePanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getVoiceRole(guildId), [guildId]);
  const p = usePanel(load);
  // Must run before the early return below -- hooks cannot be conditional.
  const guard = useSaveGuard(p.dirty, "voicerole-save-bar");

  if (p.loading) return <Loading />;

  const roles: string[] = p.value("roles") || [];
  const channels: string[] = p.value("channels") || [];

  return (
    <section className="space-y-5">
      <Warnings items={p.data?.warnings} />

      <Card
        icon={Volume2}
        title="Sprach-Rolle"
        subtitle="Wer in einem Sprachkanal sitzt, bekommt eine Rolle — und verliert sie beim Verlassen wieder."
        onReload={p.reload}
      >
        <InlineToggle
          checked={p.value("enabled")}
          onCheckedChange={(v: boolean) => p.set("enabled", v)}
          label="Sprach-Rollen aktiv"
        />

        <Field
          label="Rollen"
          hint="Alle gewählten Rollen werden gleichzeitig vergeben. Die Bot-Rolle muss in den Servereinstellungen über ihnen stehen."
        >
          <MultiRolePicker
            guildId={guildId}
            value={roles}
            onChange={(ids) => p.set("roles", ids)}
            placeholder="Rollen wählen"
          />
        </Field>

        <Field
          label="Nur diese Kanäle"
          hint="Leer lassen = gilt für alle Sprachkanäle."
        >
          <MultiChannelPicker
            guildId={guildId}
            value={channels}
            onChange={(ids) => p.set("channels", ids)}
            placeholder="Alle Sprachkanäle"
            channelTypes={["2", "13"]}
          />
        </Field>

        {p.data?.has_afk_channel && (
          <InlineToggle
            checked={p.value("ignore_afk")}
            onCheckedChange={(v: boolean) => p.set("ignore_afk", v)}
            label="AFK-Kanal ausnehmen"
            hint="Wer im AFK-Kanal geparkt wird, bekommt keine Rolle."
          />
        )}

        <InlineToggle
          checked={p.value("include_stage")}
          onCheckedChange={(v: boolean) => p.set("include_stage", v)}
          label="Bühnen-Kanäle mitzählen"
          hint="Aus: nur normale Sprachkanäle lösen die Rolle aus."
        />

      </Card>

      <StickySaveBar
        id="voicerole-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={() => p.act(() => api.updateVoiceRole(guildId, p.draft))}
      />
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Custom role commands
 * ══════════════════════════════════════════════════════════════════ */

export function CustomRolesPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getCustomRoles(guildId), [guildId]);
  const p = usePanel(load);
  const guard = useSaveGuard(p.dirty, "customroles-save-bar");
  const [name, setName] = useState("");
  const [roleId, setRoleId] = useState("");

  if (p.loading) return <Loading />;

  const prefix = p.data?.prefix || ">";
  const entries: any[] = p.data?.entries || [];
  const migrated: string[] = p.data?.migrated || [];

  const add = async () => {
    const clean = name.trim().toLowerCase();
    if (!clean) return toast.error("Gib dem Befehl einen Namen.");
    if (!roleId) return toast.error("Wähle eine Rolle.");
    await p.act(() => api.addCustomRole(guildId, { name: clean, role_id: roleId }));
    setName("");
    setRoleId("");
  };

  return (
    <section className="space-y-5">
      {migrated.length > 0 && (
        <Warn>
          Die früheren festen Rollen ({migrated.join(", ")}) sind jetzt ganz
          normale Befehle in der Liste unten. Du kannst sie umbenennen oder
          löschen — vorher ging das nicht.
        </Warn>
      )}

      <Warnings items={p.data?.warnings} />

      <Card
        icon={Hash}
        title="Eigene Rollen-Befehle"
        subtitle={`Ein Befehl pro Rolle. ${prefix}name @user gibt die Rolle — nochmal ausgeführt nimmt sie wieder weg.`}
        onReload={p.reload}
      >
        <div className="grid sm:grid-cols-[1fr_1fr_auto] gap-3 items-end">
          <Field label="Befehlsname">
            <input
              className={INPUT}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. gamer"
              maxLength={24}
            />
          </Field>
          <Field label="Rolle">
            <RolePicker
              guildId={guildId}
              value={roleId}
              onChange={(id) => setRoleId(id || "")}
              placeholder="Rolle wählen"
            />
          </Field>
          <button
            onClick={add}
            disabled={p.busy}
            className="h-[48px] px-5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest flex items-center gap-2 hover:brightness-110 disabled:opacity-40 transition-all"
          >
            <Plus className="h-3.5 w-3.5" />
            Anlegen
          </button>
        </div>

        <p className="text-[11px] text-slate-600">
          Kleinbuchstaben, Zahlen, - und _ — keine Leerzeichen. Namen, die
          der Bot schon selbst benutzt, werden abgelehnt.
        </p>

        <div className="space-y-2 pt-2">
          {entries.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-8">
              Noch kein Befehl angelegt.
            </p>
          ) : (
            entries.map((entry) => (
              <div
                key={entry.name}
                className={cn(
                  "flex items-center gap-3 rounded-xl border px-4 py-3",
                  entry.problem
                    ? "bg-amber-500/[0.04] border-amber-500/20"
                    : "bg-[#0e0e12] border-slate-800"
                )}
              >
                <code className="text-sm font-bold text-primary shrink-0">
                  {entry.command}
                </code>
                <span className="text-slate-600 shrink-0">→</span>
                <span className="text-sm text-slate-300 truncate flex-1">
                  {entry.role?.name ? (
                    <span className="flex items-center gap-1.5">
                      <span
                        className="h-2 w-2 rounded-full shrink-0"
                        style={{
                          background: entry.role.colour
                            ? `#${Number(entry.role.colour).toString(16).padStart(6, "0")}`
                            : "#94a3b8",
                        }}
                      />
                      {entry.role.name}
                    </span>
                  ) : (
                    <span className="text-amber-300">Rolle gelöscht</span>
                  )}
                </span>
                {entry.problem && (
                  <span className="text-[11px] text-amber-300/80 hidden md:block max-w-[280px] truncate">
                    {entry.problem}
                  </span>
                )}
                <button
                  onClick={() =>
                    p.act(
                      () => api.deleteCustomRole(guildId, entry.name),
                      `Befehl „${entry.name}" löschen? Die Rolle selbst bleibt.`
                    )
                  }
                  disabled={p.busy}
                  className="p-2 rounded-lg bg-white/[0.03] border border-white/10 text-slate-500 hover:text-red-400 disabled:opacity-40 shrink-0"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))
          )}
        </div>

        {entries.length > 0 && (
          <p className="text-[11px] text-slate-600">
            {entries.length} von {p.data?.max_commands ?? 56} Befehlen belegt.
          </p>
        )}
      </Card>

      <Card
        icon={Lock}
        title="Wer darf das benutzen?"
        subtitle="Ohne berechtigte Rolle können nur Admins und der Serverinhaber die Befehle nutzen."
      >
        <Field
          label="Berechtigte Rolle"
          hint="Serverinhaber und Admins dürfen immer — auch ohne diese Rolle."
        >
          <RolePicker
            guildId={guildId}
            value={p.value("reqrole") || ""}
            onChange={(id) => p.set("reqrole", id)}
            placeholder="Keine — nur Admins"
          />
        </Field>

      </Card>

      <StickySaveBar
        id="customroles-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={() =>
          p.act(() => api.updateCustomRoles(guildId, { reqrole: p.value("reqrole") }))
        }
      />
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════ *
 * Join to Create
 * ══════════════════════════════════════════════════════════════════ */

export function J2CPanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getJ2C(guildId), [guildId]);
  const p = usePanel(load);
  const guard = useSaveGuard(p.dirty, "j2c-save-bar");

  if (p.loading) return <Loading />;

  const template = String(p.value("name_template") ?? "{user}'s VC");
  const preview = template
    .replace(/\{user\.display\}/g, "Lena")
    .replace(/\{user\.name\}/g, "Lena")
    .replace(/\{user\}/g, "Lena")
    .replace(/\{count\}/g, String((p.data?.active_channels ?? 0) + 1));

  return (
    <section className="space-y-5">
      <Warnings items={p.data?.warnings} />

      <Card
        icon={Mic}
        title="Join to Create"
        subtitle="Wer die Lobby betritt, bekommt automatisch einen eigenen Sprachkanal — und der verschwindet wieder, sobald er leer ist."
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
            <p className="text-lg font-black text-white">
              {p.data?.active_channels ?? 0}
            </p>
            <p className="text-[11px] text-slate-500">Offene Kanäle</p>
          </div>
        </div>

        <Field
          label="Lobby-Kanal"
          hint="Der Sprachkanal, den man betritt, um einen eigenen zu bekommen."
        >
          <ChannelPicker
            guildId={guildId}
            value={p.value("join_channel_id") || ""}
            onChange={(id) => p.set("join_channel_id", id)}
            placeholder="Sprachkanal wählen"
            channelTypes={["2"]}
          />
        </Field>

        <Field
          label="Kanal für das Bedienfeld"
          hint="Textkanal, in dem die Knöpfe zum Verwalten stehen."
        >
          <ChannelPicker
            guildId={guildId}
            value={p.value("control_channel_id") || ""}
            onChange={(id) => p.set("control_channel_id", id)}
            placeholder="Textkanal wählen"
            channelTypes={["0", "5"]}
          />
        </Field>

        <Field
          label="Kategorie"
          hint="Wo die neuen Kanäle landen. Leer = dieselbe Kategorie wie die Lobby. Discord erlaubt 50 Kanäle je Kategorie."
        >
          <ChannelPicker
            guildId={guildId}
            value={p.value("category_id") || ""}
            onChange={(id) => p.set("category_id", id)}
            placeholder="Wie die Lobby"
            channelTypes={["4"]}
          />
        </Field>

      </Card>

      <Card
        icon={Info}
        title="Wie die neuen Kanäle aussehen"
        subtitle="Gilt für jeden Kanal, der ab jetzt erstellt wird."
      >
        <Field label="Name" hint="Platzhalter: {user}, {user.display}, {count}">
          <input
            className={INPUT}
            value={template}
            onChange={(e) => p.set("name_template", e.target.value)}
            placeholder="{user}'s VC"
            maxLength={100}
          />
        </Field>

        <div className="rounded-xl bg-[#0e0e12] border border-slate-800 px-4 py-3">
          <p className="text-[11px] text-slate-500 mb-1">Vorschau</p>
          <p className="text-sm text-white flex items-center gap-1.5">
            <Volume2 className="h-3.5 w-3.5 text-slate-500" />
            {preview || "—"}
          </p>
        </div>

        <Field
          label="Platzgrenze"
          hint="0 heißt unbegrenzt. Discord erlaubt höchstens 99."
        >
          <input
            type="number"
            min={0}
            max={99}
            className={INPUT}
            value={p.value("default_limit") ?? 2}
            onChange={(e) => p.set("default_limit", Number(e.target.value))}
          />
        </Field>

        <InlineToggle
          checked={p.value("default_locked")}
          onCheckedChange={(v: boolean) => p.set("default_locked", v)}
          label="Neue Kanäle sofort abschließen"
          hint="An: nur der Ersteller kommt rein, bis er jemanden einlädt."
        />

      </Card>

      <Card
        icon={Send}
        title="Bedienfeld"
        subtitle="Die Knopfleiste, mit der Mitglieder ihren Kanal verwalten."
      >
        <button
          onClick={() => p.act(() => api.postJ2CPanel(guildId))}
          disabled={p.busy || !p.data?.control_channel_id}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white disabled:opacity-40 transition-all"
        >
          <Send className="h-3.5 w-3.5" />
          Bedienfeld posten oder auffrischen
        </button>

        <button
          onClick={() =>
            p.act(
              () => api.resetJ2C(guildId),
              "Join to Create ausschalten? Bereits erstellte Kanäle bleiben bestehen."
            )
          }
          disabled={p.busy}
          className="w-full py-3 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-xs font-black uppercase tracking-widest text-red-300 hover:bg-red-500/10 disabled:opacity-40 transition-all"
        >
          Ausschalten
        </button>
      </Card>

      <StickySaveBar
        id="j2c-save-bar"
        count={p.dirty}
        busy={p.busy}
        shake={guard.shake}
        onDiscard={p.discard}
        onSave={() => p.act(() => api.updateJ2C(guildId, p.draft))}
      />
    </section>
  );
}
