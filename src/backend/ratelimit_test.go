package main

import (
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestClientAddress(t *testing.T) {
	tests := []struct {
		name          string
		forwarded     string
		hops          int
		remoteAddress string
		want          string
	}{
		{"no header uses the connection", "", 1, "203.0.113.9:4000", "203.0.113.9"},
		{"one hop takes the rightmost entry", "198.51.100.7", 1, "10.0.0.1:80", "198.51.100.7"},
		{"spoofed left entries are ignored", "1.2.3.4, 198.51.100.7", 1, "10.0.0.1:80", "198.51.100.7"},
		{"two hops take the second from the right", "1.2.3.4, 198.51.100.7, 10.1.1.1", 2, "10.0.0.1:80", "198.51.100.7"},
		{"too few entries fall back", "198.51.100.7", 2, "10.0.0.1:80", "10.0.0.1"},
		{"not an ip falls back", "not-an-ip", 1, "10.0.0.1:80", "10.0.0.1"},
		{"huge junk header falls back", strings.Repeat("x", 100000), 1, "10.0.0.1:80", "10.0.0.1"},
		{"ipv6 is normalised", "2001:DB8::1", 1, "10.0.0.1:80", "2001:db8::1"},
		{"ipv6 connection", "", 1, "[2001:db8::2]:80", "2001:db8::2"},
		{"remote address without port", "", 1, "10.0.0.5", "10.0.0.5"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodPost, "/api/check", nil)
			request.RemoteAddr = test.remoteAddress
			if test.forwarded != "" {
				request.Header.Set("X-Forwarded-For", test.forwarded)
			}
			if got := clientAddress(request, test.hops); got != test.want {
				t.Errorf("clientAddress = %q, want %q", got, test.want)
			}
		})
	}
}

func TestRateLimiterSweepsOncePerWindow(t *testing.T) {
	current := time.Now()
	limiter := newRateLimiter(1, time.Minute, nil)
	limiter.now = func() time.Time { return current }

	limiter.allow("a")
	current = current.Add(30 * time.Second)
	limiter.allow("b")
	current = current.Add(31 * time.Second)
	limiter.allow("c")

	// "a" expired and the sweep removed it; "b" is still inside its own window.
	if _, found := limiter.clients["a"]; found {
		t.Error("expired client a should have been swept")
	}
	if _, found := limiter.clients["b"]; !found {
		t.Error("client b is still inside its window")
	}
}

func TestRateLimiterFailsClosedWhenFull(t *testing.T) {
	var logOutput strings.Builder
	var logMutex sync.Mutex
	logger := slog.New(slog.NewTextHandler(writerFunc(func(data []byte) (int, error) {
		logMutex.Lock()
		defer logMutex.Unlock()
		return logOutput.Write(data)
	}), nil))
	current := time.Now()
	limiter := newRateLimiter(5, time.Minute, logger)
	limiter.now = func() time.Time { return current }

	for index := 0; index < maxTrackedClients; index++ {
		if !limiter.allow(fmt.Sprintf("client-%d", index)) {
			t.Fatalf("client %d should fit under the cap", index)
		}
	}
	if limiter.allow("newcomer") || limiter.allow("another") {
		t.Fatal("new clients must be denied when the table is full")
	}
	if !limiter.allow("client-0") {
		t.Fatal("a tracked client keeps its own window")
	}
	if got := strings.Count(logOutput.String(), "table is full"); got != 1 {
		t.Fatalf("table-full warning logged %d times, want once per sweep", got)
	}

	current = current.Add(time.Minute + time.Second)
	if !limiter.allow("newcomer") {
		t.Fatal("after the windows expire the sweep must free room")
	}
}

type writerFunc func([]byte) (int, error)

func (f writerFunc) Write(data []byte) (int, error) { return f(data) }

var _ io.Writer = writerFunc(nil)
