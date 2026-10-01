export const GUILD_MODULE_LABELS_DE: Record<string, string> = {
  backup: "Backup", "server-stats": "Server Stats", antinuke: "Anti-Nuke",
  automod: "Automod", honeypot: "Honeypot", verification: "Verifizierung",
  emergency: "Notfallmodus", jail: "Jail", nightmode: "Nachtmodus",
  welcome: "Willkommensnachricht", applications: "Bewerbungen",
  leave: "Abschiedsnachricht", joindm: "Beitritts-DM", autorole: "Auto-Rolle",
  reactionroles: "Reaktions-Rollen", customroles: "Eigene Rollen",
  vanityroles: "Vanity-Rollen", nickname: "Nickname-Regeln", leveling: "Leveling",
  giveaways: "Giveaways", counting: "Counting", booster: "Booster",
  notify: "Benachrichtigungen", autoreact: "Auto-Reaktion",
  autoresponder: "Autoresponder", "custom-commands": "Custom Commands",
  anonchat: "Anonymer Chat", music: "Musik", j2c: "Join to Create",
  invcrole: "Sprach-Rolle", tickets: "Tickets", compose: "Eigene Nachrichten",
  sticky: "Sticky-Nachrichten", invites: "Einladungen", tracking: "Einladungs-Log",
  noprefix: "No Prefix", speedrun: "Speedrun", "template-upload": "Template-Upload",
  templates: "Community-Templates", teamlist: "Teamliste", teamupdate: "Team-Update",
  logging: "Logging", supportqueue: "Support-Warteraum",
};

export const GUILD_MODULE_LABELS_EN: Record<string, string> = {
  backup: "Backup", "server-stats": "Server Stats", antinuke: "Anti-Nuke",
  automod: "AutoMod", honeypot: "Honeypot", verification: "Verification",
  emergency: "Emergency Mode", jail: "Jail", nightmode: "Night Mode",
  welcome: "Welcome Message", applications: "Applications", leave: "Goodbye Message",
  joindm: "Join DM", autorole: "Auto Role", reactionroles: "Reaction Roles",
  customroles: "Custom Roles", vanityroles: "Vanity Roles", nickname: "Nickname Rules",
  leveling: "Leveling", giveaways: "Giveaways", counting: "Counting", booster: "Booster",
  notify: "Notifications", autoreact: "Auto Reaction", autoresponder: "Autoresponder",
  "custom-commands": "Custom Commands", anonchat: "Anonymous Chat", music: "Music",
  j2c: "Join to Create", invcrole: "Voice Role", tickets: "Tickets",
  compose: "Custom Messages", sticky: "Sticky Messages", invites: "Invites",
  tracking: "Invite Log", noprefix: "No Prefix", speedrun: "Speedrun",
  "template-upload": "Template Upload", templates: "Community Templates",
  teamlist: "Team List", teamupdate: "Team Update", logging: "Logging",
  supportqueue: "Support Waiting Room",
};

export const TOGGLEABLE_GUILD_MODULES = new Set(Object.keys(GUILD_MODULE_LABELS_DE));

/** One status per real system. Nested pages share their parent system. */
export function guildModuleFromPath(pathname: string, guildId: string): string | null {
  const tail = pathname.split(`/dashboard/guild/${guildId}`)[1] || "";
  const parts = tail.split("/").filter(Boolean);
  if (!parts.length) return null;
  const key = parts[0];
  return TOGGLEABLE_GUILD_MODULES.has(key) ? key : null;
}

export function guildModuleFromHref(href: string, guildId: string): string | null {
  return guildModuleFromPath(href, guildId);
}
