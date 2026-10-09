"use client";

import { Link2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";
import { DiscordEmoji, DiscordEmojiText, customEmojiHtml } from "./discord-emoji";
import { useWebsiteLocale } from "@/lib/i18n/locale";

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
  return customEmojiHtml(escaped)
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


/** The same Discord-style preview for the editor and stored message designs. */
export function ComposeMessagePreview({ payload }: { payload: any }) {
  const locale = useWebsiteLocale();
  const t = (de: string, en: string) => locale === "en-GB" ? en : de;
  const kind = payload.kind || "text";
  const content = String(payload.content || "");
  const embed = { ...(payload.embed || {}), fields: Array.isArray(payload.embed?.fields) ? payload.embed.fields : [] };
  const accent = /^#[0-9a-f]{6}$/i.test(payload.color || "") ? payload.color : "#5865f2";
  const blocks = (Array.isArray(payload.blocks) ? payload.blocks : []).map((block: any, index: number) => ({ ...block, id: index }));
  return (
            <div data-no-translate className="rounded-2xl bg-[#313338] p-4 space-y-2">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-primary/30 shrink-0" />
                {/* The bot's own name, so the preview matches what the
                    server will actually see. */}
                <span className="text-sm font-semibold text-white">
                  {BRAND}
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
                      `<span class="italic text-slate-600">${t("leer", "empty")}</span>`,
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
                          <p className="text-xs font-semibold text-white"><DiscordEmojiText text={embed.author_name} /></p>
                        )}
                        {embed.title && (
                          <p className="text-[15px] font-bold text-white break-words">
                            <DiscordEmojiText text={embed.title} />
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
                                <p className="text-[13px] font-bold text-white"><DiscordEmojiText text={f.name} /></p>
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
                      <p className="text-[11px] text-[#949ba4]"><DiscordEmojiText text={embed.footer_text} /></p>
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
                      <p className="text-sm italic text-slate-600">{t("Noch nichts drin.", "No content yet.")}</p>
                    )}
                    {blocks.map((block: any) => {
                      if (block.type === "text")
                        return (
                          <p
                            key={block.id}
                            className="text-sm text-[#dbdee1] break-words"
                            dangerouslySetInnerHTML={{
                              __html: markdown(block.text || "") ||
                                `<span class="italic text-slate-600">${t("leerer Text", "empty text")}</span>`,
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
                            {t("Bild ohne gültigen Link", "Image without a valid link")}
                          </p>
                        );
                      return (
                        <div key={block.id} className="flex flex-wrap gap-2 pt-1">
                          {(block.buttons || []).map((b: any, i: number) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#4e5058] text-white text-[13px] font-medium"
                            >
                              {b.emoji && <DiscordEmoji value={b.emoji} />}
                              {b.label || t("Knopf", "Button")}
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
  );
}
