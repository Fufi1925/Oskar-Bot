"use client";

/**
 * The welcome message, editable in full.
 *
 * What this replaces: a form with six fields, in English, where the
 * channel came from a plain <Select> (which turned the channel id into a
 * JavaScript number and corrupted it), the embed's author and footer
 * could not be set at all, and the only "preview" was posting into a
 * real channel.
 *
 * Now every field the bot reads is here, the preview renders next to the
 * form as you type, and the placeholders can be inserted by clicking
 * them rather than being typed from memory.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AtSign, Eye, Image as ImageIcon, Loader2, MessageSquare, Save, Send,
  Sparkles, Trash2, Type,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker } from "@/components/dashboard/pickers";
import { WelcomeConfig } from "@/types/api";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";
import { EmojiText } from "@/components/dashboard/emoji-field";

const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

/** Exactly the placeholders utils/greet_render.py understands. */
const TOKENS = [
  { token: "{user}", hint: "Erwähnt das Mitglied", sample: "@Neuer" },
  { token: "{user_name}", hint: "Benutzername", sample: "neuer" },
  { token: "{user_nick}", hint: "Anzeigename", sample: "Neuer" },
  { token: "{user_id}", hint: "ID des Mitglieds", sample: "123456789012345678" },
  { token: "{user_avatar}", hint: "Link zum Profilbild", sample: "https://cdn.discordapp.com/…" },
  { token: "{user_createdate}", hint: "Account erstellt am", sample: "Mo, Jan 08, 2024" },
  { token: "{user_joindate}", hint: "Beigetreten am", sample: "Fr, Jul 25, 2026" },
  { token: "{server_name}", hint: "Servername", sample: "Mein Server" },
  { token: "{server_membercount}", hint: "Mitgliederzahl", sample: "1.204" },
  { token: "{server_icon}", hint: "Link zum Serverbild", sample: "https://cdn.discordapp.com/…" },
];

/**
 * Die Vorlagen, falls der Bot nicht antwortet.
 *
 * Sie kommen normalerweise von `/compose/templates/welcome`, damit die
 * Emoji-Codes aus derselben Quelle stammen wie die Auswahl
 * (`utils/emoji.py`). Eine zweite, hier gepflegte Liste liefe beim
 * ersten neuen Emoji auseinander -- genau dieser Fehler stand schon
 * einmal im Changelog, als vier Emojis auf geloeschte IDs zeigten und
 * als roher Text erschienen.
 *
 * Dieser Rueckfall traegt deshalb bewusst **keine** Emojis: ein hier
 * eingefrorener Code waere die zweite Quelle, die vermieden werden
 * soll. Ohne Verbindung bekommt man schlichte Vorlagen -- brauchbar,
 * nur ohne Bild.
 */
const FALLBACK_TEMPLATES = [
  {
    name: "Kurz & freundlich",
    type: "simple",
    message:
      "Willkommen {user} auf **{server_name}**! Du bist Mitglied Nummer {server_membercount}.",
  },
  {
    name: "Mit Bild",
    type: "embed",
    embed: {
      title: "Willkommen auf {server_name}!",
      description:
        "Schön, dass du da bist, {user}!\n\nSchau dich ruhig um — du bist unser {server_membercount}. Mitglied.",
      color: "#5865f2",
      thumbnail: "{user_avatar}",
      footer_text: "Beigetreten am {user_joindate}",
    },
  },
  {
    name: "Sachlich",
    type: "embed",
    embed: {
      title: "Neues Mitglied",
      description: "{user} ist dem Server beigetreten.",
      color: "#2f3136",
      footer_text: "Mitglied #{server_membercount}",
    },
  },
];

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

/** Fill the placeholders the same way the bot does, for the preview. */
function fillTokens(text: string) {
  let out = text || "";
  for (const t of TOKENS) {
    out = out.split(t.token).join(t.sample);
  }
  return out;
}

function isImage(url: string) {
  const filled = fillTokens(url || "");
  return /^https?:\/\//.test(filled);
}

export function WelcomeForm({
  initialConfig,
  guildId,
}: {
  initialConfig: WelcomeConfig;
  channels?: any[];
  guildId: string;
}) {
  const [config, setConfig] = useState<WelcomeConfig>(initialConfig);
  const [saved, setSaved] = useState<WelcomeConfig>(initialConfig);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const lastFocused = useRef<HTMLTextAreaElement | HTMLInputElement | null>(null);

  // Die Vorlagen vom Bot holen. Er liest die Emoji-Codes aus
  // `utils/emoji.py` -- dieselbe Quelle wie die Auswahl. Schlaegt der
  // Aufruf fehl, bleiben die schlichten Vorlagen oben stehen.
  const [templates, setTemplates] = useState<any[]>(FALLBACK_TEMPLATES);
  useEffect(() => {
    let alive = true;
    api
      .getWelcomeTemplates()
      .then((answer: any) => {
        if (alive && Array.isArray(answer?.templates) && answer.templates.length) {
          setTemplates(answer.templates);
        }
      })
      .catch(() => {
        // Kein Fehler fuer den Nutzer: die Vorlagen sind eine Abkuerzung,
        // keine Voraussetzung. Die schlichten tun es auch.
      });
    return () => {
      alive = false;
    };
  }, []);

  // Memoised: a fresh `{}` on every render would make the preview below
  // recompute constantly.
  const embed = useMemo(
    () => (config.embed_data || {}) as Record<string, any>,
    [config.embed_data]
  );
  const isEmbed = (config.welcome_type || "simple") === "embed";

  // How many top-level fields differ from what is on the server. The
  // whole embed counts as one -- reporting "7 changes" because seven
  // embed keys moved would be noise.
  const dirty = useMemo(() => {
    const keys = new Set([...Object.keys(config), ...Object.keys(saved)]);
    let count = 0;
    for (const key of keys) {
      const a = (config as any)[key];
      const b = (saved as any)[key];
      if (JSON.stringify(a ?? null) !== JSON.stringify(b ?? null)) count += 1;
    }
    return count;
  }, [config, saved]);

  const guard = useSaveGuard(dirty, "welcome-save-bar");

  const setEmbed = (patch: any) =>
    setConfig({ ...config, embed_data: { ...embed, ...patch } });

  /** Insert a placeholder where the cursor last was. */
  const insert = (token: string) => {
    const el = lastFocused.current;
    if (!el) return toast.info("Erst in ein Textfeld klicken, dann den Platzhalter.");
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? start;
    const next = el.value.slice(0, start) + token + el.value.slice(end);
    // React does not see a direct .value write, so dispatch an input event.
    const setter = Object.getOwnPropertyDescriptor(
      el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype,
      "value"
    )?.set;
    setter?.call(el, next);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.focus();
    el.setSelectionRange(start + token.length, start + token.length);
  };

  const track = {
    onFocus: (e: any) => { lastFocused.current = e.target; },
  };

  const save = async () => {
    if (!config.channel_id) {
      return toast.error("Bitte zuerst einen Kanal wählen.");
    }
    setSaving(true);
    try {
      await api.updateWelcome(guildId, config);
      setSaved(config);
      toast.success("Begrüßung gespeichert.");
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  };

  /** Post it into the channel exactly as a member would see it. */
  const sendTest = async () => {
    if (!config.channel_id) {
      return toast.error("Bitte zuerst einen Kanal wählen.");
    }
    setTesting(true);
    try {
      const res = await api.testWelcome(guildId, config.channel_id, {
        welcome_type: config.welcome_type || "simple",
        welcome_message: config.welcome_message || "",
        embed_data: config.embed_data || null,
      });
      toast.success(res?.result || "Vorschau gesendet.");
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht gesendet werden.");
    } finally {
      setTesting(false);
    }
  };

  const preview = useMemo(() => ({
    content: fillTokens(
      isEmbed ? embed.message || "" : config.welcome_message || ""
    ),
    title: fillTokens(embed.title || ""),
    description: fillTokens(embed.description || ""),
    footer: fillTokens(embed.footer_text || ""),
    author: fillTokens(embed.author_name || ""),
    thumbnail: fillTokens(embed.thumbnail || ""),
    image: fillTokens(embed.image || ""),
    colour: embed.color || "#5865f2",
  }), [config, embed, isEmbed]);

  return (
    <div className="space-y-5">
    <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
      {/* ══ Form ═══════════════════════════════════════ */}
      <div className="xl:col-span-3 space-y-6">
        <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
          <Field label="Kanal" hint="Hier landet die Begrüßung.">
            <ChannelPicker
              guildId={guildId}
              value={config.channel_id || ""}
              onChange={(id) => setConfig({ ...config, channel_id: id || null })}
              placeholder="Kanal wählen"
              channelTypes={["0", "5"]}
            />
          </Field>

          <Field label="Art der Nachricht">
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: "simple", icon: MessageSquare, label: "Nur Text", desc: "Eine normale Nachricht" },
                { id: "embed", icon: Sparkles, label: "Als Karte", desc: "Mit Rahmen, Bild und Farbe" },
              ].map((o) => (
                <button
                  key={o.id}
                  onClick={() => setConfig({ ...config, welcome_type: o.id })}
                  className={cn(
                    "text-left rounded-2xl border p-4 transition-all",
                    (config.welcome_type || "simple") === o.id
                      ? "bg-primary/10 border-primary/40"
                      : "bg-[#0e0e12] border-slate-800 hover:border-slate-700"
                  )}
                >
                  <o.icon className={cn(
                    "h-4 w-4 mb-2",
                    (config.welcome_type || "simple") === o.id ? "text-primary" : "text-slate-500"
                  )} />
                  <p className="text-sm font-bold text-white">{o.label}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">{o.desc}</p>
                </button>
              ))}
            </div>
          </Field>

          <Field
            label="Nach X Sekunden löschen"
            hint="0 heißt: die Begrüßung bleibt stehen."
          >
            <input
              type="number"
              min={0}
              value={config.auto_delete_duration || 0}
              onChange={(e) =>
                setConfig({
                  ...config,
                  auto_delete_duration: Math.max(0, Number(e.target.value) || 0),
                })
              }
              className={INPUT}
            />
          </Field>
        </div>

        {/* Placeholders */}
        <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-3">
          <div>
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Platzhalter
            </p>
            <p className="text-[11px] text-slate-600 mt-1.5">
              Ins Textfeld klicken, dann hier auf einen Platzhalter — er wird
              an der Cursorstelle eingefügt.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {TOKENS.map((t) => (
              <button
                key={t.token}
                title={`${t.hint} → ${t.sample}`}
                onClick={() => insert(t.token)}
                className="px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] font-mono text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
              >
                {t.token}
              </button>
            ))}
          </div>
        </div>

        {/* Text */}
        {!isEmbed && (
          <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6">
            <Field label="Nachricht">
              <EmojiText
                {...track}
                value={config.welcome_message || ""}
                onChange={(next) =>
                  setConfig({ ...config, welcome_message: next })
                }
                rows={5}
                limit={2000}
                showCount
                placeholder="Willkommen {user} auf {server_name}!"
                onLimitReached={(max) =>
                  toast.error(`Das passt nicht mehr in ${max} Zeichen.`)
                }
              />
            </Field>
          </div>
        )}

        {/* Embed */}
        {isEmbed && (
          <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5">
            <Field
              label="Text über der Karte"
              hint="Optional. Nützlich, um jemanden zu pingen — in der Karte selbst gibt es keine Benachrichtigung."
            >
              <EmojiText
                {...track}
                value={embed.message || ""}
                onChange={(next) => setEmbed({ message: next })}
                limit={2000}
                placeholder="{user}"
                onLimitReached={(max) =>
                  toast.error(`Das passt nicht mehr in ${max} Zeichen.`)
                }
              />
            </Field>

            <div className="grid md:grid-cols-2 gap-5">
              <Field label="Überschrift">
                <EmojiText
                  {...track}
                  value={embed.title || ""}
                  onChange={(next) => setEmbed({ title: next })}
                  limit={256}
                  placeholder="Willkommen auf {server_name}!"
                  onLimitReached={(max) =>
                    toast.error(`Eine Überschrift darf höchstens ${max} Zeichen haben.`)
                  }
                />
              </Field>
              <Field label="Farbe">
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={
                      /^#[0-9a-f]{6}$/i.test(embed.color || "")
                        ? embed.color
                        : "#5865f2"
                    }
                    onChange={(e) => setEmbed({ color: e.target.value })}
                    className="h-11 w-14 rounded-xl bg-transparent border border-slate-800 cursor-pointer p-1 shrink-0"
                  />
                  <input
                    value={embed.color || ""}
                    onChange={(e) => setEmbed({ color: e.target.value })}
                    placeholder="#5865f2"
                    className={cn(INPUT, "font-mono")}
                  />
                </div>
              </Field>
            </div>

            <Field label="Beschreibung">
              <EmojiText
                {...track}
                value={embed.description || ""}
                onChange={(next) => setEmbed({ description: next })}
                rows={4}
                limit={4096}
                showCount
                placeholder="Schön, dass du da bist, {user}!"
                onLimitReached={(max) =>
                  toast.error(`Die Beschreibung darf höchstens ${max} Zeichen haben.`)
                }
              />
            </Field>

            <div className="border-t border-slate-800 pt-5 space-y-5">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
                <AtSign className="h-3.5 w-3.5" /> Kopfzeile
              </p>
              <div className="grid md:grid-cols-2 gap-5">
                <Field label="Name">
                  <EmojiText
                    {...track}
                    value={embed.author_name || ""}
                    onChange={(next) => setEmbed({ author_name: next })}
                    limit={256}
                    placeholder="{user_name}"
                    onLimitReached={(max) =>
                      toast.error(`Die Kopfzeile darf höchstens ${max} Zeichen haben.`)
                    }
                  />
                </Field>
                <Field label="Bild daneben" hint="Muss mit https:// anfangen.">
                  <input
                    {...track}
                    value={embed.author_icon || ""}
                    onChange={(e) => setEmbed({ author_icon: e.target.value })}
                    placeholder="{user_avatar}"
                    className={INPUT}
                  />
                </Field>
              </div>
            </div>

            <div className="border-t border-slate-800 pt-5 space-y-5">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
                <Type className="h-3.5 w-3.5" /> Fußzeile
              </p>
              <div className="grid md:grid-cols-2 gap-5">
                <Field label="Text">
                  <EmojiText
                    {...track}
                    value={embed.footer_text || ""}
                    onChange={(next) => setEmbed({ footer_text: next })}
                    limit={2048}
                    placeholder="Mitglied #{server_membercount}"
                    onLimitReached={(max) =>
                      toast.error(`Die Fußzeile darf höchstens ${max} Zeichen haben.`)
                    }
                  />
                </Field>
                <Field label="Bild daneben">
                  <input
                    {...track}
                    value={embed.footer_icon || ""}
                    onChange={(e) => setEmbed({ footer_icon: e.target.value })}
                    placeholder="{server_icon}"
                    className={INPUT}
                  />
                </Field>
              </div>
            </div>

            <div className="border-t border-slate-800 pt-5 space-y-5">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
                <ImageIcon className="h-3.5 w-3.5" /> Bilder
              </p>
              <div className="grid md:grid-cols-2 gap-5">
                <Field label="Kleines Bild oben rechts">
                  <input
                    {...track}
                    value={embed.thumbnail || ""}
                    onChange={(e) => setEmbed({ thumbnail: e.target.value })}
                    placeholder="{user_avatar}"
                    className={INPUT}
                  />
                </Field>
                <Field label="Großes Bild unten">
                  <input
                    {...track}
                    value={embed.image || ""}
                    onChange={(e) => setEmbed({ image: e.target.value })}
                    placeholder="https://…"
                    className={INPUT}
                  />
                </Field>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ══ Preview + actions ══════════════════════════ */}
      <div className="xl:col-span-2 space-y-5">
        <div className="xl:sticky xl:top-6 space-y-5">
          <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
              <Eye className="h-3.5 w-3.5" /> Vorschau
            </p>

            <div className="rounded-2xl bg-[#313338] p-4 space-y-2">
              {preview.content && (
                <p className="text-sm text-[#dbdee1] whitespace-pre-line break-words">
                  {preview.content}
                </p>
              )}

              {isEmbed ? (
                <div
                  className="rounded border-l-4 bg-[#2b2d31] p-3.5 space-y-2"
                  style={{
                    borderLeftColor: /^#[0-9a-f]{6}$/i.test(preview.colour)
                      ? preview.colour
                      : "#5865f2",
                  }}
                >
                  <div className="flex gap-3">
                    <div className="min-w-0 flex-1 space-y-1.5">
                      {preview.author && (
                        <p className="text-xs font-semibold text-white">
                          {preview.author}
                        </p>
                      )}
                      {preview.title && (
                        <p className="text-[15px] font-bold text-white break-words">
                          {preview.title}
                        </p>
                      )}
                      {preview.description && (
                        <p className="text-sm text-[#dbdee1] whitespace-pre-line break-words">
                          {preview.description}
                        </p>
                      )}
                    </div>
                    {isImage(preview.thumbnail) && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={preview.thumbnail}
                        alt=""
                        className="h-16 w-16 rounded object-cover shrink-0"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                      />
                    )}
                  </div>

                  {isImage(preview.image) && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={preview.image}
                      alt=""
                      className="w-full rounded object-cover max-h-48"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                    />
                  )}

                  {preview.footer && (
                    <p className="text-[11px] text-[#949ba4] break-words">
                      {preview.footer}
                    </p>
                  )}
                </div>
              ) : (
                !preview.content && (
                  <p className="text-sm text-slate-600 italic">
                    Noch kein Text eingetragen.
                  </p>
                )
              )}
            </div>

            <p className="text-[11px] text-slate-600 leading-relaxed">
              Die Platzhalter sind hier mit Beispielwerten gefüllt. Wie es
              wirklich aussieht, zeigt &bdquo;In den Kanal senden&ldquo;.
            </p>
          </div>

          {/* The save button used to live here, four screens below the
              field you were editing. It is one bar at the bottom now. */}
          <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-3">
            <button
              onClick={sendTest}
              disabled={testing}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all"
            >
              {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              In den Kanal senden
            </button>
            <p className="text-[11px] text-slate-600 text-center">
              Sendet den aktuellen Stand — auch ungespeichert.
            </p>
          </div>

          <div className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-3">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Vorlagen
            </p>
            {templates.map((t: any) => (
              <button
                key={t.name}
                onClick={() =>
                  setConfig({
                    ...config,
                    welcome_type: t.type,
                    ...(t.type === "simple"
                      ? { welcome_message: t.message }
                      : { embed_data: t.embed as any }),
                  })
                }
                className="w-full text-left px-4 py-3 rounded-xl bg-[#0e0e12] border border-slate-800 text-sm text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
              >
                {t.name}
              </button>
            ))}

            <button
              onClick={() =>
                setConfig({
                  ...config,
                  welcome_message: "",
                  embed_data: null,
                })
              }
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-[11px] font-black uppercase tracking-widest text-slate-500 hover:text-red-400 transition-all"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Texte leeren
            </button>
          </div>
        </div>
      </div>
      </div>

      <StickySaveBar
        id="welcome-save-bar"
        count={dirty}
        busy={saving}
        shake={guard.shake}
        blocked={!config.channel_id ? "Ohne Kanal kann nichts gespeichert werden." : null}
        onDiscard={() => setConfig(saved)}
        onSave={save}
      />
    </div>
  );
}
