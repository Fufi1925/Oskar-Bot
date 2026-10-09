# Premium purchase requests and server slots

Premium is approved manually through the Admin dashboard. The dashboard offers
30 days for €2.99, 365 days for €12.99, and Lifetime for €29.99. These requests
do not create subscriptions or renew automatically. The Admin panel approves or
denies pending requests; approval grants account access and sends the existing
localized Components V2 Discord DM. A failed DM does not undo the approval.
Legacy pending 90-day requests remain supported.

Each Premium account has three server slots. The owner can remove an assignment
even after the server is deleted or the bot leaves it. Removal ends Premium from
that slot immediately and reserves that specific slot for 30 × 24 hours. Other
available slots can still be assigned. Existing settings are preserved. An
independent, active Admin server grant continues to provide access.

Cooldowns persist across restarts, membership expiration, and renewal. Assignment,
release, and request approval run in SQLite transactions. Repeated removal cannot
extend the deadline. Names and icons are saved when assigning or viewing a server;
if an old unavailable server has no saved name, the dashboard displays a generic
unavailable-server label rather than its Discord ID. IDs are transferred as strings.

Keep the persistent `bot/db` volume. `utils/premium_membership.py` upgrades existing
membership tables without resetting accounts. The privacy export includes accounts,
assignments, cooldowns, and requests; approved erasure removes those records.

Stripe integration is preserved on the pushed `archive/stripe-system` branch at
`f8dbbc0`. `main` has no Stripe routes, provisioning helpers, or Stripe dependency.
Existing environment bindings are unused; they are not deleted by this change.

Validation from the repository root:

```sh
python -m unittest discover -s bot/tests -p 'test_premium_slot_cooldown.py' -q
python -m unittest discover -s bot/tests -p 'test_premium_approval_dm.py' -q
```

From `bot/`, also run `python tests/test_premium_membership_v2.py`,
`python tests/test_privacy_erasure.py`, and `python ../.github/scripts/boot_test.py`.
From `dashboard/`, run `npx tsc --noEmit` and `npm run build`.
