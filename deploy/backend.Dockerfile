# Build context: repo root (go.work links agent/ and src/backend/).
# The agent is a Go package imported by the backend, so it ships in this image (no separate agent container).
FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.work ./
COPY agent ./agent
COPY src/backend ./src/backend
WORKDIR /src/src/backend
RUN go mod download
RUN CGO_ENABLED=0 go build -trimpath -o /out/backend .

FROM alpine:3.22
# The backend calls out over HTTPS (LLM, Discord gateway), so the Go binary needs the CA bundle.
RUN apk add --no-cache ca-certificates
RUN adduser -D -u 10001 app
COPY --from=build /out/backend /usr/local/bin/backend
USER app
EXPOSE 3001
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:3001/health >/dev/null || exit 1
CMD ["backend"]
