export type Language = "de" | "en";

export const translations = {
  de: {
    // Navigation
    dashboard: "Dashboard",
    servers: "Server",
    admin: "Admin",
    settings: "Einstellungen",
    logout: "Abmelden",
    login: "Anmelden",
    searchServers: "Server suchen...",
    
    // Landing Page
    openDashboard: "Dashboard öffnen",
    addToServer: "Zum Server hinzufügen",
    features: "Funktionen",
    architecture: "Architektur",
    modules: "Module",
    network: "Netzwerk",
    getStarted: "Kostenlos starten",
    knowledgeBase: "Wissensdatenbank",
    faq: "Häufig gestellte Fragen",
    readyToEvolve: "Bereit zur Evolution?",
    
    // Server Page
    yourServers: "Deine Server",
    selectServer: "Wähle einen Server um Einstellungen und Module zu verwalten.",
    botConnected: "Bot verbunden",
    botMissing: "Bot fehlt",
    manageServer: "Server verwalten",
    inviteBot: "Bot einladen",
    connected: "Verbunden",
    adminRights: "Admin-Rechte",
    noServers: "Keine Server gefunden",
    noAdminRights: "Keine Admin-Rechte",
    
    // Guild Tabs
    overview: "Übersicht",
    antinuke: "Antinuke",
    automod: "Automod",
    autorole: "Autorolle",
    leveling: "Level-System",
    welcome: "Begrüßung",
    logging: "Protokollierung",
    tickets: "Tickets",
    verification: "Verifizierung",
    tracking: "Tracking",
    invites: "Einladungen",
    autoReact: "Auto-Reaktion",
    joinDm: "Beitritts-DM",
    customRoles: "Eigene Rollen",
    vanityRoles: "Vanity-Rollen",
    reactionRoles: "Reaktions-Rollen",
    voiceRole: "Sprach-Rolle",
    
    // Common
    save: "Speichern",
    cancel: "Abbrechen",
    delete: "Löschen",
    enable: "Aktivieren",
    disable: "Deaktivieren",
    enabled: "Aktiviert",
    disabled: "Deaktiviert",
    loading: "Laden...",
    error: "Fehler",
    success: "Erfolg",
    retry: "Erneut versuchen",
    members: "Mitglieder",
    channels: "Kanäle",
    roles: "Rollen",
    
    // Auth
    loginWithDiscord: "Mit Discord anmelden",
    initializingConsole: "Konsole öffnen",
    loginError: "Login-Fehler",
    
    // Language
    language: "Sprache",
    german: "Deutsch",
    english: "English",
  },
  en: {
    // Navigation
    dashboard: "Dashboard",
    servers: "Servers",
    admin: "Admin",
    settings: "Settings",
    logout: "Logout",
    login: "Login",
    searchServers: "Search servers...",
    
    // Landing Page
    openDashboard: "Open Dashboard",
    addToServer: "Add to Server",
    features: "Features",
    architecture: "Architecture",
    modules: "Modules",
    network: "Network",
    getStarted: "Get Started Free",
    knowledgeBase: "Knowledge Base",
    faq: "Frequently Asked Questions",
    readyToEvolve: "Ready to Evolve?",
    
    // Server Page
    yourServers: "Your Servers",
    selectServer: "Select a server to manage its unique configuration and modules.",
    botConnected: "Bot Connected",
    botMissing: "Bot Missing",
    manageServer: "Manage Server",
    inviteBot: "Invite Bot",
    connected: "Connected",
    adminRights: "Admin Rights",
    noServers: "No Servers Found",
    noAdminRights: "No Admin Rights",
    
    // Guild Tabs
    overview: "Overview",
    antinuke: "Antinuke",
    automod: "Automod",
    autorole: "Autorole",
    leveling: "Leveling",
    welcome: "Welcome",
    logging: "Logging",
    tickets: "Tickets",
    verification: "Verification",
    tracking: "Tracking",
    invites: "Invites",
    autoReact: "Auto React",
    joinDm: "Join DM",
    customRoles: "Custom Roles",
    vanityRoles: "Vanity Roles",
    reactionRoles: "Reaction Roles",
    voiceRole: "Voice Role",
    
    // Common
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    enable: "Enable",
    disable: "Disable",
    enabled: "Enabled",
    disabled: "Disabled",
    loading: "Loading...",
    error: "Error",
    success: "Success",
    retry: "Retry",
    members: "Members",
    channels: "Channels",
    roles: "Roles",
    
    // Auth
    loginWithDiscord: "Login with Discord",
    initializingConsole: "Initialize Console",
    loginError: "Login Error",
    
    // Language
    language: "Language",
    german: "Deutsch",
    english: "English",
  },
};

export type TranslationKey = keyof typeof translations.de;

export function t(lang: Language, key: TranslationKey): string {
  return translations[lang][key] || translations.en[key] || key;
}
