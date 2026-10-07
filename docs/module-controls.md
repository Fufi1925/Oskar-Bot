# Server module controls

All server dashboard tabs were reviewed for a meaningful runtime switch.
The shared availability switches default to enabled, and joining a guild
persists these defaults without replacing any previously saved choice.
An enabled module still needs its own channels, roles, messages or rules.

| Tabs | Control |
| --- | --- |
| Backup, Server Stats, Anti-Nuke, Automod, Honeypot, Verification, Emergency, Jail, Night Mode | Pause/resume the corresponding bot system. |
| Welcome, Applications, Goodbye, Join DM, Auto Role, Reaction Roles, Custom Roles, Vanity Roles, Nickname | Pause/resume the corresponding messages, panels or role automation. |
| Leveling, Giveaways, Counting, Booster, Notify, Auto React, Autoresponder, Custom Commands, Anonymous Chat, Music | Pause/resume the corresponding system. |
| Join to Create, Voice Role, Tickets, Sticky, Invites, Tracking, No Prefix, Team List, Team Update, Logging, Support Queue | Pause/resume the corresponding system. No Prefix now also gates prefix recognition. |
| Verification / Pull, Leveling / Leaderboard | Share their parent module. Pull keeps its separate owner-confirmed, Premium-only opt-in. |
| Message editor, Speedrun, Template Upload, Community Templates | Tools, with no continuously running main-bot module to pause. Remove the shared switch and status dot; keep all tool functionality. |
| Overview, Settings, Help, Design, Bot Logs, Premium, Dashboard Access, Admin Dashboard, Owner Console, AI | Navigation, administration or tools: no shared module switch. |

Verification uses a single dashboard switch which updates both the module
gate and the actual verification configuration. Missing channel/role setup
is rejected when explicitly enabling it. Existing paused configurations stay
paused. New, unconfigured verification settings are available by default;
they cannot grant roles until configured. A failed status request is shown
as unavailable rather than falsely claiming the system is disabled.

Expired/unregistered Discord buttons, selects and modal submissions receive
an English, ephemeral Components V2 card with the bot's custom warning emoji.
Registered views, dynamic components and restart-safe ticket, application,
giveaway and self-role listeners retain their normal callbacks. Disabled
modules stop callbacks before side effects and send a private dashboard hint.
Prefix commands cannot send ephemeral messages, so their hint goes to the
invoking user's DM. Discord links do not generate component interactions.
