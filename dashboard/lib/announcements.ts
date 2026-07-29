/**
 * Ready-made announcements for the compose tab.
 *
 * These are changelog posts for the bot's own community server. They
 * only show up there: `guildId` is checked against each entry's
 * `guilds` list, so every other server sees the compose tab exactly as
 * it was, with no templates section at all. A server owner who is not
 * us has no use for "the bot got a database" and should not have to
 * scroll past it.
 *
 * To add the next one, put a new object at the top of ANNOUNCEMENTS.
 * Newest first — the list is rendered in order.
 */

/** The bot's own community server. */
export const BOT_GUILD_ID = "1530378233579704370";

export interface AnnouncementBlock {
  type: "text" | "divider" | "image" | "buttons";
  text?: string;
  url?: string;
  invisible?: boolean;
  buttons?: { label: string; url: string; emoji?: string }[];
}

export interface Announcement {
  /** Stable id, used as the React key. */
  id: string;
  /** What the button in the dashboard says. */
  label: string;
  /** One line under the button, so you know which one you are picking. */
  summary: string;
  /** Which servers may see it. */
  guilds: string[];
  /** Date shown on the button, as it should read to a human. */
  date: string;
  /** The accent colour down the left edge of the message. */
  accent: string;
  blocks: AnnouncementBlock[];
}

export const ANNOUNCEMENTS: Announcement[] = [
  {
    id: "2026-07-database",
    label: "Changelog: Datenbank",
    summary: "Einstellungen überleben jetzt Updates",
    guilds: [BOT_GUILD_ID],
    date: "29.07.2026",
    accent: "#5865f2",
    blocks: [
      {
        type: "text",
        text:
          "# 📦 Changelog · Juli 2026\n" +
          "### Eure Einstellungen bleiben jetzt erhalten",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Bisher lief der Bot ohne feste Datenbank. Bei jedem Update wurde " +
          "der Server neu aufgesetzt — und alles, was ihr eingestellt " +
          "hattet, war weg. Automod, Verifizierung, Tickets, Level-System: " +
          "jedes Mal von vorn.\n\n" +
          "**Das ist ab sofort vorbei.** Der Bot hat jetzt eine echte " +
          "Datenbank, die Updates übersteht.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was das für euch heißt\n\n" +
          "> Ihr stellt euren Server **einmal** ein — und das war's.\n\n" +
          "Wir haben alle **30 Module** einzeln geprüft: Automod, Anti-Nuke, " +
          "Verifizierung, Tickets, Begrüßung, Level-System, Giveaways, " +
          "Reaktions-Rollen, Join to Create, Counting, Jail, Nachtmodus und " +
          "alle weiteren. Jedes einzelne behält seine Einstellungen.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Außerdem neu\n\n" +
          "**YouTube-Benachrichtigungen** — Kanalnamen eintragen, Rolle und " +
          "Kanal wählen, fertig. Der Bot meldet neue Videos, Shorts und " +
          "Livestreams. Bis zu drei Kanäle pro Server.\n\n" +
          "**Dashboard auf dem Handy** — war vorher winzig und kaum " +
          "bedienbar. Ist jetzt vernünftig nutzbar.\n\n" +
          "**Tabs neu sortiert** — statt 32 Reitern in einer Reihe gibt es " +
          "jetzt Gruppen und eine Suche.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Fragen oder etwas kaputt? Meldet euch hier im Server. " +
          "Wir bauen weiter.",
      },
    ],
  },
];

/** The announcements this server is allowed to see. */
export function announcementsFor(guildId: string): Announcement[] {
  return ANNOUNCEMENTS.filter((entry) =>
    entry.guilds.includes(String(guildId))
  );
}
