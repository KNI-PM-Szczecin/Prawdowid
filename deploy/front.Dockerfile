# Build context: repo root. Public entry point: static front plus /api/* proxied to the backend.
FROM node:24-alpine AS build
# FRONT_MODE=mock builds the demo with fictional results (no backend needed); anything else builds the live front.
ARG FRONT_MODE=production
RUN npm install --global pnpm@12
WORKDIR /app
COPY src/frontend/package.json src/frontend/pnpm-lock.yaml src/frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY src/frontend ./
RUN if [ "$FRONT_MODE" = "mock" ]; then pnpm build:mock; else pnpm build; fi

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 8080
