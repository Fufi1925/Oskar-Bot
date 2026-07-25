#!/bin/bash

export PORT=${PORT:-8080}
export DASHBOARD_PORT=3000

# Set NEXTAUTH_URL automatically if not set
if [ -z "$NEXTAUTH_URL" ]; then
  if [ -n "$RAILWAY_PUBLIC_DOMAIN" ]; then
    export NEXTAUTH_URL="https://$RAILWAY_PUBLIC_DOMAIN"
  else
    export NEXTAUTH_URL="http://localhost:$PORT"
  fi
  echo "NEXTAUTH_URL set to: $NEXTAUTH_URL"
fi

# Generate NEXTAUTH_SECRET if not set
if [ -z "$NEXTAUTH_SECRET" ]; then
  export NEXTAUTH_SECRET=$(head -c 32 /dev/urandom | base64)
  echo "NEXTAUTH_SECRET generated automatically"
fi

echo "Starting University Bot..."
echo "Bot + API: port $PORT"
echo "Dashboard: port $DASHBOARD_PORT"

# Start Dashboard standalone server (NO npm needed - uses node directly)
cd /app/dashboard/standalone
ls -la server.js
HOSTNAME=0.0.0.0 PORT=$DASHBOARD_PORT node server.js > /tmp/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "Dashboard started on port $DASHBOARD_PORT (PID: $DASHBOARD_PID)"

# Wait for dashboard to be ready
echo "Waiting for Dashboard to be ready..."
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:$DASHBOARD_PORT > /dev/null 2>&1; then
    echo "Dashboard is ready!"
    break
  fi
  if [ "$i" = "30" ]; then
    echo "WARNING: Dashboard may not be ready. Logs:"
    cat /tmp/dashboard.log 2>/dev/null | tail -10
  fi
  sleep 1
done

# Ensure dashboard can talk to bot API
export API_BASE_URL="http://127.0.0.1:$PORT/api/v1"

# Forward DASHBOARD_API_KEY to NEXT_PUBLIC so dashboard can use it
if [ -n "$DASHBOARD_API_KEY" ] && [ -z "$NEXT_PUBLIC_DASHBOARD_API_KEY" ]; then
  export NEXT_PUBLIC_DASHBOARD_API_KEY="$DASHBOARD_API_KEY"
  echo "NEXT_PUBLIC_DASHBOARD_API_KEY set from DASHBOARD_API_KEY"
fi

# Set NEXT_PUBLIC_API_URL for client-side (browser) requests
if [ -n "$RAILWAY_PUBLIC_DOMAIN" ] && [ -z "$NEXT_PUBLIC_API_URL" ]; then
  export NEXT_PUBLIC_API_URL="https://$RAILWAY_PUBLIC_DOMAIN/api/v1"
  echo "NEXT_PUBLIC_API_URL set to: $NEXT_PUBLIC_API_URL"
fi

# Start Bot + API server
echo "Starting Bot + API server on port $PORT..."
cd /app/bot
python university_bot.py > /tmp/bot.log 2>&1 &
BOT_PID=$!
echo "Bot server started (PID: $BOT_PID)"

echo ""
echo "All services started!"
echo "  Bot + API:   port $PORT"
echo "  Dashboard:   port $DASHBOARD_PORT"

# Keep container running
wait
