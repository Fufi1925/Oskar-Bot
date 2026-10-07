# Live statistics

The public `/honeypot/stats` page refreshes every 30 seconds through
`/api/honeypot-stats`. This server-side proxy publishes only aggregate counters
and daily chart points; the API key, guild IDs and server configuration stay
private. A failed request returns HTTP 503 instead of invented zero counts.
The page labels the last reading when refreshing fails.

Total moderations come from persisted Honeypot counters. Successful moderation
events also increment a UTC day/server counter in the same transaction. The
seven-day server count deduplicates servers across the entire period. Tracking
starts when the daily schema is installed; earlier days are gaps, and totals
recorded before that remain intact. Daily records are excluded from ordinary
configuration exports and included in full database backups.

The three exclusive counters in support guild `1530378233579704370` use the same
function for dashboard values and Discord voice-channel names. Servers come
from the connected guild list. Users are unique member IDs across those guilds,
including bots, with accounts shared between servers counted once. Unrelated
DM users in `bot.users` are excluded. Incomplete member lists are chunked before
counting; if they remain incomplete, the request fails rather than estimating.
Command totals use recorded prefix/slash successes and include buffered events
when storage temporarily prevents their flush.

Dashboard native dropdowns now use `WebsiteSelect`, retaining a hidden native
form control for existing change handlers, disabled options, optgroups and
multiple selection. Menus use the existing portal positioning and keyboard
navigation. Disabled module settings stay unmounted, with the banner centered
lower on the page. Enabling moves it upward over 450 ms while settings appear
from below. Reduced-motion preferences disable these animations.
