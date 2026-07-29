# University Bot - Single Railway Deployment
# Bot + Dashboard together in one container

# Stage 1: Build Dashboard
FROM node:18-alpine AS dashboard-builder

WORKDIR /app/dashboard

# Accept build args for NEXT_PUBLIC_* variables
# NOTE: never add the API key here. NEXT_PUBLIC_* values are baked into the
# JavaScript bundle and would be readable by every visitor. Browser requests
# are proxied through /api/bot, which attaches the key server-side.
ARG NEXT_PUBLIC_BRAND_NAME="University Bot"
ARG NEXT_PUBLIC_BRAND_NAME_WORD="UB"
ARG NEXT_PUBLIC_ADMIN_IDS=""

# Set them as env vars during build
ENV NEXT_PUBLIC_BRAND_NAME=${NEXT_PUBLIC_BRAND_NAME}
ENV NEXT_PUBLIC_BRAND_NAME_WORD=${NEXT_PUBLIC_BRAND_NAME_WORD}
ENV NEXT_PUBLIC_ADMIN_IDS=${NEXT_PUBLIC_ADMIN_IDS}

COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm install

COPY dashboard/ ./
RUN npm run build

# Stage 2: Production
FROM python:3.11-slim

WORKDIR /app

# Install curl plus the SAME Node major version used to build the dashboard.
# Debian's default "nodejs" package lags behind and is not pinned, which made
# the build and runtime environments drift apart.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get purge -y gnupg && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot/ ./bot/

# Copy dashboard standalone build
COPY --from=dashboard-builder /app/dashboard/.next/standalone ./dashboard/standalone
COPY --from=dashboard-builder /app/dashboard/.next/static ./dashboard/standalone/.next/static
COPY --from=dashboard-builder /app/dashboard/public ./dashboard/standalone/public

# Copy start script
COPY start.sh ./start.sh
RUN chmod +x start.sh

# Environment
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DASHBOARD_PORT=3000
ENV HOSTNAME=0.0.0.0

# Where the databases live.
#
# Everything the bot writes -- 61 SQLite files, the JSON config and the
# two strays (rr.db, j2c_data.db) that sit outside db/ -- is put under
# this one directory at startup, so a single mounted volume covers all
# of it. Without a volume mounted here the directory is just part of the
# container and the data is gone on the next deploy, which is the
# behaviour this replaces.
#
# On Railway: add a volume in the dashboard with the mount path /data.
#
# No VOLUME instruction here on purpose -- Railway rejects the whole
# build with "docker VOLUME at Line N is not supported, use Railway
# Volumes". It manages mounts itself, so the declaration is both
# unnecessary and fatal.
ENV DATA_DIR=/data

EXPOSE 8080

CMD ["./start.sh"]
