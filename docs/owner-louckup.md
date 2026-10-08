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
bot ban state, dashboard sign-in counts and the latest authorized OAuth snapshot.
The shared-server list explicitly reports its cache limitations. OAuth guild lists
include servers without the bot, but describe the membership at the capture time.

Existing authorizations are not retroactively recovered. A snapshot appears at
the next dashboard login or server verification using the existing `identify`
and `guilds` scopes. No additional scope is requested. No passwords, private
messages, email addresses or OAuth credentials are retained in this feature.

Snapshots expire after 30 days, access logs after 90 days. The API runs a cleanup
worker every minute and also deletes expired records on access. Account export
includes the snapshot; account erasure removes it and related grants/audit data.

## Checks

From `bot`: `python tests/test_owner_louckup.py`.

From `dashboard`: `node --test tests/owner-louckup.test.cjs`,
`node node_modules/typescript/bin/tsc --noEmit` and `npm run build`.
