#!/bin/bash
set -u

export PORT=${PORT:-8080}
export DASHBOARD_PORT=${DASHBOARD_PORT:-3000}
export PHANTOM_PORT=${PHANTOM_PORT:-8787}

# Phantom public URL (isolated under /phantom on same domain)
if [ -z "${PHANTOM_BASE_URL:-}" ]; then
  if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
    export PHANTOM_BASE_URL="https://$RAILWAY_PUBLIC_DOMAIN/phantom"
  else
    export PHANTOM_BASE_URL="http://localhost:$PORT/phantom"
  fi
  echo "👻 PHANTOM_BASE_URL set to: $PHANTOM_BASE_URL"
fi
export PHANTOM_COOKIE_PATH="${PHANTOM_COOKIE_PATH:-/phantom}"
if [ -n "${DATA_DIR:-}" ]; then
  mkdir -p "$DATA_DIR/phantom"
  export PHANTOM_DB_PATH="${PHANTOM_DB_PATH:-$DATA_DIR/phantom/phantom.db}"
fi

# ── Louckup (isolated under /louckup, same domain) ────────────────
# Eigener Bereich mit eigener Discord-Application. Nichts davon haengt
# an Phantom — nur die Domain teilen sie sich.
if [ -z "${LOUCKUP_BASE_URL:-}" ]; then
  if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
    export LOUCKUP_BASE_URL="https://$RAILWAY_PUBLIC_DOMAIN/louckup"
  else
    export LOUCKUP_BASE_URL="http://localhost:$PORT/louckup"
  fi
  echo "🔒 LOUCKUP_BASE_URL set to: $LOUCKUP_BASE_URL"
fi
export LOUCKUP_COOKIE_PATH="${LOUCKUP_COOKIE_PATH:-/louckup}"
if [ -n "${DATA_DIR:-}" ]; then
  mkdir -p "$DATA_DIR/louckup"
  export LOUCKUP_DB_PATH="${LOUCKUP_DB_PATH:-$DATA_DIR/louckup/louckup.db}"
fi
# Wer hier rein darf: LOUCKUP_OWNER_IDS hat Vorrang, sonst gilt die
# Owner-Liste des Bots. Beides leer heisst: niemand kommt auf
# /louckup/dashboard — die Loginseite weist darauf hin.
if [ -z "${LOUCKUP_OWNER_IDS:-}" ] && [ -n "${OWNER_IDS:-}" ]; then
  export LOUCKUP_OWNER_IDS="$OWNER_IDS"
fi
# Wie NEXTAUTH_SECRET: ohne festen Wert sind nach jedem Neustart alle
# Louckup-Sessions ungueltig.
if [ -z "${LOUCKUP_SECRET_KEY:-}" ] && [ -n "${DASHBOARD_API_KEY:-}" ]; then
  export LOUCKUP_SECRET_KEY="$DASHBOARD_API_KEY"
fi

# ── LBoost Shop (isolated under /lbost-shop) ──────────────────────
# Eigene Discord-Application, eigener Session-Schluessel, eigene
# Freigabeliste und bereits reservierter Token fuer den spaeteren Shop-Bot.
if [ -z "${LBOST_SHOP_BASE_URL:-}" ]; then
  if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
    export LBOST_SHOP_BASE_URL="https://$RAILWAY_PUBLIC_DOMAIN/lbost-shop"
  else
    export LBOST_SHOP_BASE_URL="http://localhost:$PORT/lbost-shop"
  fi
  echo "🛍️ LBOST_SHOP_BASE_URL set to: $LBOST_SHOP_BASE_URL"
fi
export LBOST_SHOP_COOKIE_PATH="${LBOST_SHOP_COOKIE_PATH:-/lbost-shop}"
if [ -n "${DATA_DIR:-}" ]; then
  mkdir -p "$DATA_DIR/lbost-shop"
  export LBOST_SHOP_DB_PATH="${LBOST_SHOP_DB_PATH:-$DATA_DIR/lbost-shop/lbost_shop.sqlite3}"
fi
# Globale Owner duerfen immer hinein; die zusaetzlichen Nutzer stehen
# ausschliesslich in LBOST_SHOP_AUTHORIZED_IDS.
if [ -z "${LBOST_SHOP_OWNER_IDS:-}" ] && [ -n "${OWNER_IDS:-}" ]; then
  export LBOST_SHOP_OWNER_IDS="$OWNER_IDS"
fi

# Set NEXTAUTH_URL automatically if not set
if [ -z "${NEXTAUTH_URL:-}" ]; then
  if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
    export NEXTAUTH_URL="https://$RAILWAY_PUBLIC_DOMAIN"
  else
    export NEXTAUTH_URL="http://localhost:$PORT"
  fi
  echo "🌐 NEXTAUTH_URL set to: $NEXTAUTH_URL"
fi

# OAuth is extremely strict about redirect_uri. A trailing callback path,
# whitespace, localhost on Railway or a trailing slash can make Discord accept
# the consent and then reject the token exchange. Normalize to one public
# origin before Next.js starts, while keeping intentional custom domains.
NORMALIZED_NEXTAUTH_URL="$(python - "$NEXTAUTH_URL" "${RAILWAY_PUBLIC_DOMAIN:-}" <<'PY'
import sys
from urllib.parse import urlsplit
raw = (sys.argv[1] or "").strip().strip('"').strip("'")
railway = (sys.argv[2] or "").strip()
if raw and "://" not in raw:
    raw = "https://" + raw
parts = urlsplit(raw)
host = (parts.hostname or "").lower()
if railway and host in {"localhost", "127.0.0.1", "0.0.0.0", ""}:
    print("https://" + railway)
elif parts.scheme in {"http", "https"} and parts.netloc:
    print(f"{parts.scheme}://{parts.netloc}")
else:
    print("")
PY
)"
if [ -n "$NORMALIZED_NEXTAUTH_URL" ]; then
  if [ "$NORMALIZED_NEXTAUTH_URL" != "$NEXTAUTH_URL" ]; then
    echo "🛠️ NEXTAUTH_URL normalized: $NEXTAUTH_URL -> $NORMALIZED_NEXTAUTH_URL"
  fi
  export NEXTAUTH_URL="$NORMALIZED_NEXTAUTH_URL"
else
  echo "❌ NEXTAUTH_URL is invalid; Discord OAuth cannot start"
fi
export NEXTAUTH_URL_INTERNAL="${NEXTAUTH_URL_INTERNAL:-http://127.0.0.1:$DASHBOARD_PORT}"
echo "🔁 University OAuth callback: $NEXTAUTH_URL/api/auth/callback/discord"

# The main dashboard may use new dedicated names or the legacy variables.
# Dedicated values also repair every older main-dashboard OAuth route that
# still reads DISCORD_CLIENT_*. Never silently borrow LBOST_SHOP_*.
if [ -n "${UNIVERSITY_DISCORD_CLIENT_ID:-}" ]; then
  export DISCORD_CLIENT_ID="$UNIVERSITY_DISCORD_CLIENT_ID"
elif [ -n "${MAIN_BOT_CLIENT_ID:-}" ]; then
  export DISCORD_CLIENT_ID="$MAIN_BOT_CLIENT_ID"
fi
if [ -n "${UNIVERSITY_DISCORD_CLIENT_SECRET:-}" ]; then
  export DISCORD_CLIENT_SECRET="$UNIVERSITY_DISCORD_CLIENT_SECRET"
elif [ -n "${MAIN_BOT_CLIENT_SECRET:-}" ]; then
  export DISCORD_CLIENT_SECRET="$MAIN_BOT_CLIENT_SECRET"
fi
if [ -z "${UNIVERSITY_DISCORD_CLIENT_ID:-${MAIN_BOT_CLIENT_ID:-${DISCORD_CLIENT_ID:-}}}" ]; then
  echo "❌ University Discord OAuth client ID is missing"
fi
if [ -z "${UNIVERSITY_DISCORD_CLIENT_SECRET:-${MAIN_BOT_CLIENT_SECRET:-${DISCORD_CLIENT_SECRET:-}}}" ]; then
  echo "❌ University Discord OAuth client secret is missing"
fi
if [ -n "${LBOST_SHOP_DISCORD_CLIENT_ID:-}" ] && [ "${UNIVERSITY_DISCORD_CLIENT_ID:-${MAIN_BOT_CLIENT_ID:-${DISCORD_CLIENT_ID:-}}}" = "$LBOST_SHOP_DISCORD_CLIENT_ID" ]; then
  echo "⚠️ University and LBoost use the same Discord Client ID. Set UNIVERSITY_DISCORD_CLIENT_ID to the main app."
fi

# IMPORTANT: NEXTAUTH_SECRET must be stable across restarts, otherwise every
# restart invalidates all login cookies and users must authorize Discord again.
if [ -z "${NEXTAUTH_SECRET:-}" ]; then
  if [ -n "${DASHBOARD_API_KEY:-}" ]; then
    export NEXTAUTH_SECRET="$DASHBOARD_API_KEY"
    echo "🔑 NEXTAUTH_SECRET set from DASHBOARD_API_KEY for stable sessions"
  else
    export NEXTAUTH_SECRET=$(head -c 32 /dev/urandom | base64)
    echo "⚠️ NEXTAUTH_SECRET generated automatically. Set it in Railway to keep sessions after restarts."
  fi
fi

# Runtime API environment for the Dashboard server must be exported BEFORE
# starting Next.js. The Dashboard itself runs on port 3000, but its server-side
# API calls must go to the FastAPI/Bot proxy on port 8080.
export API_BASE_URL="http://127.0.0.1:$PORT/api/v1"

# SECURITY: the API key must never be exposed to the browser. Anything named
# NEXT_PUBLIC_* is inlined into the client bundle by Next.js, so the key is
# deliberately NOT mirrored there. Browser requests go through the authorizing
# proxy at /api/bot instead, which attaches the key server-side.
if [ -n "${NEXT_PUBLIC_DASHBOARD_API_KEY:-}" ]; then
  unset NEXT_PUBLIC_DASHBOARD_API_KEY
  echo "🛡️ NEXT_PUBLIC_DASHBOARD_API_KEY was set and has been removed (it would leak the key to browsers)"
fi

# Admin IDs are needed server-side for authorization checks.
#
# The bot reads OWNER_IDS *and* ADMIN_IDS (utils/dashboard_roles.py), the
# dashboard proxy only ever read ADMIN_IDS. On a deployment that sets just
# OWNER_IDS — which is what the Railway setup does — the two disagreed:
# the bot considered the deployer an owner, the proxy did not, and every
# admin request was rejected before it ever reached the bot. Filling the
# gap here keeps both halves on the same list.
if [ -z "${ADMIN_IDS:-}" ] && [ -n "${NEXT_PUBLIC_ADMIN_IDS:-}" ]; then
  export ADMIN_IDS="$NEXT_PUBLIC_ADMIN_IDS"
fi
if [ -z "${ADMIN_IDS:-}" ] && [ -n "${OWNER_IDS:-}" ]; then
  export ADMIN_IDS="$OWNER_IDS"
  echo "🔑 ADMIN_IDS taken from OWNER_IDS so the dashboard agrees with the bot"
fi

echo "=========================================="
echo "🤖 Starting University Bot..."
echo "=========================================="
echo "📡 Bot + API: port $PORT"
echo "🖥️ Dashboard: port $DASHBOARD_PORT"
echo "=========================================="

DASHBOARD_PID=""
LBOST_SHOP_BOT_PID=""
cleanup() {
  if [ -n "${LBOST_SHOP_BOT_PID:-}" ] && kill -0 "$LBOST_SHOP_BOT_PID" 2>/dev/null; then
    echo "🧹 Stopping LBoost Shop Bot (PID: $LBOST_SHOP_BOT_PID)"
    kill "$LBOST_SHOP_BOT_PID" 2>/dev/null || true
    wait "$LBOST_SHOP_BOT_PID" 2>/dev/null || true
  fi
  if [ -n "${PHANTOM_BOT_PID:-}" ] && kill -0 "$PHANTOM_BOT_PID" 2>/dev/null; then
    echo "🧹 Stopping Phantom Bot (PID: $PHANTOM_BOT_PID)"
    kill "$PHANTOM_BOT_PID" 2>/dev/null || true
    wait "$PHANTOM_BOT_PID" 2>/dev/null || true
  fi
  if [ -n "$DASHBOARD_PID" ] && kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    echo "🧹 Stopping Dashboard (PID: $DASHBOARD_PID)"
    kill "$DASHBOARD_PID" 2>/dev/null || true
    wait "$DASHBOARD_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Start Dashboard standalone server
cd /app/dashboard/standalone
ls -la server.js 2>/dev/null || echo "⚠️ server.js not found!"
HOSTNAME=0.0.0.0 PORT=$DASHBOARD_PORT node server.js > /tmp/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "✅ Dashboard started on port $DASHBOARD_PORT (PID: $DASHBOARD_PID)"

# Wait for dashboard to be ready
echo "⏳ Waiting for Dashboard to be ready..."
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:$DASHBOARD_PORT > /dev/null 2>&1; then
    echo "✅ Dashboard is ready!"
    break
  fi
  if ! kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    echo "❌ Dashboard process exited early. Logs:"
    cat /tmp/dashboard.log 2>/dev/null | tail -30
    exit 1
  fi
  if [ "$i" = "30" ]; then
    echo "❌ Dashboard failed to start. Logs:"
    cat /tmp/dashboard.log 2>/dev/null | tail -30
    exit 1
  fi
  sleep 1
done

# Start Bot (logs go to stdout for visibility)
echo ""
echo "🚀 Starting Bot + API server on port $PORT..."
echo "=========================================="
# Start Phantom ticket bot (optional — only if token is set)
PHANTOM_BOT_PID=""
if [ -n "${PHANTOM_BOT_TOKEN:-}" ] && [ -f /app/phantom/run_bot.py ]; then
  echo "👻 Starting Phantom Ticket-Bot..."
  cd /app/phantom
  PYTHONPATH=/app/phantom python run_bot.py > /tmp/phantom-bot.log 2>&1 &
  PHANTOM_BOT_PID=$!
  echo "✅ Phantom Ticket-Bot started (PID: $PHANTOM_BOT_PID)"
else
  echo "ℹ️ Phantom Ticket-Bot skipped (PHANTOM_BOT_TOKEN not set)"
fi

# Start the isolated LBoost Shop gateway client. It intentionally has no
# commands or handlers yet, but stays connected for future shop features.
if [ -n "${LBOST_SHOP_BOT_TOKEN:-}" ] && [ -f /app/lbost-shop/run_bot.py ]; then
  echo "🛍️ Starting LBoost Shop Bot (no features enabled yet)..."
  cd /app/lbost-shop
  PYTHONPATH=/app/lbost-shop python run_bot.py > /tmp/lbost-shop-bot.log 2>&1 &
  LBOST_SHOP_BOT_PID=$!
  echo "✅ LBoost Shop Bot started (PID: $LBOST_SHOP_BOT_PID)"
else
  echo "ℹ️ LBoost Shop Bot skipped (LBOST_SHOP_BOT_TOKEN not set)"
fi

cd /app/bot
python university_bot.py 2>&1
BOT_EXIT=$?

echo ""
echo "❌ Bot exited with code $BOT_EXIT"
cleanup
trap - EXIT INT TERM

# Exit code 75 means Discord is rate limiting our login attempts. Restarting
# quickly makes that worse — every attempt extends the block — so back off
# for a long time instead. Anything else is likely a crash worth retrying.
if [ "$BOT_EXIT" = "75" ]; then
  RATE_LIMIT_BACKOFF=${RATE_LIMIT_BACKOFF:-900}
  echo "🛑 Discord login rate limit hit."
  echo "   Waiting ${RATE_LIMIT_BACKOFF}s before trying again so the block can expire."
  echo "   Restarting the service now would only extend it."
  sleep "$RATE_LIMIT_BACKOFF"
else
  echo "Restarting in 15 seconds..."
  sleep 15
fi

exec "$0"
