package main

import (
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
)

// rateLimiter allows at most limit requests per window for each client address (fixed window, in memory).
type rateLimiter struct {
	mu      sync.Mutex
	limit   int
	window  time.Duration
	clients map[string]*clientWindow
	now     func() time.Time
}

type clientWindow struct {
	started time.Time
	count   int
}

func newRateLimiter(limit int, window time.Duration) *rateLimiter {
	return &rateLimiter{limit: limit, window: window, clients: make(map[string]*clientWindow), now: time.Now}
}

// allow reports whether the client may make another request and drops windows that already expired.
func (l *rateLimiter) allow(client string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	current := l.now()
	for address, entry := range l.clients {
		if current.Sub(entry.started) >= l.window {
			delete(l.clients, address)
		}
	}
	entry, found := l.clients[client]
	if !found {
		l.clients[client] = &clientWindow{started: current, count: 1}
		return true
	}
	if entry.count >= l.limit {
		return false
	}
	entry.count++
	return true
}

// clientAddress prefers the first X-Forwarded-For hop because the backend only sits behind the front proxy.
func clientAddress(request *http.Request) string {
	if forwarded := request.Header.Get("X-Forwarded-For"); forwarded != "" {
		first, _, _ := strings.Cut(forwarded, ",")
		return strings.TrimSpace(first)
	}
	host, _, err := net.SplitHostPort(request.RemoteAddr)
	if err != nil {
		return request.RemoteAddr
	}
	return host
}
