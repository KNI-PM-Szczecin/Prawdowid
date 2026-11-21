# Build context is the repo root. Public entry point: static front plus /api/* proxied to backend.
FROM node:24-alpine AS build
RUN corepack enable
WORKDIR /app
COPY src/frontend/package.json src/frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY src/frontend ./
RUN pnpm build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
