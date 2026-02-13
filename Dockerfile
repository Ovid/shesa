# Shesha arXiv Web Explorer
# Build:  docker compose build
# Run:    docker compose up
# See:    http://localhost:8000

# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend

WORKDIR /build
COPY src/shesha/experimental/web/frontend/package.json \
     src/shesha/experimental/web/frontend/package-lock.json ./
RUN npm ci --silent
COPY src/shesha/experimental/web/frontend/ ./
RUN npm run build

# --- Stage 2: Runtime ---
FROM python:3.12-slim

# Install git (needed for hatch-vcs version detection)
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Copy built frontend into the source tree
COPY --from=frontend /build/dist src/shesha/experimental/web/frontend/dist

RUN pip install --no-cache-dir -e ".[web]"

EXPOSE 8000

ENTRYPOINT ["shesha-web", "--no-browser"]
