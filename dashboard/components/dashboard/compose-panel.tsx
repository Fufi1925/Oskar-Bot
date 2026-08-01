"use client";

/**
 * Design a message and post it as the bot.
 *
 * Three kinds: plain text, a classic embed, or a Components V2 layout
 * built from blocks the author arranges themselves.
 *
 * The preview is rendered to look like Discord rather than like the
 * dashboard, because the whole question somebody has here is "what will
 * this look like over there".
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowDown, ArrowUp, Check, Copy, Eye, FileText, Image as ImageIcon,
  Layers, Link2, Loader2, Minus, MousePointerClick, Pencil, Plus, Send,
  Sparkles, Trash2, Type, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChannelPicker } from "@/components/dashboard/pickers";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { announcementsFor } from "@/lib/announcements";

const INPUT =
  "w-full bg-[#0d1b31] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors";

type Kind = "text" | "embed" | "v2";

interface Block {
  id: number;
  type: "text" | "divider" | "image" | "buttons";
  text?: string;
  url?: string;
  invisible?: boolean;
  buttons?: { label: string; url: string; emoji?: string }[];
}

let nextId = 1;

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

/**
 * Discord renders **bold**, *italic*, `code`, __underline__, three
 * levels of heading and small text.
 *
 * The headings were missing here, so a preview of "# Titel" showed the
 * hash as literal text while Discord would have rendered a heading --
 * the preview was lying about what would be posted.
 */
function markdown(text: string) {
  const escaped = (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .replace(/```([\s\S]*?)```/g, '<pre class="bg-black/40 rounded p-2 my-1 text-[12px] overflow-x-auto">$1</pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-black/40 rounded px-1">$1</code>')
    // Headings first: they are line-anchored, and running them after
    // the inline rules would let a bold marker split the line.
    .replace(/^### (.*)$/gm, '<span class="block font-bold text-[15px] mt-2">$1</span>')
    .replace(/^## (.*)$/gm, '<span class="block font-bold text-[17px] mt-2">$1</span>')
    .replace(/^# (.*)$/gm, '<span class="block font-bold text-[20px] mt-2">$1</span>')
    .replace(/^-# (.*)$/gm, '<span class="block text-[11px] text-slate-400">$1</span>')
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/__([^_]+)__/g, "<u>$1</u>")
    .replace(/\*([^*]+)\*/g, "<i>$1</i>")
    .replace(/^&gt; (.*)$/gm, '<span class="border-l-2 border-slate-600 pl-2 block">$1</span>')
    .replace(/\n/g, "<br/>");
}

export function ComposePanel({ guildId }: { guildId: string }) {
  const [kind, setKind] = useState<Kind>("text");
  const [channelId, setChannelId] = useState("");
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const [sent, setSent] = useState<{ url: string; id: string } | null>(null);

  // text
  const [content, setContent] = useState("");

  // embed
  const [embed, setEmbed] = useState<any>({
    title: "", description: "", color: "#5865f2",
    footer_text: "", author_name: "", image: "", thumbnail: "",
    fields: [] as any[],
  });

  // v2
  const [blocks, setBlocks] = useState<Block[]>([
    { id: nextId++, type: "text", text: "**Überschrift**\nDein Text hier." },
  ]);
  const [accent, setAccent] = useState("#5865f2");

  const [allowMentions, setAllowMentions] = useState(false);
  const [pin, setPin] = useState(false);

  /**
   * Which bot posts.
   *
   * Only the support server has a second one; everywhere else this
   * comes back with a single option and the picker stays hidden rather
   * than showing a choice of one.
   */
  const [senders, setSenders] = useState<any[]>([]);
  const [sender, setSender] = useState("main");

  useEffect(() => {
    let cancelled = false;
    api
      .getSenders(guildId)
      .then((res) => {
        if (!cancelled) setSenders(res?.options || []);
      })
      .catch(() => {
        // A missing list is not worth an error toast -- the tab works
        // fine with just the main bot.
        if (!cancelled) setSenders([]);
      });
    return () => {
      cancelled = true;
    };
  }, [guildId]);

  const payload = useMemo(() => {
    const base: any = {
      kind, channel_id: channelId, allow_mentions: allowMentions, pin, sender,
    };
    if (kind === "text") base.content = content;
    if (kind === "embed") base.embed = embed;
    if (kind === "v2") {
      base.color = accent;
      base.blocks = blocks.map(({ id, ...rest }) => rest);
    }
    return base;
  }, [kind, channelId, content, embed, blocks, accent, allowMentions, pin, sender]);

  // Check as you type, but not on every keystroke.
  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const res = await api.checkMessage(guildId, payload);
        setProblems(res.problems || []);
      } catch {
        setProblems([]);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [guildId, payload]);

  const send = async () => {
    if (!channelId) return toast.error("Bitte einen Kanal auswählen.");
    setBusy(true);
    try {
      const res = await api.sendComposed(guildId, payload);
      toast.success(res?.result || "Gesendet.");
      setSent({ url: res.url, id: res.message_id });
    } catch (err: any) {
      toast.error(err?.message || "Senden fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  // ── block helpers ────────────────────────────────────────────────
  const addBlock = (type: Block["type"]) =>
    setBlocks((b) => [
      ...b,
      type === "buttons"
        ? { id: nextId++, type, buttons: [{ label: "Mehr erfahren", url: "https://" }] }
        : { id: nextId++, type, text: "", url: "" },
    ]);

  const patchBlock = (id: number, patch: Partial<Block>) =>
    setBlocks((b) => b.map((x) => (x.id === id ? { ...x, ...patch } : x)));

  const removeBlock = (id: number) =>
    setBlocks((b) => b.filter((x) => x.id !== id));

  const moveBlock = (id: number, delta: number) =>
    setBlocks((b) => {
      const index = b.findIndex((x) => x.id === id);
      const target = index + delta;
      if (index < 0 || target < 0 || target >= b.length) return b;
      const copy = [...b];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });

  /**
   * Prepared changelog posts, and only on the server they belong to.
   *
   * Everywhere else this is an empty list and the card below is not
   * rendered at all -- a stranger's server has no use for "the bot got
   * a database" and should not have to scroll past it.
   */
  const announcements = announcementsFor(guildId);

  const loadAnnouncement = (entry: (typeof announcements)[number]) => {
    setKind("v2");
    setAccent(entry.accent);
    setBlocks(entry.blocks.map((block) => ({ ...block, id: nextId++ })));
    setSent(null);
    toast.success(`„${entry.label}" geladen — Kanal wählen und senden.`);
  };

  return (
    <section className="grid xl:grid-cols-5 gap-6">
      {/* ══ Editor ═══════════════════════════════════ */}
      <div className="xl:col-span-3 space-y-5">
        {announcements.length > 0 && (
          <div className="bg-[#10233f] border border-primary/25 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card">
            <div className="flex gap-3">
              <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
                <Sparkles className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="font-black text-white">Fertige Ankündigungen</p>
                <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
                  Nur auf diesem Server sichtbar. Laden, Kanal wählen,
                  senden — vorher lässt sich noch alles ändern.
                </p>
              </div>
            </div>

            <div className="space-y-2">
              {announcements.map((entry) => (
                <button
                  key={entry.id}
                  onClick={() => loadAnnouncement(entry)}
                  className="w-full text-left rounded-2xl border border-slate-800 bg-[#0d1b31] px-4 py-3 hover:border-primary/40 transition-colors"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-bold text-white">{entry.label}</p>
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                      {entry.date}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {entry.summary}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
          <Field label="Art der Nachricht">
            <div className="grid md:grid-cols-3 gap-2">
              {[
                { id: "text", icon: Type, label: "Nur Text", desc: "Eine ganz normale Nachricht" },
                { id: "embed", icon: FileText, label: "Embed", desc: "Rahmen, Felder, Bilder" },
                { id: "v2", icon: Layers, label: "Components V2", desc: "Frei aus Bausteinen" },
              ].map((o) => (
                <button
                  key={o.id}
                  onClick={() => { setKind(o.id as Kind); setSent(null); }}
                  className={cn(
                    "text-left rounded-2xl border p-4 transition-all",
                    kind === o.id
                      ? "bg-primary/10 border-primary/40"
                      : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                  )}
                >
                  <o.icon className={cn(
                    "h-4 w-4 mb-2",
                    kind === o.id ? "text-primary" : "text-slate-500"
                  )} />
                  <p className="text-sm font-bold text-white">{o.label}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">{o.desc}</p>
                </button>
              ))}
            </div>
          </Field>
        </div>

        {/* ── Text ─────────────────────────────────── */}
        {kind === "text" && (
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card">
            <Field
              label="Nachricht"
              hint="Discord-Formatierung geht: **fett**, *kursiv*, `Code`, > Zitat."
            >
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={8}
                maxLength={2000}
                placeholder="Was der Bot schreiben soll …"
                className={cn(INPUT, "resize-y")}
              />
              <p className="text-[11px] text-slate-600 text-right">{content.length} / 2000</p>
            </Field>
          </div>
        )}

        {/* ── Embed ────────────────────────────────── */}
        {kind === "embed" && (
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
            <Field
              label="Text über dem Embed"
              hint="Nur hier funktionieren Erwähnungen — ein Ping im Embed benachrichtigt niemanden."
            >
              <input
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Optional"
                className={INPUT}
              />
            </Field>

            <div className="grid md:grid-cols-2 gap-5">
              <Field label="Titel">
                <input
                  value={embed.title}
                  onChange={(e) => setEmbed({ ...embed, title: e.target.value })}
                  maxLength={256}
                  className={INPUT}
                />
              </Field>
              <Field label="Farbe">
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={/^#[0-9a-f]{6}$/i.test(embed.color) ? embed.color : "#5865f2"}
                    onChange={(e) => setEmbed({ ...embed, color: e.target.value })}
                    className="h-11 w-14 rounded-xl bg-transparent border border-slate-800 cursor-pointer p-1 shrink-0"
                  />
                  <input
                    value={embed.color}
                    onChange={(e) => setEmbed({ ...embed, color: e.target.value })}
                    className={cn(INPUT, "font-mono")}
                  />
                </div>
              </Field>
            </div>

            <Field label="Beschreibung">
              <textarea
                value={embed.description}
                onChange={(e) => setEmbed({ ...embed, description: e.target.value })}
                rows={5}
                maxLength={4096}
                className={cn(INPUT, "resize-y")}
              />
            </Field>

            <div className="grid md:grid-cols-2 gap-5">
              <Field label="Autor (Kopfzeile)">
                <input
                  value={embed.author_name}
                  onChange={(e) => setEmbed({ ...embed, author_name: e.target.value })}
                  className={INPUT}
                />
              </Field>
              <Field label="Fußzeile">
                <input
                  value={embed.footer_text}
                  onChange={(e) => setEmbed({ ...embed, footer_text: e.target.value })}
                  className={INPUT}
                />
              </Field>
              <Field label="Großes Bild (URL)">
                <input
                  value={embed.image}
                  onChange={(e) => setEmbed({ ...embed, image: e.target.value })}
                  placeholder="https://…"
                  className={INPUT}
                />
              </Field>
              <Field label="Kleines Bild oben rechts">
                <input
                  value={embed.thumbnail}
                  onChange={(e) => setEmbed({ ...embed, thumbnail: e.target.value })}
                  placeholder="https://…"
                  className={INPUT}
                />
              </Field>
            </div>

            {/* Fields */}
            <div className="border-t border-slate-800 pt-5 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Felder ({embed.fields.length}/25)
                </p>
                <button
                  onClick={() =>
                    setEmbed({
                      ...embed,
                      fields: [...embed.fields, { name: "", value: "", inline: false }],
                    })
                  }
                  disabled={embed.fields.length >= 25}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-[11px] font-black uppercase tracking-widest text-slate-300 hover:text-primary disabled:opacity-40 transition-all"
                >
                  <Plus className="h-3.5 w-3.5" /> Feld
                </button>
              </div>

              {embed.fields.map((field: any, index: number) => (
                <div key={index} className="bg-[#0d1b31] border border-slate-800 rounded-2xl p-4 space-y-3">
                  <div className="flex gap-2">
                    <input
                      value={field.name}
                      onChange={(e) => {
                        const fields = [...embed.fields];
                        fields[index] = { ...field, name: e.target.value };
                        setEmbed({ ...embed, fields });
                      }}
                      placeholder="Name"
                      className={cn(INPUT, "flex-1")}
                    />
                    <button
                      onClick={() =>
                        setEmbed({
                          ...embed,
                          fields: embed.fields.filter((_: any, i: number) => i !== index),
                        })
                      }
                      className="p-3 rounded-xl text-slate-500 hover:text-red-400 transition-all shrink-0"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <textarea
                    value={field.value}
                    onChange={(e) => {
                      const fields = [...embed.fields];
                      fields[index] = { ...field, value: e.target.value };
                      setEmbed({ ...embed, fields });
                    }}
                    rows={2}
                    placeholder="Inhalt"
                    className={cn(INPUT, "resize-y")}
                  />
                  <InlineToggle
                    checked={field.inline}
                    onCheckedChange={(v: boolean) => {
                      const fields = [...embed.fields];
                      fields[index] = { ...field, inline: v };
                      setEmbed({ ...embed, fields });
                    }}
                    label="Nebeneinander anzeigen"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── V2 blocks ────────────────────────────── */}
        {kind === "v2" && (
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-5 border-glow-card">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                Bausteine ({blocks.length})
              </p>
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-slate-600">Farbstreifen</span>
                <input
                  type="color"
                  value={accent}
                  onChange={(e) => setAccent(e.target.value)}
                  className="h-9 w-12 rounded-lg bg-transparent border border-slate-800 cursor-pointer p-1"
                />
              </div>
            </div>

            <div className="flex gap-1.5 flex-wrap">
              {[
                { type: "text", icon: Type, label: "Text" },
                { type: "divider", icon: Minus, label: "Trennlinie" },
                { type: "image", icon: ImageIcon, label: "Bild" },
                { type: "buttons", icon: MousePointerClick, label: "Knöpfe" },
              ].map((o) => (
                <button
                  key={o.type}
                  onClick={() => addBlock(o.type as Block["type"])}
                  className="flex items-center gap-1.5 px-3 h-10 rounded-xl bg-[#0d1b31] border border-slate-800 text-xs font-bold text-slate-300 hover:text-primary hover:border-primary/30 transition-all"
                >
                  <o.icon className="h-3.5 w-3.5" />
                  {o.label}
                </button>
              ))}
            </div>

            {blocks.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-8 border border-dashed border-slate-800 rounded-2xl">
                Noch kein Baustein — oben einen hinzufügen.
              </p>
            ) : (
              <div className="space-y-3">
                {blocks.map((block, index) => (
                  <div
                    key={block.id}
                    className="bg-[#0d1b31] border border-slate-800 rounded-2xl p-4 space-y-3"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-600 flex-1">
                        {{
                          text: "Text", divider: "Trennlinie",
                          image: "Bild", buttons: "Knöpfe",
                        }[block.type]}
                      </span>
                      <button
                        onClick={() => moveBlock(block.id, -1)}
                        disabled={index === 0}
                        className="p-1.5 rounded-lg text-slate-600 hover:text-white disabled:opacity-20"
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => moveBlock(block.id, 1)}
                        disabled={index === blocks.length - 1}
                        className="p-1.5 rounded-lg text-slate-600 hover:text-white disabled:opacity-20"
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => removeBlock(block.id)}
                        className="p-1.5 rounded-lg text-slate-600 hover:text-red-400"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    {block.type === "text" && (
                      <textarea
                        value={block.text || ""}
                        onChange={(e) => patchBlock(block.id, { text: e.target.value })}
                        rows={3}
                        placeholder="**Fett**, *kursiv*, `Code` …"
                        className={cn(INPUT, "resize-y")}
                      />
                    )}

                    {block.type === "image" && (
                      <input
                        value={block.url || ""}
                        onChange={(e) => patchBlock(block.id, { url: e.target.value })}
                        placeholder="https://…"
                        className={INPUT}
                      />
                    )}

                    {block.type === "divider" && (
                      <InlineToggle
                        checked={!block.invisible}
                        onCheckedChange={(v: boolean) => patchBlock(block.id, { invisible: !v })}
                        label="Sichtbare Linie"
                        hint="Aus: nur ein Abstand, ohne Strich."
                      />
                    )}

                    {block.type === "buttons" && (
                      <div className="space-y-2">
                        {(block.buttons || []).map((button, bi) => (
                          <div key={bi} className="flex gap-2 flex-wrap">
                            <input
                              value={button.emoji || ""}
                              onChange={(e) => {
                                const buttons = [...(block.buttons || [])];
                                buttons[bi] = { ...button, emoji: e.target.value };
                                patchBlock(block.id, { buttons });
                              }}
                              placeholder="🔗"
                              className="w-14 bg-[#0b1626] border border-slate-800 rounded-xl px-2 py-3 text-sm text-white text-center focus:outline-none"
                            />
                            <input
                              value={button.label}
                              onChange={(e) => {
                                const buttons = [...(block.buttons || [])];
                                buttons[bi] = { ...button, label: e.target.value };
                                patchBlock(block.id, { buttons });
                              }}
                              placeholder="Beschriftung"
                              className={cn(INPUT, "flex-1 min-w-[120px]")}
                            />
                            <input
                              value={button.url}
                              onChange={(e) => {
                                const buttons = [...(block.buttons || [])];
                                buttons[bi] = { ...button, url: e.target.value };
                                patchBlock(block.id, { buttons });
                              }}
                              placeholder="https://…"
                              className={cn(INPUT, "flex-1 min-w-[160px]")}
                            />
                            <button
                              onClick={() =>
                                patchBlock(block.id, {
                                  buttons: (block.buttons || []).filter((_, i) => i !== bi),
                                })
                              }
                              className="p-3 rounded-xl text-slate-500 hover:text-red-400 shrink-0"
                            >
                              <X className="h-4 w-4" />
                            </button>
                          </div>
                        ))}
                        <button
                          onClick={() =>
                            patchBlock(block.id, {
                              buttons: [...(block.buttons || []),
                                { label: "", url: "https://" }],
                            })
                          }
                          disabled={(block.buttons || []).length >= 5}
                          className="text-[11px] font-black uppercase tracking-widest text-slate-500 hover:text-primary disabled:opacity-40"
                        >
                          + Knopf (max 5 pro Reihe)
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="rounded-xl bg-white/[0.02] border border-white/5 p-3.5 flex gap-2.5">
              <Link2 className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Knöpfe können nur Links öffnen. Ein Knopf, der etwas im Bot
                auslöst, braucht Code dahinter — den gibt es bei Tickets,
                Gewinnspielen und der Verifizierung schon fertig.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ══ Preview + send ═══════════════════════════ */}
      <div className="xl:col-span-2 space-y-5">
        <div className="xl:sticky xl:top-6 space-y-5">
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
              <Eye className="h-3.5 w-3.5" /> Vorschau
            </p>

            <div className="rounded-2xl bg-[#313338] p-4 space-y-2">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-primary/30 shrink-0" />
                {/* The bot's own name, so the preview matches what the
                    server will actually see. */}
                <span className="text-sm font-semibold text-white">
                  {process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot"}
                </span>
                <span className="px-1 py-0.5 rounded bg-[#5865f2] text-[9px] font-bold uppercase text-white">
                  Bot
                </span>
              </div>

              {kind === "text" && (
                <p
                  className="text-sm text-[#dbdee1] break-words pl-10"
                  dangerouslySetInnerHTML={{
                    __html: markdown(content) ||
                      '<span class="italic text-slate-600">leer</span>',
                  }}
                />
              )}

              {kind === "embed" && (
                <div className="pl-10 space-y-1.5">
                  {content && (
                    <p
                      className="text-sm text-[#dbdee1] break-words"
                      dangerouslySetInnerHTML={{ __html: markdown(content) }}
                    />
                  )}
                  <div
                    className="rounded border-l-4 bg-[#2b2d31] p-3.5 space-y-2"
                    style={{
                      borderLeftColor: /^#[0-9a-f]{6}$/i.test(embed.color)
                        ? embed.color : "#5865f2",
                    }}
                  >
                    <div className="flex gap-3">
                      <div className="min-w-0 flex-1 space-y-1.5">
                        {embed.author_name && (
                          <p className="text-xs font-semibold text-white">{embed.author_name}</p>
                        )}
                        {embed.title && (
                          <p className="text-[15px] font-bold text-white break-words">
                            {embed.title}
                          </p>
                        )}
                        {embed.description && (
                          <p
                            className="text-sm text-[#dbdee1] break-words"
                            dangerouslySetInnerHTML={{ __html: markdown(embed.description) }}
                          />
                        )}
                        {embed.fields.length > 0 && (
                          <div className="grid grid-cols-2 gap-2 pt-1">
                            {embed.fields.map((f: any, i: number) => (
                              <div key={i} className={cn(!f.inline && "col-span-2")}>
                                <p className="text-[13px] font-bold text-white">{f.name}</p>
                                <p
                                  className="text-[13px] text-[#dbdee1] break-words"
                                  dangerouslySetInnerHTML={{ __html: markdown(f.value) }}
                                />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      {/^https?:\/\//.test(embed.thumbnail) && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={embed.thumbnail} alt="" className="h-16 w-16 rounded object-cover shrink-0"
                          onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                      )}
                    </div>
                    {/^https?:\/\//.test(embed.image) && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={embed.image} alt="" className="w-full rounded object-cover max-h-48"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                    )}
                    {embed.footer_text && (
                      <p className="text-[11px] text-[#949ba4]">{embed.footer_text}</p>
                    )}
                  </div>
                </div>
              )}

              {kind === "v2" && (
                <div className="pl-10">
                  <div
                    className="rounded border-l-4 bg-[#2b2d31] p-3.5 space-y-2.5"
                    style={{ borderLeftColor: accent }}
                  >
                    {blocks.length === 0 && (
                      <p className="text-sm italic text-slate-600">Noch nichts drin.</p>
                    )}
                    {blocks.map((block) => {
                      if (block.type === "text")
                        return (
                          <p
                            key={block.id}
                            className="text-sm text-[#dbdee1] break-words"
                            dangerouslySetInnerHTML={{
                              __html: markdown(block.text || "") ||
                                '<span class="italic text-slate-600">leerer Text</span>',
                            }}
                          />
                        );
                      if (block.type === "divider")
                        return (
                          <div
                            key={block.id}
                            className={cn(
                              "my-1",
                              block.invisible ? "h-2" : "border-t border-slate-600"
                            )}
                          />
                        );
                      if (block.type === "image")
                        return /^https?:\/\//.test(block.url || "") ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img key={block.id} src={block.url} alt=""
                            className="w-full rounded object-cover max-h-48"
                            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                        ) : (
                          <p key={block.id} className="text-[11px] italic text-slate-600">
                            Bild ohne gültigen Link
                          </p>
                        );
                      return (
                        <div key={block.id} className="flex flex-wrap gap-2 pt-1">
                          {(block.buttons || []).map((b, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#4e5058] text-white text-[13px] font-medium"
                            >
                              {b.emoji && <span>{b.emoji}</span>}
                              {b.label || "Knopf"}
                              <Link2 className="h-3 w-3 opacity-60" />
                            </span>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Problems */}
          {problems.length > 0 && (
            <div className="rounded-2xl bg-red-500/[0.07] border border-red-500/25 p-4 space-y-2">
              <p className="text-[11px] font-black uppercase tracking-widest text-red-300 flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5" />
                Das geht so noch nicht
              </p>
              {problems.map((p, i) => (
                <p key={i} className="text-[12px] text-red-200/80 leading-relaxed">• {p}</p>
              ))}
            </div>
          )}

          {/* Send */}
          <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 space-y-4 border-glow-card">
            {/* Only rendered where there is an actual choice. A picker
                with one option is noise. */}
            {senders.length > 1 && (
              <Field
                label="Als welcher Bot"
                hint="Der Status-Bot läuft getrennt und kann auch posten, wenn der Hauptbot gerade nicht erreichbar ist."
              >
                <div className="grid sm:grid-cols-2 gap-2">
                  {senders.map((option) => (
                    <button
                      key={option.id}
                      onClick={() => { setSender(option.id); setSent(null); }}
                      className={cn(
                        "text-left rounded-2xl border p-3 transition-all",
                        sender === option.id
                          ? "bg-primary/10 border-primary/40"
                          : "bg-[#0d1b31] border-slate-800 hover:border-slate-700"
                      )}
                    >
                      <p className="text-sm font-bold text-white">{option.name}</p>
                      <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                        {option.description}
                      </p>
                    </button>
                  ))}
                </div>
              </Field>
            )}

            <Field label="In welchen Kanal">
              <ChannelPicker
                guildId={guildId}
                value={channelId}
                onChange={(id) => { setChannelId(id || ""); setSent(null); }}
                placeholder="Kanal wählen"
                channelTypes={["0", "5"]}
              />
            </Field>

            <div className="space-y-3">
              <InlineToggle
                checked={allowMentions}
                onCheckedChange={setAllowMentions}
                label="Erwähnungen benachrichtigen"
                hint="Aus (empfohlen): @everyone bleibt lesbar, pingt aber niemanden."
              />
              <InlineToggle
                checked={pin}
                onCheckedChange={setPin}
                label="Nachricht anpinnen"
              />
            </div>

            <button
              onClick={send}
              disabled={busy || !channelId || problems.length > 0}
              title={
                !channelId ? "Erst einen Kanal wählen"
                  : problems.length ? "Erst die Hinweise oben beheben"
                    : undefined
              }
              className="w-full flex items-center justify-center gap-2 py-4 rounded-2xl bg-primary text-xs font-black uppercase tracking-widest shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 transition-all"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Absenden
            </button>

            {sent && (
              <div className="rounded-xl bg-emerald-500/[0.07] border border-emerald-500/25 p-3.5 space-y-2">
                <p className="text-[12px] text-emerald-200/90 flex items-center gap-1.5">
                  <Check className="h-3.5 w-3.5" /> Gesendet.
                </p>
                <div className="flex gap-2 flex-wrap">
                  <a
                    href={sent.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] font-black uppercase tracking-widest text-emerald-300 hover:underline"
                  >
                    In Discord ansehen
                  </a>
                  <button
                    onClick={() => {
                      navigator.clipboard?.writeText(sent.id);
                      toast.success("Nachrichten-ID kopiert.");
                    }}
                    className="text-[11px] font-black uppercase tracking-widest text-slate-400 hover:text-white flex items-center gap-1"
                  >
                    <Copy className="h-3 w-3" /> ID kopieren
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
