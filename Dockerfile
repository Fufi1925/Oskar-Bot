# University Bot - Single Railway Deployment
# Bot + Dashboard together in one container

# Stage 1: Build Dashboard
FROM node:18-alpine AS dashboard-builder

WORKDIR /app/dashboard

# Accept build args for NEXT_PUBLIC_* variables
ARG NEXT_PUBLIC_BRAND_NAME="University Bot"
ARG NEXT_PUBLIC_BRAND_NAME_WORD="UB"
ARG NEXT_PUBLIC_ADMIN_IDS=""
ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_DASHBOARD_API_KEY=""

# Set them as env vars during build
ENV NEXT_PUBLIC_BRAND_NAME=${NEXT_PUBLIC_BRAND_NAME}
ENV NEXT_PUBLIC_BRAND_NAME_WORD=${NEXT_PUBLIC_BRAND_NAME_WORD}
ENV NEXT_PUBLIC_ADMIN_IDS=${NEXT_PUBLIC_ADMIN_IDS}
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_DASHBOARD_API_KEY=${NEXT_PUBLIC_DASHBOARD_API_KEY}

COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm install

COPY dashboard/ ./
RUN npm run build

# Stage 2: Production
FROM python:3.11-slim

WORKDIR /app

# Install Node.js and curl
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs curl && \
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

EXPOSE 8080

CMD ["./start.sh"]
