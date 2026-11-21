# Build context is the repo root. Backend lives in src/backend and is built standalone (GOWORK=off).
FROM golang:1.27-alpine AS build
WORKDIR /src/src/backend
COPY src/backend/go.mod src/backend/go.sum ./
RUN GOWORK=off go mod download
COPY src/backend ./
RUN GOWORK=off CGO_ENABLED=0 go build -o /out/backend .

FROM alpine:3.24
RUN adduser -D -u 10001 app
COPY --from=build /out/backend /usr/local/bin/backend
USER app
CMD ["backend"]
