# Owner Louckup

The new admin tab and `/dashboard/admin/louckup` are separate from the existing
`/louckup` application and the existing user lookup tab.

## Configuration

- Set `OWNER_IDS` on both the dashboard and bot services. Only these IDs are
  accepted; `ADMIN_IDS`, application owners and dashboard team roles do not qualify.
- Set `OWNER_LOUCKUP_TOTP_SECRET` on the **bot service only**. Use a random
  20-byte Base32 secret. Never commit it or use a `NEXT_PUBLIC_` variable.
- Add that same secret to an authenticator app: SHA1, six digits, 30 seconds.
  The validator allows one adjacent time step for clock drift and rejects replays.
- The dashboard uses its existing server-only `DASHBOARD_API_KEY` to contact
  the bot. Without either required key, access fails closed.
- `NEXTAUTH_URL` must point to the public dashboard URL. The 2FA origin check
  uses this address behind the bot's reverse proxy, rather than the internal
  localhost hop. Forwarded headers cannot override the trusted origin.

Successful 2FA creates a ten-minute grant. Its hash is stored in the existing
database directory; the browser holds the grant in a Secure/HttpOnly/SameSite
cookie in production. It is bound to the owner ID and the specific NextAuth login.
Changing the TOTP secret invalidates all existing grants. Five failed attempts
block the owner for five minutes. Codes, secrets and lookup results are not logged.

## Data

The view combines public Discord profile information, cached shared bot servers,
bot ban state, dashboard sign-in counts and the latest authorized OAuth snapshot,
including connected accounts and the user's own guild membership details.
The shared-server list explicitly reports its cache limitations. OAuth guild lists
include servers without the bot, but describe the membership at the capture time.

Dashboard login and OAuth verification request `identify connections guilds
guilds.members.read` by default. Configured owners can manage this selection in
**Dashboard settings** (`/dashboard/admin/dashboard-settings`). `identify` and
`guilds` are required for sign-in and server access; `connections` and
`guilds.members.read` can be disabled. The selection is stored in
`db/dashboard_settings.db` and read at each new authorization. Request parameters
cannot override it. If the policy service is unavailable, new authorizations stop
instead of silently requesting default permissions. Collection is limited to
the selected, granted scopes even if Discord returns earlier, broader grants.
Optional `guilds.join` retains its existing Premium and owner-consent gates.
Discord must authorize these scopes; earlier authorizations cannot supply the
new data retroactively.

The same owner-only tab can revoke sessions for a single Discord ID or everyone,
including the acting owner, across all devices. A persistent global cutoff and
existing per-user cutoffs are checked by middleware and server session handling;
their caches expire after 15 seconds. New sign-ins after the cutoff work normally.
Saving the scope selection does not sign anyone out or revoke Discord grants;
owners can use the logout controls to require a new authorization.

The expanded consent version invalidates all earlier dashboard sessions once,
including middleware and server/API access. Fresh complete authorizations carry
the new version and survive subsequent deployments. Browser sessions check for
revocation every minute and on focus.

The bot collects additional data in the background with a two-minute deadline,
two concurrent membership requests per job, bounded retries and pagination.
Incomplete retrieval is labelled explicitly. No passwords, private messages,
email addresses or OAuth credentials are retained in this feature. A bearer
token is forwarded only over the internal, API-key-protected server endpoint and
lives temporarily in task memory; it is never included in stored snapshots,
lookup responses, logs or exports. Older jobs cannot overwrite a newer consent
or recreate an erased account. Jobs are cancelled during shutdown.

Snapshots expire after 30 days, access logs after 90 days. The API runs a cleanup
worker every minute and also deletes expired records on access. Account export
includes the snapshot; account erasure removes it and related grants/audit data.

## Checks

From `bot`: `python tests/test_owner_louckup.py` and
`python tests/test_dashboard_settings.py`.

From `dashboard`: `node --test tests/owner-louckup.test.cjs tests/dashboard-settings.test.cjs`,
`node node_modules/typescript/bin/tsc --noEmit` and `npm run build`.
