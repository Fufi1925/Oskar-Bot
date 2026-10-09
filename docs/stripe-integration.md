# University Bot: Stripe Billing and Payments

## Integration plan and decisions

Business: https://universtiy-bot.up.railway.app — Discord community management and security.
The Stripe plugin install failed because `stripe@openai-curated` was unavailable in the marketplace.
The MCP server at https://mcp.stripe.com was registered, but authentication was blocked by the environment's network policy. `stripe_implementation_planner` was therefore unavailable.
The requested `npx skills add https://docs.stripe.com` fallback could not reach the documentation host. Official skills were installed from `stripe/ai` on GitHub instead. This plan applies their `stripe-best-practices` payments, billing, security and tax references; it is not a planner-tool response.

| Package | Price (EUR) | Stripe mode | Renewal |
| --- | ---: | --- | --- |
| Monthly | €2.99 | subscription | Calendar month, automatic |
| Yearly | €12.99 | subscription | Calendar year, automatic |
| Lifetime | €29.99 | payment | One payment |

Every package has the same three fixed Discord server slots and includes Ticket AI.
A month follows Stripe's calendar billing dates, rather than a fixed 30-day timer. Lifetime slots remain permanently assigned.

1. The signed-in Discord account opens a server-created hosted Checkout Session. Prices, currency, quantities, customer identity and return URLs come from trusted server settings.
2. Stripe collects payment details, handles authentication and renewals. Dynamic payment methods are used; no card details or publishable key are needed by this hosted-redirect integration.
3. A signed webhook reconciles current Stripe objects. Lifetime access requires a paid session with the exact configured price. Subscription access requires a paid invoice and uses its line item's absolute paid period end. Active subscription status alone never grants access.
4. SQLite commits event deduplication and payment entitlements together. Replayed or delayed invoices cannot extend access twice or shorten a later paid period. Refunds, disputes and early fraud warnings block the affected payment. Full refunds revoke its access; partial refunds retain access. Blocked payments require support review and are never silently restored.
5. The Customer Portal offers invoices, payment-method changes and cancellation at the end of the paid period. A cancelled subscription retains paid-through access. Failed payments do not extend access. Paid Stripe access ends at its paid-through date, retaining settings but disabling Premium runtime.
6. Confirmed payments send a Components V2 DM with custom emojis and the user's selected DE/EN language; English is the default. Blocked DMs never roll back a payment. Notification delivery is best effort after commit.
7. Approved privacy erasure expires open checkouts and cancels subscriptions before deleting local billing associations. If Stripe is unavailable, the request remains open for retry. Stripe's legally required financial records are handled separately.

## Server configuration (Railway)

Keep keys in the platform's secret storage or private runtime variables, never in source, public Next.js variables, Docker build arguments or committed environment files. Rotate the secret key shared in chat. Prefer a restricted API key with only customers, prices, Checkout Sessions, subscriptions, invoices, invoice payments, payment intents, charges and Customer Portal access. The setup command also needs Products, Prices, portal configurations and webhook endpoint write permissions; use separate provisioning credentials.

Required runtime variables:

- `STRIPE_MODE=test` (default; live keys are refused unless explicitly set to `live`).
- `STRIPE_SECRET_KEY`: private test credential from secure environment settings.
- `STRIPE_WEBHOOK_SECRET`: signing secret for the exact webhook endpoint and mode.
- `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_YEARLY`, `STRIPE_PRICE_LIFETIME`: IDs for the matching active EUR prices. Runtime validates amounts, intervals, mode and inclusive tax behavior.
- `STRIPE_PORTAL_CONFIGURATION`: customer portal configuration ID.
- `STRIPE_PUBLIC_URL=https://universtiy-bot.up.railway.app` (optional; otherwise uses trusted `NEXTAUTH_URL`/dashboard URL). HTTPS origin only, without a path.
- Existing `NEXTAUTH_URL`, Discord OAuth secrets and `DASHBOARD_API_KEY` remain required.

The repository includes a Stripe-key pre-commit guard. Enable it in a checkout with `git config core.hooksPath .githooks`. It rejects staged secret/restricted keys and only reports filenames, never key values.

Persist `/app/bot/db` on a Railway volume. Losing this database loses Discord/customer associations, deduplication history and server assignments. Restore from a protected backup before processing payments; do not run multiple replicas against isolated databases.

When secure credentials and Stripe API network access are available:

```sh
python tools/setup_stripe.py
```

The command is test-only and repeatable. It creates/reuses Premium and Premium Lifetime products, the three prices, the restricted portal configuration, and a webhook endpoint. It prints public object IDs, never credentials. Copy those IDs to Railway variables. Obtain the endpoint's signing secret from Stripe Dashboard and save it privately as `STRIPE_WEBHOOK_SECRET`. Restart/redeploy the service after changing runtime settings.

Webhook URL: `https://universtiy-bot.up.railway.app/api/stripe/webhook`
API and SDK: Stripe Python 16.x, `2026-09-30.endive`.
The endpoint is outside the dashboard API-key mount and requires a valid Stripe signature over the raw request body (300-second tolerance, 1 MiB cap). It must remain reachable by Stripe, without an interactive login or external dashboard authentication wall.

Subscriptions: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.created/updated/deleted/paused/resumed`, `charge.refunded`, `charge.dispute.created`, `radar.early_fraud_warning.created`. Only events used by this integration are enabled. Customer profiles are not mirrored, so `customer.updated` is unnecessary.

## Verification and deployment limits

Automated tests exercise paid and unpaid checkout, renewals, duplicate/reordered events, invalid signatures, foreign customers, refunds/disputes, price validation, return-page ownership, idempotent checkout, portal configuration and Premium expiry. They use a temporary database and simulated Stripe responses; they are not proof of actual account setup or bank settlement.

Before enabling real payments, perform an end-to-end Stripe test checkout for every plan, check webhook delivery in Workbench, verify renewal/cancellation with a test clock, and test a failed payment and refund. No real Stripe test objects or Railway variables could be configured in this session because network/secure credential access was unavailable. The website displays test mode and disables checkout until the required settings exist.

Live launch requires an explicit live configuration and live prices, portal configuration and webhook signing secret. Do not reuse test IDs. Existing test grants must be removed before a live launch.

Tax: prices are configured inclusive. Automatic Tax is not enabled because no tax registration or product tax classification was confirmed. Confirm applicable VAT obligations and active registrations before enabling Stripe Tax; see https://docs.stripe.com/billing/taxes/collect-taxes and https://docs.stripe.com/tax/set-up. Enabling `automatic_tax` without an active registration does not collect tax.

The old manually approved purchase requests remain available to administrators for outstanding requests, while new purchases use Checkout. An existing active grant or subscription blocks a second purchase; manage an ongoing subscription through the portal. Automatic upgrades to Lifetime and recurring-plan switches are deliberately not offered.
