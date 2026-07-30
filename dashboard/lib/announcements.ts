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
    id: "2026-07-counting-neustart",
    label: "Changelog: Counting-Neustart",
    summary: "Fehler = Kanal komplett leer und Regeln wieder oben",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#ed4245",
    blocks: [
      {
        type: "text",
        text:
          "# 🧹 Changelog · Counting\n" +
          "### Nach einem Fehler beginnt wirklich alles von vorn",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Bisher blieb nach einem Fehler der ganze Verlauf stehen: " +
          "Ihr wart bei **833**, jemand schrieb die falsche Zahl, der " +
          "Zähler sprang auf 0 — und im Kanal standen weiter 800 alte " +
          "Zahlen, mit den Regeln ganz oben, wo sie niemand mehr sah.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was jetzt passiert\n\n" +
          "> 🧹 Fällt der Zähler auf **0**, wird der Kanal " +
          "**komplett geleert** — egal wie viele Nachrichten drin " +
          "sind.\n" +
          "> 📋 Danach stehen die **Regeln wieder ganz oben**, als " +
          "einzige Nachricht im Kanal.\n" +
          "> 📉 Auf der Karte steht, **wer** die Kette gerissen hat " +
          "und **wie weit** ihr gekommen wart — die Info geht also " +
          "nicht mit den Nachrichten verloren.\n" +
          "> 🏆 Der **Rekord bleibt** erhalten.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Kleingedrucktes\n\n" +
          "> ⏳ Nachrichten, die älter als 14 Tage sind, muss Discord " +
          "einzeln löschen. Das dauert länger, sie werden aber " +
          "trotzdem entfernt.\n" +
          "> 🔐 Fehlt dem Bot das Recht **„Nachrichten verwalten“**, " +
          "kann er nicht aufräumen — dann meldet er den Fehler wie " +
          "bisher, statt kommentarlos nichts zu tun.\n" +
          "> 🎛️ Wer das nicht will, stellt unter „Bei einem Fehler“ " +
          "auf **Weiterzählen** — dann wird nie geleert.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Kleine Richtigstellung zur letzten Meldung: Nachrichten " +
          "über 14 Tage werden **doch** gelöscht, nur langsamer. Das " +
          "hatten wir falsch angekündigt.",
      },
    ],
  },
  {
    id: "2026-07-counting-live",
    label: "Changelog: Counting",
    summary: "Regel-Nachricht zählt live mit, Neustart räumt den Kanal auf",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#3ba55d",
    blocks: [
      {
        type: "text",
        text:
          "# 🔢 Changelog · Counting\n" +
          "### Die Regeln zeigen jetzt den echten Stand",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Bisher war die Regel-Nachricht eine Momentaufnahme: Sobald " +
          "jemand weitergezählt hatte, stimmten „Als Nächstes“ und der " +
          "Rekord darin nicht mehr.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was neu ist\n\n" +
          "> 🔄 **Die Regel-Nachricht hält sich selbst aktuell.** " +
          "„Als Nächstes“ und der Rekord werden mitgeschrieben — die " +
          "Nachricht wird bearbeitet, nicht ständig neu gepostet.\n" +
          "> 🧹 **Ein Knopf startet das Spiel neu.** „Kanal leeren & " +
          "Regeln posten“ räumt den Zähl-Kanal frei, postet die Regeln " +
          "und stellt den Zähler auf 0.\n" +
          "> 🏆 **Der Rekord bleibt** dabei erhalten — nur die laufende " +
          "Runde beginnt von vorn.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Gut zu wissen\n\n" +
          "> ⏱️ Die Nachricht wird höchstens alle paar Sekunden " +
          "aktualisiert. Bei schnellem Zählen bleibt sie so trotzdem " +
          "lesbar, ohne dass Discord uns ausbremst.\n" +
          "> 🗑️ Wird die Regel-Nachricht gelöscht, merkt der Bot das " +
          "und hört auf, sie zu suchen.\n" +
          "> 📅 Nachrichten, die **älter als 14 Tage** sind, kann " +
          "Discord nicht auf einmal löschen — die bleiben stehen. Der " +
          "Bot sagt es dazu.\n" +
          "> 🔐 Dafür braucht der Bot im Kanal das Recht " +
          "**„Nachrichten verwalten“**.",
      },
      { type: "divider" },
      {
        type: "text",
        text: "-# Zu finden im Dashboard unter Counting → Zähler verwalten.",
      },
    ],
  },
  {
    id: "2026-07-fehler-sichtbar",
    label: "Changelog: Fehlermeldungen",
    summary: "Abstürze verschwanden spurlos, Befehle in DMs stürzten ab",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#faa61a",
    blocks: [
      {
        type: "text",
        text:
          "# 🛟 Changelog · Fehlermeldungen\n" +
          "### Wenn ein Befehl einfach nichts tat",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Ging in einem Befehl etwas schief, das nicht vorhergesehen " +
          "war, passierte **gar nichts**: keine Antwort für euch, keine " +
          "Zeile im Log für uns. Der Befehl sah aus, als hättet ihr ihn " +
          "nie abgeschickt.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was kaputt war\n\n" +
          "> 🕳️ **Unbekannte Fehler fielen ins Nichts.** Zwölf bekannte " +
          "Fälle wurden behandelt, danach hörte die Behandlung einfach " +
          "auf — ohne Meldung, ohne Protokoll.\n" +
          "> 💥 **Befehle in Privatnachrichten stürzten ab.** Die " +
          "Prüfung der Ignorier-Liste ist serverbezogen; in einer DM " +
          "gibt es keinen Server. Die Fehlerbehandlung lief dabei " +
          "selbst auf einen Fehler.\n" +
          "> 🙈 **„Dir fehlt eine Berechtigung“ wurde verschluckt**, " +
          "wenn man auf der Ignorier-Liste stand — man bekam die " +
          "falsche Begründung zu sehen.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was jetzt gilt\n\n" +
          "> ✅ Unerwartete Fehler bekommen eine **klare Antwort**: es " +
          "liegt an uns, nicht an euch.\n" +
          "> ✅ Der vollständige **Fehlerbericht landet im Protokoll** — " +
          "wir sehen Probleme jetzt sofort statt erst nach einer " +
          "Meldung.\n" +
          "> ✅ Befehle in **Privatnachrichten** antworten wieder " +
          "richtig.\n" +
          "> ✅ Berechtigungs-Hinweise werden **nicht mehr überdeckt**.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Unbekannte Befehle bleiben still — es spamt also nichts, " +
          "wenn man sich vertippt.",
      },
    ],
  },
  {
    id: "2026-07-emojis-kaputt",
    label: "Changelog: Emojis",
    summary: "Vier tote Emojis und ein Sync, der sie nicht heilen konnte",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#ed4245",
    blocks: [
      {
        type: "text",
        text:
          "# 🧩 Changelog · Emojis\n" +
          "### Warum an manchen Stellen `<:error:139…>` stand",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "In einigen Antworten tauchte statt eines Emojis der nackte " +
          "Quelltext auf, etwa `<:error:1397218903389044776>`. Das " +
          "passiert, wenn Discord den Emoji hinter der ID nicht kennt — " +
          "dann wird der Platzhalter einfach als Text ausgegeben.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was kaputt war\n\n" +
          "> ❌ **Vier Emojis gab es nicht mehr** — `error`, das " +
          "Partner-Abzeichen, Bug-Hunter II und Hypesquad-Events. Die " +
          "Vorlagen zeigten auf gelöschte Bilder.\n" +
          "> 🔁 **Der automatische Abgleich lief ins Leere.** Er wollte " +
          "sie bei jedem Start neu hochladen, kam an die Bilder nicht " +
          "heran und meldete stur `4 failures` — bei jedem Neustart, " +
          "endlos.\n" +
          "> 👑 **Die Krone war als unbewegt eingetragen**, obwohl sie " +
          "animiert ist. Ein falsches `a:` reicht schon, damit Discord " +
          "den Text stehen lässt.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was jetzt gilt\n\n" +
          "> ✅ Die vier fehlenden Emojis wurden **neu hochgeladen**, " +
          "`error` zeigt auf ein vorhandenes rotes Kreuz.\n" +
          "> ✅ Der Abgleich übernimmt das **animiert-Kennzeichen von " +
          "Discord** statt aus der eigenen Vorlage — der Krone-Fehler " +
          "kann sich so selbst reparieren.\n" +
          "> ✅ Beim Herunterladen werden jetzt **mehrere Bildformate** " +
          "probiert statt nur einem.\n" +
          "> ✅ Gegen die echte Discord-Schnittstelle geprüft: " +
          "**142 von 142 passen, keine Fehlschläge.**",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Ein Test wacht ab sofort darüber, dass keine ID, kein " +
          "Name und kein animiert-Kennzeichen mehr auseinanderlaufen.",
      },
    ],
  },
  {
    id: "2026-07-logs",
    label: "Changelog: Logs",
    summary: "Reaktionen wurden nie geloggt, Rollen im falschen Reiter",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#ed4245",
    blocks: [
      {
        type: "text",
        text:
          "# 📋 Changelog · Logs\n" +
          "### Zwei Fehler behoben, drei Ereignisse ergänzt",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Der Reiter heißt jetzt **Logs** statt „Protokollierung“ — " +
          "kürzer und das, was ohnehin alle sagen. Unter dem alten " +
          "Namen ist er weiterhin auffindbar.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was kaputt war\n\n" +
          "> 😀 **Reaktionen** wurden nur erfasst, solange die Nachricht " +
          "noch im Zwischenspeicher des Bots lag — auf einem lebhaften " +
          "Server sind das ein paar Minuten. Bei allem, was älter war, " +
          "kam schlicht nichts an. Jetzt wird jede Reaktion erfasst, " +
          "egal wie alt die Nachricht ist.\n" +
          "> 🎭 **Rollenvergabe** landete unter „Moderation“. Wer die " +
          "Kategorie **Rollen** eingeschaltet und dann eine Rolle " +
          "vergeben hat, sah nichts — nicht zu unterscheiden von einem " +
          "kaputten Bot. Steht jetzt unter Rollen, samt der Person, die " +
          "sie vergeben hat.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Neu erfasst\n\n" +
          "> 🧹 **Massenlöschungen** — beim Aufräumen von hundert " +
          "Nachrichten blieb bisher **keinerlei** Spur zurück. Jetzt ein " +
          "Eintrag mit Anzahl, verantwortlicher Person und einer " +
          "Leseprobe.\n" +
          "> 🧵 **Threads**, die erstellt oder gelöscht werden.\n" +
          "> 🔗 **Einladungen** — über eine Einladung kommt ein Raid " +
          "herein, das gehört ins Log.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Im Reiter gibt es jetzt dauerhaft „Alles hierhin " +
          "protokollieren“ und „Alle Arten ausschalten“ — statt neun " +
          "einzelner Schalter.",
      },
    ],
  },
  {
    id: "2026-07-status-service",
    label: "Changelog: Störungsmeldungen",
    summary: "Ausfallmeldung, Uptime, Wartungsmodus, Statusseite",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#3ba55d",
    blocks: [
      {
        type: "text",
        text:
          "# 🚨 Changelog · Störungen\n" +
          "### Ihr erfahrt es jetzt, statt es zu merken",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Bisher änderte sich bei einer Störung nur still das " +
          "Status-Panel — wer nicht zufällig hinsah, erfuhr nichts. " +
          "Jetzt gibt es eine **Meldung mit Ping**, sobald der Bot " +
          "ausfällt, und eine **Entwarnung**, die sagt, wie lange es " +
          "gedauert hat.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was dazugekommen ist\n\n" +
          "> 📈 **Uptime-Verlauf** — das Panel zeigt die " +
          "Erreichbarkeit der letzten sieben Tage und wann die letzte " +
          "Störung war.\n" +
          "> 📊 **`/verlauf`** — Graphen für Erreichbarkeit, " +
          "Antwortzeit und Fehler. Lücken sind als Lücken gezeichnet: " +
          "„nicht gemessen“ und „alles in Ordnung“ sind zwei " +
          "verschiedene Aussagen.\n" +
          "> 🔧 **Wartungsmodus** — geplante Arbeiten werden als " +
          "Wartung angekündigt statt als Ausfall, und lösen keinen " +
          "Alarm aus.\n" +
          "> 🌐 **Statusseite** — `/status` auf der Website, ohne " +
          "Discord und ohne Anmeldung erreichbar. Genau dann, wenn " +
          "Discord selbst das Problem ist.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Und ein Fehler, der das Gegenteil bewirkte\n\n" +
          "Nach zu vielen Anfragen sperrt Discord kurzzeitig aus. Der " +
          "Status-Bot startete daraufhin sofort neu, fragte erneut an, " +
          "wurde erneut gesperrt — im Sekundentakt. Der Wächter hat die " +
          "Störung dadurch **verlängert**. Er wartet die Sperre jetzt " +
          "ab, statt dagegen anzurennen.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Es wird nur bei echten Ausfällen gemeldet. Ein Neustart " +
          "nach einem Update ist kein Alarm — sonst gewöhnt man sich " +
          "das Wegsehen an.",
      },
    ],
  },
  {
    id: "2026-07-dashboard-button",
    label: "Changelog: Dashboard-Knopf",
    summary: "Direktlink in Willkommens-DM, Hilfe und Alarmen",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#5865f2",
    blocks: [
      {
        type: "text",
        text:
          "# 🔗 Changelog · Dashboard\n" +
          "### Der Weg zu den Einstellungen ist jetzt einen Klick lang",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "In der **Willkommens-DM** und im **Hilfe-Menü** gibt es " +
          "jetzt einen Knopf, der direkt zu **eurem** Server im " +
          "Dashboard führt — nicht auf die Startseite.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Dabei aufgefallen\n\n" +
          "> 🕳️ Die Willkommens-DM hatte einen Website-Knopf mit einer " +
          "**Adresse ohne Hostnamen**. Discord zeigt so einen Knopf " +
          "brav an, er führt nur nirgendwohin.\n" +
          "> 🛡️ Beim **Anti-Nuke-Alarm** fehlte der Knopf zu den " +
          "Einstellungen vollständig — ausgerechnet bei der Meldung, " +
          "bei der man am schnellsten hinmuss. Er wurde nur " +
          "eingeblendet, wenn eine bestimmte Einstellung gesetzt war, " +
          "und die war es nie. Gemeldet hat das niemand, weil ein " +
          "fehlender Knopf wie Absicht aussieht.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Die Regel überall: keine Adresse, kein Knopf. Ein toter " +
          "Link ist schlimmer als gar keiner.",
      },
    ],
  },
  {
    id: "2026-07-legal",
    label: "Changelog: Datenschutz",
    summary: "Datenschutz, AGB und Impressum neu geschrieben",
    guilds: [BOT_GUILD_ID],
    date: "30.07.2026",
    accent: "#faa61a",
    blocks: [
      {
        type: "text",
        text:
          "# ⚖️ Changelog · Rechtliches\n" +
          "### Da stand, was gut klang — nicht, was stimmt",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "Die Datenschutzerklärung versprach **AES-256-Verschlüsselung** " +
          "und „weltweit verteilte Server“. Beides war nicht wahr: eure " +
          "Einstellungen liegen in ganz normalen Datenbankdateien auf " +
          "**einem** Server. Ein Versprechen, das man nicht hält, ist " +
          "schlimmer als eine ehrliche Beschreibung.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "## Was jetzt dasteht\n\n" +
          "> 📄 **Datenschutz** — was tatsächlich gespeichert wird, wo " +
          "es liegt, wie lange, und wie ihr es löschen lasst.\n" +
          "> 📜 **Lizenz** — der Quellcode ist nicht frei verwendbar; " +
          "Lizenz, README und Impressum behaupteten das " +
          "widersprüchlich.\n" +
          "> 🏷️ **Impressum** — die Angaben wurden vorher nur beim Bauen " +
          "eingelesen, Änderungen kamen nie an. Fehlt eine Pflichtangabe, " +
          "sagt die Seite das deutlich, statt eine Lücke zu verstecken.",
      },
      { type: "divider" },
      {
        type: "text",
        text:
          "-# Nichts von alledem ändert, was der Bot tut — nur, was " +
          "über ihn behauptet wird.",
      },
    ],
  },
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
