"use client";

import React from "react";
import { cn } from "@/lib/utils";

/** Discord's normal custom-emoji form plus the short legacy form some saved
 * dashboard values used. Both render as the real CDN image in previews. */
const CUSTOM_EMOJI = /<(a?):([A-Za-z0-9_]+):(\d{5,22})>|<emoji:(\d{5,22})>/g;

function EmojiImage({
  id,
  name,
  animated,
  className,
}: {
  id: string;
  name: string;
  animated: boolean;
  className?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`https://cdn.discordapp.com/emojis/${id}.${animated ? "gif" : "png"}?size=48&quality=lossless`}
      alt={`:${name}:`}
      title={`:${name}:`}
      draggable={false}
      className={cn("inline-block h-[1.35em] w-[1.35em] object-contain align-[-0.22em]", className)}
    />
  );
}

/** Render one emoji value. Unicode stays Unicode; custom syntax becomes art. */
export function DiscordEmoji({ value, className }: { value: string; className?: string }) {
  const raw = String(value || "");
  const match = /^(?:<(a?):([A-Za-z0-9_]+):(\d{5,22})>|<emoji:(\d{5,22})>)$/.exec(raw);
  if (!match) return <span className={className}>{raw}</span>;
  return (
    <EmojiImage
      id={match[3] || match[4]}
      name={match[2] || "emoji"}
      animated={match[1] === "a"}
      className={className}
    />
  );
}

/** Render custom emojis inside arbitrary preview text without changing the
 * stored Discord text. This is presentation-only: the API still receives the
 * original `<:name:id>` value Discord expects. */
export function DiscordEmojiText({ text, className }: { text: string; className?: string }) {
  const value = String(text || "");
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  CUSTOM_EMOJI.lastIndex = 0;
  while ((match = CUSTOM_EMOJI.exec(value)) !== null) {
    if (match.index > cursor) parts.push(value.slice(cursor, match.index));
    parts.push(
      <EmojiImage
        key={`${match.index}-${match[3] || match[4]}`}
        id={match[3] || match[4]}
        name={match[2] || "emoji"}
        animated={match[1] === "a"}
      />
    );
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) parts.push(value.slice(cursor));
  return <span className={className}>{parts.length ? parts : value}</span>;
}

/** HTML replacement for previews that already use a sanitized innerHTML
 * renderer (the Components V2 composer). Call only after HTML escaping. */
export function customEmojiHtml(escaped: string): string {
  return escaped.replace(
    /&lt;(a?):([A-Za-z0-9_]+):(\d{5,22})&gt;|&lt;emoji:(\d{5,22})&gt;/g,
    (_all, animated, name, normalId, legacyId) => {
      const id = normalId || legacyId;
      const ext = animated === "a" ? "gif" : "png";
      const safeName = name || "emoji";
      return `<img src="https://cdn.discordapp.com/emojis/${id}.${ext}?size=48&amp;quality=lossless" alt=":${safeName}:" title=":${safeName}:" class="inline-block h-[1.35em] w-[1.35em] object-contain align-[-0.22em]" draggable="false" />`;
    }
  );
}
