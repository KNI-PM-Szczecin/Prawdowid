package main

import (
	"log/slog"
	"net"
	"net/http"
	"net/netip"
	"strings"
	"sync"
	"time"
)

// maxTrackedClients caps the limiter map so spoofed or numerous addresses cannot exhaust memory.
const maxTrackedClients = 10000

// rateLimiter allows at most limit requests per window for each client address (fixed window, in memory).
type rateLimiter struct {
	mu        sync.Mutex
	limit     int
	window    time.Duration
	clients   map[string]*clientWindow
	now       func() time.Time
	logger    *slog.Logger
	lastSweep time.Time
	// fullLogged keeps the "table full" warning to one line per sweep.
	fullLogged bool
}

type clientWindow struct {
	started time.Time
	count   int
}

func newRateLimiter(limit int, window time.Duration, logger *slog.Logger) *rateLimiter {
	return &rateLimiter{limit: limit, window: window, clients: make(map[string]*clientWindow), now: time.Now, logger: logger}
}

// allow reports whether the client may make another request. Expired windows are swept at most once per window;
// when the table is still full after a sweep, unknown clients are denied (fail closed).
func (l *rateLimiter) allow(client string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	current := l.now()
	if current.Sub(l.lastSweep) >= l.window {
		l.sweep(current)
	}
	entry, found := l.clients[client]
	if found && current.Sub(entry.started) >= l.window {
		delete(l.clients, client)
		found = false
	}
	if !found {
		if len(l.clients) >= maxTrackedClients {
			l.logTableFull()
			return false
		}
		l.clients[client] = &clientWindow{started: current, count: 1}
		return true
	}
	if entry.count >= l.limit {
		return false
	}
	entry.count++
	return true
}

func (l *rateLimiter) sweep(current time.Time) {
	for address, entry := range l.clients {
		if current.Sub(entry.started) >= l.window {
			delete(l.clients, address)
		}
	}
	l.lastSweep = current
	l.fullLogged = false
}

func (l *rateLimiter) logTableFull() {
	if l.fullLogged || l.logger == nil {
		return
	}
	l.fullLogged = true
	l.logger.Warn("rate limiter table is full, denying new clients", "maxTrackedClients", maxTrackedClients)
}

// clientAddress returns the IP used as the rate-limit key. The Nth entry from the right of X-Forwarded-For
// (N = trustedProxyHops) is the one appended by our own proxy; entries further left are client-controlled.
// A missing header, too few entries or a value that is not an IP fall back to the connection address.
func clientAddress(request *http.Request, trustedProxyHops int) string {
	if forwarded := request.Header.Get("X-Forwarded-For"); forwarded != "" {
		entries := strings.Split(forwarded, ",")
		if trustedProxyHops >= 1 && trustedProxyHops <= len(entries) {
			candidate := strings.TrimSpace(entries[len(entries)-trustedProxyHops])
			if address, err := netip.ParseAddr(candidate); err == nil {
				return address.Unmap().String()
			}
		}
	}
	host, _, err := net.SplitHostPort(request.RemoteAddr)
	if err != nil {
		host = request.RemoteAddr
	}
	if address, parseErr := netip.ParseAddr(host); parseErr == nil {
		return address.Unmap().String()
	}
	return host
}
