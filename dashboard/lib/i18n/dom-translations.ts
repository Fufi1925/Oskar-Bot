import { Language } from "./translations";

/**
 * Phrase-level translations for legacy dashboard text that is still hard-coded
 * inside pages/components. The dashboard already has a proper `t()` helper for
 * new code, but this bridge makes the language switcher apply consistently
 * across the existing UI without rewriting every page by hand.
 */
export const phrasePairs: Array<[de: string, en: string]> = [
  // Navigation / generic
  ["Dashboard", "Dashboard"],
  ["Server", "Servers"],
  ["Admin", "Admin"],
  ["Einstellungen", "Settings"],
  ["Abmelden", "Logout"],
  ["Anmelden", "Login"],
  ["Abbrechen", "Cancel"],
  ["Speichern", "Save"],
  ["Löschen", "Delete"],
  ["Aktivieren", "Enable"],
  ["Deaktivieren", "Disable"],
  ["Aktiviert", "Enabled"],
  ["Deaktiviert", "Disabled"],
  ["Laden...", "Loading..."],
  ["Fehler", "Error"],
  ["Erfolg", "Success"],
  ["Erneut versuchen", "Retry"],
  ["Mitglieder", "Members"],
  ["Kanäle", "Channels"],
  ["Rollen", "Roles"],
  ["Sprache", "Language"],
  ["Deutsch", "German"],
  ["Englisch", "English"],
  ["Suche", "Search"],
  ["Status", "Status"],
  ["Aktiv", "Active"],
  ["Inaktiv", "Inactive"],
  ["Gesamt", "Total"],
  ["Zurück", "Back"],

  // Landing page
  ["Dashboard öffnen", "Open Dashboard"],
  ["Zum Server hinzufügen", "Add to Server"],
  ["Funktionen", "Features"],
  ["Architektur", "Architecture"],
  ["Module", "Modules"],
  ["Netzwerk", "Network"],
  ["Kostenlos starten", "Get Started Free"],
  ["Wissensdatenbank", "Knowledge Base"],
  ["Häufig gestellte Fragen", "Frequently Asked Questions"],
  ["Bereit zur", "Ready to"],
  ["Evolution?", "Evolve?"],
  ["Moderiert.", "Moderated."],
  ["Weltweit", "Global"],
  ["Weltweit erreichbar.", "Globally reachable."],
  ["Erreichbar.", "Reachable."],
  ["Weltweit Uptime", "Global Uptime"],
  ["Konsole öffnen", "Initialize Console"],
  ["Mit Discord anmelden", "Login with Discord"],
  ["Login-Fehler", "Login Error"],
  ["Dokumentation", "Documentation"],
  ["API-Referenz", "API Reference"],
  ["Datenschutz", "Privacy"],
  ["Nutzungsbedingungen", "Terms of Service"],
  ["Discord Server", "Discord Server"],
  ["GitHub Repository", "GitHub Repository"],
  ["System", "System"],
  ["Identität", "Identity"],
  ["Identity", "Identity"],
  ["Join 5,000+ communities scaling their automation with the University Bot Engine. Setup takes less than 30 seconds.", "Join 5,000+ communities scaling their automation with the University Bot Engine. Setup takes less than 30 seconds."],
  ["Schließe dich 5.000+ Communities an, die ihre Automatisierung mit der University Bot Engine skalieren. Die Einrichtung dauert weniger als 30 Sekunden.", "Join 5,000+ communities scaling their automation with the University Bot Engine. Setup takes less than 30 seconds."],

  // Auth diagnostics
  ["Diagnose", "Diagnostics"],
  ["• Discord Developer Portal: Prüfe OAuth2 Redirect URI", "• Discord Developer Portal: Check OAuth2 Redirect URI"],
  ["• Railway: Prüfe DISCORD_CLIENT_ID und DISCORD_CLIENT_SECRET", "• Railway: Check DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET"],
  ["• Railway: Prüfe NEXTAUTH_URL (ohne /api/auth/ Pfad)", "• Railway: Check NEXTAUTH_URL (without /api/auth/ path)"],
  ["• Railway: Prüfe NEXTAUTH_SECRET (mindestens 32 Zeichen)", "• Railway: Check NEXTAUTH_SECRET (at least 32 characters)"],

  // Dashboard shell
  ["Authentifizierung...", "Authenticating..."],
  ["Authenticating...", "Authenticating..."],
  ["Dashboard", "Dashboard"],
  ["Server", "Servers"],
  ["Admin Panel", "Admin Panel"],
  ["Zurück zu Servern", "Back to Servers"],
  ["Back to Server", "Back to Servers"],
  ["Übersicht", "Overview"],
  ["Sicherheit", "Security"],
  ["Engagement", "Engagement"],
  ["Dienstprogramme", "Utility"],
  ["Utility", "Utility"],
  ["Begrüßung", "Welcome"],
  ["Level-System", "Leveling"],
  ["Vanity-Rollen", "Vanity Roles"],
  ["Autorolle", "Auto Role"],
  ["Auto-Reaktion", "Auto React"],
  ["Reaktions-Rollen", "Reaction Roles"],
  ["Beitritts-DM", "Join DM"],
  ["Einladungen", "Invites"],
  ["Sprach-Rolle", "Voice Role"],
  ["Eigene Rollen", "Custom Roles"],
  ["Server verwalten", "Manage Server"],
  ["Support Matrix", "Support Matrix"],
  ["Deautorisieren", "Deauthorize"],
  ["Deauthorize", "Deauthorize"],
  ["Authentifiziert als", "Authenticated As"],
  ["Authenticated As", "Authenticated As"],
  ["Aktiv", "Active"],
  ["Benutzer", "User"],
  ["Broadcast-Metriken", "Broadcast Metrics"],
  ["Broadcast Metrics", "Broadcast Metrics"],
  ["System-Broadcast", "System Broadcast"],
  ["System Broadcast", "System Broadcast"],
  ["Keine aktiven Broadcasts", "No active broadcasts"],
  ["No active broadcasts", "No active broadcasts"],
  ["Alles läuft normal", "Everything is operating normally"],
  ["Everything is operating normally", "Everything is operating normally"],
  ["Löschen", "Clear"],
  ["Clear", "Clear"],
  ["Neuronales Netzwerk abfragen...", "Query neural network..."],
  ["Query neural network...", "Query neural network..."],
  ["Systemfehler erkannt", "System Fault Detected"],
  ["System Fault Detected", "System Fault Detected"],
  ["System wird initialisiert", "Initializing System"],
  ["Initializing System", "Initializing System"],
  ["Parameter werden vom Edge-Cortex geladen...", "Fetching parameters from edge cortex..."],
  ["Fetching parameters from edge cortex...", "Fetching parameters from edge cortex..."],

  // Dashboard home
  ["Systemkern.", "System Core."],
  ["System", "System"],
  ["Core.", "Core."],
  ["Status und Live-Metriken für", "Status and live metrics for"],
  ["Status and live metrics for", "Status and live metrics for"],
  ["Gesamte Server", "Total Guilds"],
  ["Total Guilds", "Total Guilds"],
  ["Gesamte Benutzer", "Total Users"],
  ["Total Users", "Total Users"],
  ["Systemlaufzeit", "System Uptime"],
  ["System Uptime", "System Uptime"],
  ["API-Latenz", "API Latency"],
  ["API Latency", "API Latency"],
  ["Schnellaktionen", "Quick Actions"],
  ["Quick Actions", "Quick Actions"],
  ["Effizienz", "Efficiency"],
  ["Efficiency", "Efficiency"],
  ["Server verwalten", "Manage Servers"],
  ["Manage Servers", "Manage Servers"],
  ["Zeige und konfiguriere deine Discord-Server.", "View and configure your Discord guilds."],
  ["View and configure your Discord guilds.", "View and configure your Discord guilds."],
  ["Globale Einstellungen", "Global Settings"],
  ["Global Settings", "Global Settings"],
  ["Passe deine persönlichen Dashboard-Einstellungen an.", "Adjust your personal dashboard preferences."],
  ["Adjust your personal dashboard preferences.", "Adjust your personal dashboard preferences."],
  ["Support-Matrix", "Support Matrix"],
  ["Hole Hilfe von unserem neuralen Support-Team.", "Get help from our neural support team."],
  ["Get help from our neural support team.", "Get help from our neural support team."],
  ["Lerne, wie du die University Bot Engine meisterst.", "Learn how to master the University Bot engine."],
  ["Learn how to master the University Bot engine.", "Learn how to master the University Bot engine."],
  ["Modulstatus", "Module Status"],
  ["Module Status", "Module Status"],
  ["Globaler Betriebszustand des University Bot Kerns.", "Global operational health of University Bot core."],
  ["Global operational health of University Bot core.", "Global operational health of University Bot core."],
  ["Neurales Gateway", "Neural Gateway"],
  ["Neural Gateway", "Neural Gateway"],
  ["Datenbank-Cluster", "Database Cluster"],
  ["Database Cluster", "Database Cluster"],
  ["Edge-Shards", "Edge Shards"],
  ["Edge Shards", "Edge Shards"],
  ["Optimal", "Optimal"],
  ["Synchronisiert", "Synchronized"],
  ["Synchronized", "Synchronized"],
  ["Betriebsbereit", "Operational"],
  ["Operational", "Operational"],
  ["Systemdiagnose", "System Diagnostics"],
  ["System Diagnostics", "System Diagnostics"],

  // Guilds
  ["Deine Server", "Your Servers"],
  ["Your Servers", "Your Servers"],
  ["Wähle einen Server um Einstellungen und Module zu verwalten.", "Select a server to manage settings and modules."],
  ["Select a server to manage settings and modules.", "Select a server to manage settings and modules."],
  ["Verbunden", "Connected"],
  ["Admin-Rechte", "Admin Rights"],
  ["Verbindungsfehler", "Connection Error"],
  ["Connection Error", "Connection Error"],
  ["Bot verbundene Server", "Bot connected servers"],
  ["Bot connected servers", "Bot connected servers"],
  ["Server ohne Bot", "Servers without bot"],
  ["Servers without bot", "Servers without bot"],
  ["Bot fehlt", "Bot missing"],
  ["Bot missing", "Bot missing"],
  ["Bot einladen", "Invite bot"],
  ["Invite bot", "Invite bot"],
  ["Keine Admin-Rechte", "No admin rights"],
  ["No admin rights", "No admin rights"],
  ["Du hast auf keinem Server Administrator- oder Server-verwalten Rechte.", "You do not have administrator or manage server permissions on any server."],
  ["You do not have administrator or manage server permissions on any server.", "You do not have administrator or manage server permissions on any server."],
  ["Keine Server gefunden", "No servers found"],
  ["No servers found", "No servers found"],
  ["Du bist auf keinem Discord-Server Mitglied.", "You are not a member of any Discord server."],
  ["You are not a member of any Discord server.", "You are not a member of any Discord server."],
  ["Keine Server gefunden", "No Servers Found"],
  ["Keine Admin-Rechte", "No Admin Rights"],
  ["GUILD ID", "GUILD ID"],

  // Guild overview
  ["Zugriff verweigert", "Access Denied"],
  ["Access Denied", "Access Denied"],
  ["Zurück zu Servern", "Back to Servers"],
  ["Server Owner Dashboard", "Server Owner Dashboard"],
  ["Serverinhaber-Dashboard", "Server Owner Dashboard"],
  ["Aktive Module", "Active Modules"],
  ["Aktiv Modules", "Active Modules"],
  ["Active Modules", "Active Modules"],
  ["Systemkonsole", "System Console"],
  ["System Console", "System Console"],
  ["Dashboard mit WebSocket-Pool verbunden...", "Dashboard connected to WebSocket pool..."],
  ["Dashboard connected to WebSocket pool...", "Dashboard connected to WebSocket pool..."],
  ["Guild-Konfiguration wird aus primärer Datenbank geladen...", "Fetching guild_config from primary database..."],
  ["Fetching guild_config from primary database...", "Fetching guild_config from primary database..."],
  ["Cache erfolgreich synchronisiert.", "Cache synchronized successfully."],
  ["Cache synchronized successfully.", "Cache synchronized successfully."],
  ["Datenbankstatus", "Database Status"],
  ["Database Status", "Database Status"],
  ["Alle Serverdaten sind verschlüsselt und über unser leistungsstarkes Edge-Netzwerk repliziert.", "All guild data is encrypted and replicated across our high-performance edge network."],
  ["All guild data is encrypted and replicated across our high-performance edge network.", "All guild data is encrypted and replicated across our high-performance edge network."],
  ["Sicherheitskontext", "Security Context"],
  ["Security Context", "Security Context"],
  ["Vertrauensfaktor", "Trust Factor"],
  ["Trust Factor", "Trust Factor"],
  ["Bot ist vollständig mit Administratorrechten authentifiziert.", "Bot is fully authenticated with administrator privileges."],
  ["Bot is fully authenticated with administrator privileges.", "Bot is fully authenticated with administrator privileges."],

  // Module descriptions / forms
  ["Schütze deinen Server vor bösartigen Massenlöschungen, Massenbanns und anderen zerstörerischen Aktionen.", "Protect your server from malicious mass-deletion, mass-banning, and other destructive actions."],
  ["Protect your server from malicious mass-deletion, mass-banning, and other destructive actions.", "Protect your server from malicious mass-deletion, mass-banning, and other destructive actions."],
  ["Schütze deine Community mit automatisierten Filtersystemen.", "Protect your community with automated filter systems."],
  ["Protect your community with automated filter systems.", "Protect your community with automated filter systems."],
  ["Neue Mitglieder und Bots automatisch Rollen zuweisen.", "Automatically assign roles to new members and bots."],
  ["Automatically assign roles to new members and bots.", "Automatically assign roles to new members and bots."],
  ["Aktive Mitglieder mit XP und Rangfortschritt belohnen.", "Reward active members with XP and rank progressions."],
  ["Reward active members with XP and rank progressions.", "Reward active members with XP and rank progressions."],
  ["Neue Mitglieder auf deinem Server begrüßen.", "Greet new members to your server."],
  ["Greet new members to your server.", "Greet new members to your server."],
  ["Ereignisse und Versandrouten für deinen Server konfigurieren.", "Configure events and dispatch routes for your server."],
  ["Configure events and dispatch routes for your server.", "Configure events and dispatch routes for your server."],
  ["Private Support-Kanäle und Anfragekategorien verwalten.", "Manage private support channels and inquiry categories."],
  ["Manage private support channels and inquiry categories.", "Manage private support channels and inquiry categories."],
  ["Ein Gatekeeper-System zur Verifizierung neuer Mitglieder einrichten.", "Set up a gatekeeper system to verify new members."],
  ["Set up a gatekeeper system to verify new members.", "Set up a gatekeeper system to verify new members."],
  ["Kernkonfiguration des Bots für diesen Server verwalten.", "Manage core bot configuration for this server."],
  ["Manage core bot configuration for this server.", "Manage core bot configuration for this server."],
  ["Temporäre Sprachkanäle einrichten, die automatisch erstellt werden, wenn ein Mitglied einem bestimmten Kanal beitritt.", "Set up temporary voice channels that are created automatically when a member joins a specific channel."],
  ["Set up temporary voice channels that are created automatically when a member joins a specific channel.", "Set up temporary voice channels that are created automatically when a member joins a specific channel."],
  ["Mitgliedern erlauben, sich durch Reaktion auf eine Nachricht selbst Rollen zu geben.", "Allow members to self-assign roles by reacting to a message."],
  ["Allow members to self-assign roles by reacting to a message.", "Allow members to self-assign roles by reacting to a message."],
  ["Spezielle Rollen für Mitglieder mit deinem Vanity-/Invite-Link im Status vergeben.", "Give special roles to members with your vanity/invite link in their status."],
  ["Give special roles to members with your vanity/invite link in their status.", "Give special roles to members with your vanity/invite link in their status."],
  ["Vordefinierte Rollen konfigurieren, die einfach per Command zugewiesen werden können.", "Configure predefined roles that can be easily assigned using commands."],
  ["Configure predefined roles that can be easily assigned using commands.", "Configure predefined roles that can be easily assigned using commands."],
  ["Automatisch mit Emojis reagieren, wenn bestimmte Trigger-Wörter gesendet werden.", "Automatically react with emojis when specific trigger words are sent."],
  ["Automatically react with emojis when specific trigger words are sent.", "Automatically react with emojis when specific trigger words are sent."],
  ["Automatisch eine Rolle zuweisen, wenn Mitglieder einem Sprachkanal beitreten.", "Automatically assign a role when members join a voice channel."],
  ["Automatically assign a role when members join a voice channel.", "Automatically assign a role when members join a voice channel."],
  ["Top-Einlader im Server basierend auf verfolgten Beitritten.", "Top inviters in the server based on tracked join events."],
  ["Top inviters in the server based on tracked join events.", "Top inviters in the server based on tracked join events."],

  // AutoReact
  ["Trigger hinzufügen", "Add Trigger"],
  ["Add Trigger", "Add Trigger"],
  ["Keine Trigger konfiguriert", "No triggers configured"],
  ["No triggers configured", "No triggers configured"],
  ["Beginne mit deinem ersten Auto-Reaction-Trigger.", "Start by adding your first auto-reaction trigger."],
  ["Start by adding your first auto-reaction trigger.", "Start by adding your first auto-reaction trigger."],
  ["Ersten Trigger hinzufügen", "Add Your First Trigger"],
  ["Add Your First Trigger", "Add Your First Trigger"],
  ["Trigger-Wort (ein Wort)", "Trigger Word (single word)"],
  ["Trigger Word (single word)", "Trigger Word (single word)"],
  ["Emojis (durch Leerzeichen getrennt)", "Emojis (space separated)"],
  ["Emojis (space separated)", "Emojis (space separated)"],
  ["So funktioniert es", "How It Works"],
  ["How It Works", "How It Works"],
  ["• Trigger sind einzelne Wörter, auf die der Bot achtet.", "• Triggers are single words that the bot watches for."],
  ["• Triggers are single words that the bot watches for.", "• Triggers are single words that the bot watches for."],
  ["• Wenn eine Nachricht einen Trigger enthält, reagiert der Bot mit den konfigurierten Emojis.", "• When a message contains a trigger, the bot reacts with the configured emojis."],
  ["• When a message contains a trigger, the bot reacts with the configured emojis.", "• When a message contains a trigger, the bot reacts with the configured emojis."],
  ["• Bis zu 10 Emojis pro Trigger und maximal 10 Trigger pro Server.", "• Up to 10 emojis per trigger, and 10 triggers max per guild."],
  ["• Up to 10 emojis per trigger, and 10 triggers max per guild.", "• Up to 10 emojis per trigger, and 10 triggers max per guild."],
  ["• Eigene Emojis müssen von diesem Server stammen.", "• Custom emojis must be from this server."],
  ["• Custom emojis must be from this server.", "• Custom emojis must be from this server."],

  // Common form labels
  ["Systemstatus", "System Status"],
  ["System Status", "System Status"],
  ["Master-Steuerung", "Master Control"],
  ["Master Control", "Master Control"],
  ["Geschützt", "Protected"],
  ["Protected", "Protected"],
  ["Log-Kanal", "Log Channel"],
  ["Log Channel", "Log Channel"],
  ["Logging-Konfiguration", "Logging Configuration"],
  ["Logging Configuration", "Logging Configuration"],
  ["Information", "Information"],
  ["Nachrichteninhalt", "Message Content"],
  ["Message Content", "Message Content"],
  ["Willkommensnachricht", "Welcome Message"],
  ["Welcome Message", "Welcome Message"],
  ["Nutzungshinweis", "Usage Note"],
  ["Usage Note", "Usage Note"],
  ["Nachrichten-ID", "Message ID"],
  ["Message ID", "Message ID"],
  ["Emoji", "Emoji"],
  ["Zuzuweisende Rolle", "Role to Assign"],
  ["Role to Assign", "Role to Assign"],
  ["Rolle", "Role"],
  ["Role", "Role"],
  ["Anleitung", "Usage Guide"],
  ["Usage Guide", "Usage Guide"],
  ["DM-Benachrichtigungen", "DM Notifications"],
  ["DM Notifications", "DM Notifications"],
  ["Sende eine DM, wenn ein Benutzer eine Rolle erhält/verliert.", "Send a DM when a user gets/loses a role."],
  ["Send a DM when a user gets/loses a role.", "Send a DM when a user gets/loses a role."],
  ["Neue Reaktionsrolle erstellen", "Create New Reaction Role"],
  ["Create New Reaction Role", "Create New Reaction Role"],
  ["Aktive Reaktionsrollen", "Active Reaction Roles"],
  ["Active Reaction Roles", "Active Reaction Roles"],
  ["Keine Reaktionsrollen konfiguriert.", "No reaction roles configured."],
  ["No reaction roles configured.", "No reaction roles configured."],
  ["Unbekannte Rolle", "Unknown Role"],
  ["Unknown Role", "Unknown Role"],
  ["Vanity-Text / URL", "Vanity Text / URL"],
  ["Vanity Text / URL", "Vanity Text / URL"],
  ["Zu vergebende Rolle", "Role to Give"],
  ["Role to Give", "Role to Give"],
  ["Aktive Setups", "Active Setups"],
  ["Active Setups", "Active Setups"],
  ["Noch keine Vanity-Rollen konfiguriert.", "No vanity role setups configured yet."],
  ["No vanity role setups configured yet.", "No vanity role setups configured yet."],
  ["Vanity-Text", "Vanity Text"],
  ["Vanity Text", "Vanity Text"],
  ["Neues Vanity-Setup hinzufügen", "Add New Vanity Setup"],
  ["Add New Vanity Setup", "Add New Vanity Setup"],
  ["Verifizierungskanal", "Verification Channel"],
  ["Verification Channel", "Verification Channel"],
  ["Verifizierte Rolle", "Verified Role"],
  ["Verified Role", "Verified Role"],
  ["Verifizierungsmethode", "Verification Method"],
  ["Verification Method", "Verification Method"],
  ["Nicht gesetzt", "Not Set"],
  ["Not Set", "Not Set"],
  ["Button-Klick", "Button Click"],
  ["Button Click", "Button Click"],
  ["CAPTCHA-Bild", "CAPTCHA Image"],
  ["CAPTCHA Image", "CAPTCHA Image"],
  ["Beides (kombiniert)", "Both (Combined)"],
  ["Both (Combined)", "Both (Combined)"],
  ["Wichtig", "Important"],
  ["Important", "Important"],
  ["Live-System", "Live System"],
  ["Live System", "Live System"],
  ["Rang", "Rank"],
  ["Rank", "Rank"],
  ["Benutzer", "User"],
  ["Stufe", "Level"],
  ["Level", "Level"],
  ["Gesamt-XP", "Total XP"],
  ["Total XP", "Total XP"],
  ["Keine weiteren Mitglieder gerankt...", "No additional members ranked yet..."],
  ["No additional members ranked yet...", "No additional members ranked yet..."],
  ["aktive Wettbewerber", "active competitors"],
  ["active competitors", "active competitors"],
  ["Globale Rangliste wird synchronisiert...", "Syncing global rankings..."],
  ["Syncing global rankings...", "Syncing global rankings..."],
  ["Top-Beitragende nach Erfahrung und Aktivität.", "Top contributors by experience and activity."],
  ["Top contributors by experience and activity.", "Top contributors by experience and activity."],

  // Docs/legal
  ["University Bot Dokumentation", "University Bot Docs"],
  ["University Bot Docs", "University Bot Docs"],
  ["Schnelle Ausführung", "Fast Dispatch"],
  ["Fast Dispatch", "Fast Dispatch"],
  ["Sicherer Knoten", "Secure Node"],
  ["Secure Node", "Secure Node"],
  ["Neurale Architektur", "Neural Architecture"],
  ["Neural Architecture", "Neural Architecture"],
  ["Protokollübersicht", "Protocol Overview"],
  ["Protocol Overview", "Protocol Overview"],
  ["Interne Referenz", "Internal Ref"],
  ["Internal Ref", "Internal Ref"],
  ["Live-Stream aktiv", "Live Stream Active"],
  ["Live Stream Active", "Live Stream Active"],
  ["Richtlinie.", "Policy."],
  ["Policy.", "Policy."],
  ["Datenerfassung", "Data Collection"],
  ["Data Collection", "Data Collection"],
  ["Datenintegrität", "Data Integrity"],
  ["Data Integrity", "Data Integrity"],
  ["Nutzerrechte", "User Rights"],
  ["User Rights", "User Rights"],
  ["Dienst.", "Service."],
  ["Service.", "Service."],
  ["Akzeptanz des Protokolls", "Acceptance of Protocol"],
  ["Acceptance of Protocol", "Acceptance of Protocol"],
  ["Nutzungsbeschränkungen", "Usage Constraints"],
  ["Usage Constraints", "Usage Constraints"],
  ["API & Skalierung", "API & Scaling"],
  ["API & Scaling", "API & Scaling"],
];

function normalise(text: string) {
  return text.replace(/\s+/g, " ").trim();
}

function preserveWhitespace(original: string, translated: string) {
  const leading = original.match(/^\s*/)?.[0] ?? "";
  const trailing = original.match(/\s*$/)?.[0] ?? "";
  return `${leading}${translated}${trailing}`;
}

function buildMap(language: Language) {
  const map = new Map<string, string>();
  for (const [de, en] of phrasePairs) {
    if (language === "de") {
      map.set(normalise(en), de);
    } else {
      map.set(normalise(de), en);
    }
  }
  return map;
}

function translateValue(value: string, map: Map<string, string>) {
  const key = normalise(value);
  if (!key) return value;
  const translated = map.get(key);
  return translated ? preserveWhitespace(value, translated) : value;
}

function shouldSkipNode(node: Node) {
  const parent = node.parentElement;
  if (!parent) return true;
  if (parent.closest("script,style,noscript,code,pre,textarea,[data-no-translate]")) return true;
  return false;
}

export function translateDashboardDom(language: Language, root: ParentNode = document) {
  if (typeof document === "undefined") return;
  const map = buildMap(language);

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (shouldSkipNode(node)) return NodeFilter.FILTER_REJECT;
      return normalise(node.textContent || "") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });

  const textNodes: Text[] = [];
  while (walker.nextNode()) {
    textNodes.push(walker.currentNode as Text);
  }

  for (const node of textNodes) {
    const current = node.textContent || "";
    const translated = translateValue(current, map);
    if (translated !== current) node.textContent = translated;
  }

  const selector = "input[placeholder], textarea[placeholder], [title], [aria-label]";
  root.querySelectorAll?.(selector).forEach((element) => {
    for (const attr of ["placeholder", "title", "aria-label"]) {
      const value = element.getAttribute(attr);
      if (!value) continue;
      const translated = translateValue(value, map);
      if (translated !== value) element.setAttribute(attr, translated);
    }
  });
}
