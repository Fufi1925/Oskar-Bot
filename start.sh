#!/bin/bash
set -u

export PORT=${PORT:-8080}
export DASHBOARD_PORT=${DASHBOARD_PORT:-3000}

# Set NEXTAUTH_URL automatically if not set
if [ -z "${NEXTAUTH_URL:-}" ]; then
  if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
    export NEXTAUTH_URL="https://$RAILWAY_PUBLIC_DOMAIN"
  else
    export NEXTAUTH_URL="http://localhost:$PORT"
  fi
  echo "🌐 NEXTAUTH_URL set to: $NEXTAUTH_URL"
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

if [ -n "${DASHBOARD_API_KEY:-}" ] && [ -z "${NEXT_PUBLIC_DASHBOARD_API_KEY:-}" ]; then
  export NEXT_PUBLIC_DASHBOARD_API_KEY="$DASHBOARD_API_KEY"
  echo "🔑 NEXT_PUBLIC_DASHBOARD_API_KEY set from DASHBOARD_API_KEY"
fi

if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ] && [ -z "${NEXT_PUBLIC_API_URL:-}" ]; then
  export NEXT_PUBLIC_API_URL="/api/v1"
  echo "🌐 NEXT_PUBLIC_API_URL set to: $NEXT_PUBLIC_API_URL"
fi

echo "=========================================="
echo "🤖 Starting University Bot..."
echo "=========================================="
echo "📡 Bot + API: port $PORT"
echo "🖥️ Dashboard: port $DASHBOARD_PORT"
echo "=========================================="

DASHBOARD_PID=""
cleanup() {
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
cd /app/bot
python university_bot.py 2>&1
BOT_EXIT=$?

echo ""
echo "❌ Bot exited with code $BOT_EXIT"
cleanup
trap - EXIT INT TERM

echo "Restarting in 5 seconds..."
sleep 5
exec "$0"
