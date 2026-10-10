import { loginUrl } from "@/lib/auth-navigation";
/* eslint-disable @next/next/no-img-element -- Discord CDN media has runtime dimensions and must remain byte-for-byte linked. */
import { BRAND_LOGO } from "@/lib/brand";
import { getServerSession } from "next-auth/next";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import { DiscordEmojiText } from "@/components/dashboard/discord-emoji";
import "./transcript.css";

export const dynamic = "force-dynamic";
export const metadata = { title: "Ticket Transcript" };

const API_BASE_URL =
  process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

type AnyData = Record<string, any>;

function when(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

function DiscordContent({ text }: { text: string }) {
  const value = String(text || "");
  const codeBlocks = value.split(/(```[\s\S]*?```)/g);
  return <>{codeBlocks.map((block, blockIndex) => {
    if (block.startsWith("```") && block.endsWith("```")) {
      return <pre className="code-block" key={blockIndex}>{block.slice(3, -3).replace(/^\w+\n/, "")}</pre>;
    }
    const token = /<(a?):([A-Za-z0-9_]+):(\d{5,22})>|\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|`([^`]+)`|(https?:\/\/[^\s<]+)/g;
    const parts: React.ReactNode[] = [];
    let cursor = 0;
    let match: RegExpExecArray | null;
    while ((match = token.exec(block)) !== null) {
      if (match.index > cursor) parts.push(block.slice(cursor, match.index));
      if (match[3]) {
        parts.push(<img className="inline-emoji" key={match.index} src={`https://cdn.discordapp.com/emojis/${match[3]}.${match[1] === "a" ? "gif" : "png"}?size=48&quality=lossless`} alt={`:${match[2]}:`} />);
      } else if (match[4]) parts.push(<strong key={match.index}>{match[4]}</strong>);
      else if (match[5]) parts.push(<u key={match.index}>{match[5]}</u>);
      else if (match[6]) parts.push(<s key={match.index}>{match[6]}</s>);
      else if (match[7]) parts.push(<code key={match.index}>{match[7]}</code>);
      else if (match[8]) parts.push(<a key={match.index} href={match[8]} target="_blank" rel="noreferrer">{match[8]}</a>);
      cursor = match.index + match[0].length;
    }
    if (cursor < block.length) parts.push(block.slice(cursor));
    return <span key={blockIndex}>{parts}</span>;
  })}</>;
}

function renderComponent(component: AnyData, key: string): React.ReactNode {
  const children = component.components || component.children || [];
  if (component.type === 10) {
    return <div className="cv2-text" key={key}><DiscordContent text={component.content || ""} /></div>;
  }
  if (component.type === 14) {
    return <div className={`cv2-separator ${component.divider === false ? "blank" : ""}`} key={key} />;
  }
  if (component.type === 2) {
    const style = Number(component.style || 2);
    return <span className={`discord-button style-${style}`} key={key}><DiscordEmojiText text={`${component.emoji?.name || ""} ${component.label || "Button"}`} /></span>;
  }
  if ([3, 5, 6, 7, 8].includes(Number(component.type))) {
    return <div className="discord-select" key={key}>{component.placeholder || "Select an option"}<span>⌄</span></div>;
  }
  if (component.type === 11) {
    const url = component.media?.url || component.url;
    return url ? <img className="cv2-thumbnail" src={url} alt="Section thumbnail" key={key} /> : null;
  }
  if (component.type === 12) {
    const items = component.items || [];
    return <div className="media-grid" key={key}>{items.map((item: AnyData, index: number) => {
      const url = item.media?.url || item.url;
      return url ? <img src={url} alt={item.description || "Attached media"} key={index} /> : null;
    })}</div>;
  }
  if (children.length || component.accessory) {
    const accent = component.type === 17 && component.accent_color != null
      ? `#${Number(component.accent_color).toString(16).padStart(6, "0")}`
      : undefined;
    return <div
      className={component.type === 17 ? "cv2-container" : component.type === 9 ? "cv2-section" : "cv2-row"}
      style={accent ? { borderLeftColor: accent } : undefined}
      key={key}
    >
      <div className={component.type === 1 ? "cv2-button-row" : undefined}>{children.map((child: AnyData, index: number) => renderComponent(child, `${key}-${index}`))}</div>
      {component.accessory && renderComponent(component.accessory, `${key}-accessory`)}
    </div>;
  }
  return null;
}

function DiscordEmbed({ embed }: { embed: AnyData }) {
  const color = typeof embed.color === "number" ? `#${embed.color.toString(16).padStart(6, "0")}` : "#202225";
  return <div className="discord-embed" style={{ borderColor: color }}>
    {embed.author?.name && <div className="embed-author">{embed.author.name}</div>}
    {embed.title && <div className="embed-title">{embed.url ? <a href={embed.url}>{embed.title}</a> : embed.title}</div>}
    {embed.description && <div className="embed-description"><DiscordContent text={embed.description} /></div>}
    {Array.isArray(embed.fields) && <div className="embed-fields">{embed.fields.map((field: AnyData, index: number) =>
      <div className={field.inline ? "embed-field inline" : "embed-field"} key={index}>
        <strong>{field.name}</strong><DiscordContent text={field.value || ""} />
      </div>
    )}</div>}
    {embed.image?.url && <img className="embed-image" src={embed.image.url} alt="Embed attachment" />}
    {embed.thumbnail?.url && <img className="embed-thumbnail" src={embed.thumbnail.url} alt="Embed thumbnail" />}
    {embed.footer?.text && <div className="embed-footer">{embed.footer.text}</div>}
  </div>;
}

function Message({ message, compact = false }: { message: AnyData; compact?: boolean }) {
  return <article className={`discord-message ${compact ? "compact" : ""}`} id={`message-${message.id}`}>
    {compact
      ? <time className="compact-time" dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</time>
      : <img className="avatar" src={message.author.avatar_url || BRAND_LOGO} alt="" />}
    <div className="message-body">
      {message.reply && <div className="reply-line"><span>↪</span> <strong>{message.reply.author || "Original message"}</strong> {message.reply.content}</div>}
      {!compact && <div className="message-meta">
        <strong className="display-name">{message.author.display_name}</strong>
        {message.author.bot && <span className="app-badge">APP</span>}
        <time dateTime={message.created_at}>{when(message.created_at)}</time>
        {message.edited_at && <span className="edited">(edited)</span>}
      </div>}
      {message.content && <div className="message-content"><DiscordContent text={message.content} />{compact && message.edited_at && <span className="edited"> (edited)</span>}</div>}
      {message.attachments?.map((attachment: AnyData) => {
        const image = String(attachment.content_type || "").startsWith("image/");
        return image
          ? <a href={attachment.url} key={attachment.id} className="attachment-image"><img src={attachment.proxy_url || attachment.url} alt={attachment.description || attachment.filename} /></a>
          : <a href={attachment.url} key={attachment.id} className="attachment-file"><span>↧</span><span><strong>{attachment.filename}</strong><small>{Math.ceil((attachment.size || 0) / 1024)} KB</small></span></a>;
      })}
      {message.stickers?.map((sticker: AnyData, index: number) => <img className="sticker" src={sticker.url} alt={sticker.name} key={index} />)}
      {message.embeds?.map((embed: AnyData, index: number) => <DiscordEmbed embed={embed} key={index} />)}
      {message.components?.length > 0 && <div className="components-v2">{message.components.map((component: AnyData, index: number) => renderComponent(component, String(index)))}</div>}
      {message.reactions?.length > 0 && <div className="reactions">{message.reactions.map((reaction: AnyData, index: number) => <span key={index}><DiscordEmojiText text={reaction.emoji} /> {reaction.count}</span>)}</div>}
    </div>
  </article>;
}

export default async function TicketTranscriptPage({ params }: { params: { ticketId: string } }) {
  const session = await getServerSession(authOptions);
  const callbackUrl = `/Tickets/Transkript/${encodeURIComponent(params.ticketId)}`;
  if (!session?.user?.id) redirect(loginUrl(callbackUrl));
  if (!/^\d{15,22}$/.test(params.ticketId)) {
    return <main className="transcript-error"><h1>Invalid transcript</h1><p>This ticket ID is not valid.</p></main>;
  }

  const response = await fetch(
    `${API_BASE_URL}/tickets/transcript/${params.ticketId}?actor=${encodeURIComponent(session.user.id)}`,
    {
      headers: {
        Authorization: `Bearer ${process.env.DASHBOARD_API_KEY || ""}`,
      },
      cache: "no-store",
    },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    return <main className="transcript-error"><h1>Transcript unavailable</h1><p>{body.detail || "You do not have access, or this transcript has expired."}</p></main>;
  }
  const transcript = await response.json();

  return <div className="discord-shell">
    <aside className="server-rail"><div className="server-icon">U</div></aside>
    <aside className="channel-rail">
      <header>{transcript.guild_name}<span>⌄</span></header>
      <div className="channel-category">TICKET ARCHIVE</div>
      <div className="channel active"><span>#</span>{transcript.channel_name}</div>
      <div className="channel-details">
        <span>Ticket #{transcript.ticket_number || transcript.ticket_id}</span>
        <span>{transcript.category_name || "Support"}</span>
      </div>
    </aside>
    <main className="chat-panel">
      <header className="chat-header"><span className="hash">#</span><strong>{transcript.channel_name}</strong><span className="header-divider" /><span>Read-only ticket transcript</span></header>
      <section className="message-list">
        <div className="channel-start"><div className="start-hash">#</div><h1>Welcome to #{transcript.channel_name}!</h1><p>This is the start of the archived ticket from <strong>{transcript.guild_name}</strong>.</p><div className="archive-notice">Private archive · Expires {when(transcript.expires_at)} · {transcript.messages.length} messages</div></div>
        {transcript.messages.map((message: AnyData, index: number) => {
          const previous = transcript.messages[index - 1];
          const compact = Boolean(
            previous && !message.reply && previous.author?.id === message.author?.id &&
            new Date(message.created_at).getTime() - new Date(previous.created_at).getTime() < 7 * 60 * 1000
          );
          return <Message message={message} compact={compact} key={message.id} />;
        })}
      </section>
      <footer className="read-only">You are viewing a read-only transcript</footer>
    </main>
  </div>;
}
