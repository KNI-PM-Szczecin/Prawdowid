# Build context is the repo root because go.work links backend/ and agent/.
FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.work ./
COPY agent ./agent
COPY backend ./backend
WORKDIR /src/backend
RUN go mod download
RUN CGO_ENABLED=0 go build -o /out/backend .

FROM alpine:3.24
RUN adduser -D -u 10001 app
COPY --from=build /out/backend /usr/local/bin/backend
USER app
CMD ["backend"]
