# dashboard/ — Web-Dashboard

**CloudTIX** · Next.js 14 (App Router), TypeScript, Tailwind.
Öffentliche Seiten, Server-Dashboard, Admin-Bereich — und der Proxy
unter `app/api/bot/[...path]/`, der die Rechte prüft.

---

## ✦ Overview

This folder contains the CloudTIX web dashboard built with `Next.js 14` (App Router), `TypeScript`, and `Tailwind CSS`. It connects to the bot's FastAPI backend via a permanent Cloudflare Tunnel HTTPS URL and lets server admins manage all bot settings through a sleek, branded UI.

```
dashboard/
├── app/                       App Router pages & API routes
│   ├── api/auth/              NextAuth OAuth callback
│   ├── dashboard/             Main dashboard area
│   │   ├── admin/             Admin-only panel
│   │   ├── guilds/            Server selection
│   │   └── guild/[guildId]/   Per-server settings pages
│   │       ├── antinuke/
│   │       ├── automod/
│   │       ├── leveling/
│   │       ├── logging/
│   │       ├── tickets/
│   │       ├── welcome/
│   │       └── …more
│   ├── docs/                  Documentation page
│   ├── privacy/               Privacy policy
│   └── terms/                 Terms of service
├── components/
│   ├── dashboard/             Feature-specific form components
│   └── ui/                    Base UI components (button, card, input…)
├── hooks/                     Custom React hooks
├── lib/                       API client, auth config, utilities
└── types/                     TypeScript type definitions
```

---

## ✦ Features

- **Discord OAuth2 login** — secure sign-in, session managed by NextAuth
- **Per-server management** — antinuke, automod, leveling, logging, tickets, welcome, and more
- **Live bot stats** — real-time metrics pulled from the FastAPI backend
- **Admin panel** — owner-only configuration and announcements
- **Fully branded** — name, logo, and colours via environment variables
- **HTTPS ready** — connects to the bot's permanent Cloudflare Tunnel URL
- **Vercel-ready** — deploys in minutes with zero config changes

---

## ✦ Prerequisites

| Requirement | Notes |
|---|---|
| Node.js 18+ | — |
| CloudTIX bot running | with `API_ENABLED=true` and `TUNNEL_ENABLED=true` |
| Discord OAuth app | from [Discord Developer Portal](https://discord.com/developers/applications) |

---

## ✦ Setup

### 1 — Install dependencies

```bash
npm install
```

### 2 — Configure environment

Create a `.env.local` file in this folder:

```env
# ── Bot API ───────────────────────────────────────────────────────
# Server-side connection to the local bot API
API_BASE_URL                  = http://127.0.0.1:8080/api/v1
DASHBOARD_API_KEY             = your_shared_api_key   # must match the bot

# ── NextAuth ──────────────────────────────────────────────────────
NEXTAUTH_URL                  = http://localhost:3000
NEXTAUTH_SECRET               = a_long_random_string   # generate: openssl rand -base64 32

# ── Discord OAuth ─────────────────────────────────────────────────
DISCORD_CLIENT_ID             = your_discord_oauth_client_id
DISCORD_CLIENT_SECRET         = your_discord_oauth_client_secret

# ── Branding ──────────────────────────────────────────────────────
NEXT_PUBLIC_ADMIN_IDS         = your_discord_user_id
NEXT_PUBLIC_BRAND_NAME        = "CloudTIX"
NEXT_PUBLIC_BRAND_NAME_WORD   = "CloudTIX"
```

### 3 — Run locally

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## ✦ Environment Reference

| Variable | Description |
|---|---|
| `API_BASE_URL` | Server-side URL to the bot API; set automatically by start.sh on Railway |
| `DASHBOARD_API_KEY` | Shared server-side API key, matching the bot configuration |
| `NEXTAUTH_URL` | `https://cloudtix.up.railway.app` in production |
| `NEXTAUTH_SECRET` | Random secret for NextAuth session signing |
| `DISCORD_CLIENT_ID` | Discord OAuth2 client ID |
| `DISCORD_CLIENT_SECRET` | Discord OAuth2 client secret |
| `NEXT_PUBLIC_ADMIN_IDS` | Comma-separated Discord user IDs with admin panel access |
| `NEXT_PUBLIC_BRAND_NAME` | Bot name shown in the dashboard UI |
| `NEXT_PUBLIC_BRAND_NAME_WORD` | Wordmark, default `CloudTIX` |

---

## ✦ Deployment (Railway)

CloudTIX runs at **https://cloudtix.up.railway.app**. The root `Dockerfile`
builds Next.js and starts the dashboard together with the main bot through
`start.sh`. Use [the Railway deployment guide](../RAILWAY_DEPLOYMENT.md)
for the complete configuration and the isolated applications.

Set `NEXTAUTH_URL=https://cloudtix.up.railway.app`, a stable
`NEXTAUTH_SECRET`, the main application's Discord OAuth credentials and
`DASHBOARD_API_KEY` in the main Railway service.

Add both redirects to the main application's **OAuth2 → Redirects** in
the Discord Developer Portal:

```text
https://cloudtix.up.railway.app/api/auth/callback/discord
https://cloudtix.up.railway.app/api/verify/callback
```

The public URL helper normalizes the origin and migrates the former
website host. `start.sh` applies the same address to Phantom, Louckup and
LBoost Shop unless a separate base URL is explicitly configured.

---

## ✦ Connecting to the Bot API

Browser requests use the relative `/api/bot` proxy. The proxy checks the
logged-in user's permissions and attaches `DASHBOARD_API_KEY` on the
server. Keep this key in server-side environment variables.

| Environment | Server-side API_BASE_URL |
|---|---|
| Local dev | `http://127.0.0.1:8080/api/v1` |
| Railway | `http://127.0.0.1:$PORT/api/v1` (exported by start.sh) |

The bot's public proxy serves the dashboard on the same domain. Internal
Next.js traffic goes to `http://127.0.0.1:$DASHBOARD_PORT`; public OAuth
redirects and links use `https://cloudtix.up.railway.app`.

---

## ✦ Troubleshooting

| Problem | Fix |
|---|---|
| Auth error on login | Check Discord OAuth client ID/secret and redirect URI in Developer Portal |
| Dashboard can't load data | Confirm bot is running with `API_ENABLED=true` and `API_BASE_URL` is correct |
| CORS error in browser | Use `https://cloudtix.up.railway.app` in `CORS_ORIGINS` |
| `NEXTAUTH_SECRET` error | Make sure `NEXTAUTH_SECRET` is set and non-empty |
| API key rejected (401) | The server-side `DASHBOARD_API_KEY` must match the bot |
| Login redirects to an old address | Redeploy and check `NEXTAUTH_URL` and the Discord Redirects list |

---

<div align="center">

## ✦ CloudTIX Devs

*Built for protection. Designed for style.*

<a href="https://discord.gg/F3TedBAVZT"><img src="https://discord.com/api/guilds/1301573144817045524/widget.png?style=banner2" alt="CloudTIX Development Discord Server" width="480"/></a>

<p>
  <a href="https://discord.gg/F3TedBAVZT"><img src="https://img.shields.io/badge/Discord-Join_Server-5865F2?style=for-the-badge&logo=discord&logoColor=white"/></a>
  <a href="https://youtube.com/@UniversityBotDevs"><img src="https://img.shields.io/badge/YouTube-University%20Bot%20Devs-FF0000?style=for-the-badge&logo=youtube&logoColor=white"/></a>
  <a href="https://github.com/Fufi1925/Oskar-Bot"><img src="https://img.shields.io/badge/GitHub-University%20Bot-181717?style=for-the-badge&logo=github&logoColor=white"/></a>
</p>

© 2026 CloudTIX Devs — alle Rechte vorbehalten, siehe [LICENSE](../LICENSE)

</div>
