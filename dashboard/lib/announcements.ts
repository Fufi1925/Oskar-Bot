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
    id: "2026-07-team-page",
    label: "Changelog: Team-Seite",
    summary: "Team-Seite mit Profilbildern",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#5865f2",
    blocks: [
      {
        type: "text",
        text:
          "# 👥 Changelog · Team\n" +
          "### Wer hinter dem Bot steckt",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Die Team-Seite zeigt jetzt beide Entwickler mit ihrem " +
          "echten Discord-Profilbild und -Namen.\n\n" +
          "> **Fufi** — Entwicklung und Betrieb von Bot und Dashboard\n" +
          "> **Vexo** — Entwickler des Template-Bots, von ihm stammt " +
          "die ursprüngliche Idee zum Projekt",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Fragen oder Fehler? Am schnellsten hier im Support-Server.",
      },
    ],
  },
  {
    id: "2026-07-backups",
    label: "Changelog: Backups",
    summary: "Tägliche Sicherung, und zwei fehlende Datenbanken",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#faa61a",
    blocks: [
      {
        type: "text",
        text:
          "# 💾 Changelog · Backups\n" +
          "### Zwei Datenbanken fehlten in der automatischen Sicherung",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Die automatische Sicherung hat **Reaktions-Rollen** und " +
          "**Join to Create** übersprungen — beide liegen außerhalb des " +
          "Datenbank-Ordners. Beim Zurückspielen wären sie weg gewesen. " +
          "Behoben: es wird jetzt überall dasselbe gesichert.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Außerdem\n\n" +
          "> 📅 **Einmal am Tag** statt alle sechs Stunden.\n" +
          "> 🧹 **Nur die neueste** wird behalten — kein Zumüllen mehr.\n" +
          "> ✅ **Erst prüfen, dann löschen** — die alte Sicherung " +
          "verschwindet erst, wenn die neue gelesen und für gut " +
          "befunden wurde. Geht etwas schief, bleibt die alte da.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Sicherungen liegen unter Admin → Backups und lassen sich " +
          "dort herunterladen.",
      },
    ],
  },
  {
    id: "2026-07-status-emojis",
    label: "Changelog: Status-Emojis",
    summary: "Eigene Emojis im Status-Panel",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#3ba55d",
    blocks: [
      {
        type: "text",
        text:
          "# ✨ Changelog · Status-Panel\n" +
          "### Jetzt mit unseren eigenen Emojis",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Das Status-Panel benutzt ab sofort die eigenen Emojis statt " +
          "der Standard-Kreise — für Online, Störung, Startvorgang, " +
          "Laufzeit und die Knöpfe.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Falls Discord sie mal nicht liefert, fällt das Panel " +
          "automatisch auf die normalen Symbole zurück — es bleibt " +
          "immer lesbar.",
      },
    ],
  },
  {
    id: "2026-07-j2c-fix",
    label: "Changelog: Join to Create",
    summary: "Zwei Fehler behoben, warum Einstellungen nicht wirkten",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#faa61a",
    blocks: [
      {
        type: "text",
        text:
          "# 🔧 Changelog · Join to Create\n" +
          "### Zwei Fehler behoben, die das Einstellen wirkungslos machten",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Wer Join to Create im Dashboard eingestellt hat, bei dem ist " +
          "unter Umständen **nichts passiert**. Zwei Ursachen, beide " +
          "gefunden und behoben.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was kaputt war\n\n" +
          "> 🗄️ **Ältere Server** — auf Servern, die den Bot schon länger " +
          "nutzen, brach das Laden mit einem Datenbankfehler ab. Der Bot " +
          "hat die Einstellung nie zu sehen bekommen, obwohl das " +
          "Dashboard sie als gespeichert anzeigte.\n" +
          "> 🔌 **Ausschalten wirkte nicht** — nach dem Abschalten hat der " +
          "Bot bis zum nächsten Neustart weiter Kanäle angelegt.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Falls es bei euch nicht ging: einmal neu einstellen, " +
          "jetzt greift es sofort.",
      },
    ],
  },
  {
    id: "2026-07-status-panel",
    label: "Changelog: Status-Panel",
    summary: "Statusanzeige neu gebaut, ein Abschnitt pro Bot",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#3ba55d",
    blocks: [
      {
        type: "text",
        text:
          "# 📊 Changelog · Status-Panel\n" +
          "### Neu gebaut, übersichtlicher, ein Abschnitt pro Bot",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Die Statusanzeige im Status-Kanal war eine lange Liste mit " +
          "allen Links unten dran. Jetzt hat **jeder Bot seinen eigenen " +
          "Abschnitt** — mit Profilbild, Zustand, Messwerten und seinen " +
          "eigenen Knöpfen darunter.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was sich geändert hat\n\n" +
          "> 🖼️ **Profilbilder** — beide Bots stehen mit ihrem echten " +
          "Discord-Bild im Panel.\n" +
          "> 🎯 **Knöpfe gehören zum Bot** — vorher hingen alle Links " +
          "unten in einer Reihe.\n" +
          "> ⏱️ **Live-Zeitstempel** — zählt sich selbst hoch und zeigt " +
          "**eure** Zeitzone statt UTC.\n" +
          "> 🧹 **Support-Knopf raus** — das Panel steht im " +
          "Support-Server, der Link zeigte auf diesen Raum hier.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Mit `/status` erzwingt ihr jederzeit eine sofortige Prüfung.",
      },
    ],
  },
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
