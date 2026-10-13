// Package hermes is a JSON-RPC-over-WebSocket client for `hermes serve` (tui_gateway): the same
// protocol Hermes Desktop uses. Newline-delimited JSON-RPC 2.0 frames; server events arrive as
// notifications {method:"event", params:{type, session_id, payload}}; streaming deltas may be
// coalesced several-per-frame, so every inbound message is split on newlines.
package hermes

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

type Event struct {
	Type      string         `json:"type"`
	SessionID string         `json:"session_id"`
	Payload   map[string]any `json:"payload"`
}

type frame struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      *int64          `json:"id,omitempty"`
	Method  string          `json:"method,omitempty"`
	Params  json.RawMessage `json:"params,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type Client struct {
	url     string
	mu      sync.Mutex
	conn    *websocket.Conn
	nextID  atomic.Int64
	pending map[int64]chan frame
	subs    map[string][]chan Event // session_id -> subscribers
	ready   chan struct{}
}

func New(host string, port int, token string) *Client {
	return &Client{
		url:     fmt.Sprintf("ws://%s:%d/api/ws?token=%s", host, port, token),
		pending: map[int64]chan frame{},
		subs:    map[string][]chan Event{},
		ready:   make(chan struct{}),
	}
}

// Connect dials and starts the reader; it retries until ctx is cancelled.
func (c *Client) Connect(ctx context.Context) error {
	for attempt := 1; ; attempt++ {
		conn, _, err := websocket.DefaultDialer.DialContext(ctx, c.url, nil)
		if err == nil {
			c.mu.Lock()
			c.conn = conn
			c.mu.Unlock()
			go c.reader(conn)
			select {
			case <-c.ready:
				log.Printf("[hermes] connected (%s)", c.url[:strings.Index(c.url, "?")])
				return nil
			case <-time.After(15 * time.Second):
				conn.Close()
				err = errors.New("no gateway.ready within 15s")
			case <-ctx.Done():
				conn.Close()
				return ctx.Err()
			}
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		wait := time.Duration(min(attempt, 10)) * time.Second
		log.Printf("[hermes] connect failed (%v); retry in %s", err, wait)
		select {
		case <-time.After(wait):
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}

func (c *Client) reader(conn *websocket.Conn) {
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			log.Printf("[hermes] connection lost: %v", err)
			c.mu.Lock()
			if c.conn == conn {
				c.conn = nil
			}
			for id, ch := range c.pending {
				ch <- frame{Error: &rpcError{Code: -1, Message: "connection lost"}}
				delete(c.pending, id)
			}
			c.mu.Unlock()
			return
		}
		for _, line := range strings.Split(string(data), "\n") {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			var f frame
			if json.Unmarshal([]byte(line), &f) != nil {
				continue
			}
			c.handle(f)
		}
	}
}

func (c *Client) handle(f frame) {
	if f.ID != nil && f.Method == "" { // response
		c.mu.Lock()
		ch, ok := c.pending[*f.ID]
		delete(c.pending, *f.ID)
		c.mu.Unlock()
		if ok {
			ch <- f
		}
		return
	}
	if f.Method != "event" {
		return
	}
	var ev Event
	if json.Unmarshal(f.Params, &ev) != nil {
		return
	}
	if ev.Type == "gateway.ready" {
		select {
		case <-c.ready:
		default:
			close(c.ready)
		}
		return
	}
	c.mu.Lock()
	subs := append([]chan Event(nil), c.subs[ev.SessionID]...)
	c.mu.Unlock()
	for _, s := range subs {
		select {
		case s <- ev:
		default:
			log.Printf("[hermes] dropping event %s: subscriber slow", ev.Type)
		}
	}
}

// Call sends a request and waits for its response.
func (c *Client) Call(ctx context.Context, method string, params any) (json.RawMessage, error) {
	c.mu.Lock()
	conn := c.conn
	if conn == nil {
		c.mu.Unlock()
		return nil, errors.New("hermes not connected")
	}
	id := c.nextID.Add(1)
	ch := make(chan frame, 1)
	c.pending[id] = ch
	req := map[string]any{"jsonrpc": "2.0", "id": id, "method": method, "params": params}
	data, _ := json.Marshal(req)
	err := conn.WriteMessage(websocket.TextMessage, append(data, '\n'))
	c.mu.Unlock()
	if err != nil {
		return nil, err
	}
	select {
	case f := <-ch:
		if f.Error != nil {
			return nil, fmt.Errorf("%s: %s (code %d)", method, f.Error.Message, f.Error.Code)
		}
		return f.Result, nil
	case <-ctx.Done():
		c.mu.Lock()
		delete(c.pending, id)
		c.mu.Unlock()
		return nil, ctx.Err()
	}
}

// Subscribe returns a channel receiving events for sid; call the cancel func when done.
func (c *Client) Subscribe(sid string) (<-chan Event, func()) {
	ch := make(chan Event, 256)
	c.mu.Lock()
	c.subs[sid] = append(c.subs[sid], ch)
	c.mu.Unlock()
	return ch, func() {
		c.mu.Lock()
		list := c.subs[sid]
		for i, s := range list {
			if s == ch {
				c.subs[sid] = append(list[:i], list[i+1:]...)
				break
			}
		}
		c.mu.Unlock()
	}
}

// CreateSession opens a fresh agent session (profile "" = the home's default companion).
func (c *Client) CreateSession(ctx context.Context, profile string) (string, error) {
	params := map[string]any{"messages": []any{}}
	if profile != "" {
		params["profile"] = profile
	}
	res, err := c.Call(ctx, "session.create", params)
	if err != nil {
		return "", err
	}
	var out struct {
		SessionID string `json:"session_id"`
	}
	if err := json.Unmarshal(res, &out); err != nil || out.SessionID == "" {
		return "", fmt.Errorf("session.create: bad result %s", string(res))
	}
	return out.SessionID, nil
}

// Submit sends a user prompt; the reply streams as events on the session.
func (c *Client) Submit(ctx context.Context, sid, text string) error {
	_, err := c.Call(ctx, "prompt.submit", map[string]any{"session_id": sid, "text": text})
	return err
}

func (c *Client) Connected() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.conn != nil
}
