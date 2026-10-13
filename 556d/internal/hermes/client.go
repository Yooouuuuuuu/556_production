// Package hermes is a JSON-RPC-over-WebSocket client for `hermes serve` (tui_gateway): the same
// protocol Hermes Desktop uses. Newline-delimited JSON-RPC 2.0 frames; server events arrive as
// notifications {method:"event", params:{type, session_id, payload}}; streaming deltas may be
// coalesced several-per-frame, so every inbound message is split on newlines. The client
// reconnects on loss; Generation() changes on every successful connect so callers know their
// server-side sessions are gone (tui_gateway sessions are per process).
package hermes

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
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
	host, token string
	port        int
	ctx         context.Context
	mu          sync.Mutex
	conn        *websocket.Conn
	nextID      atomic.Int64
	gen         atomic.Int64
	pending     map[int64]chan frame
	subs        map[string][]chan Event // session_id -> subscribers
	ready       chan struct{}
	readyOnce   *sync.Once
	http        *http.Client
}

func New(host string, port int, token string) *Client {
	return &Client{
		host: host, port: port, token: token,
		pending: map[int64]chan frame{},
		subs:    map[string][]chan Event{},
		http:    &http.Client{Timeout: 30 * time.Second},
	}
}

func (c *Client) wsURL() string {
	return fmt.Sprintf("ws://%s:%d/api/ws?token=%s", c.host, c.port, url.QueryEscape(c.token))
}

// Connect dials (retrying until ctx is cancelled) and keeps reconnecting after any loss.
func (c *Client) Connect(ctx context.Context) error {
	c.ctx = ctx
	return c.connect()
}

func (c *Client) connect() error {
	for attempt := 1; ; attempt++ {
		c.mu.Lock()
		c.ready = make(chan struct{})
		c.readyOnce = &sync.Once{}
		ready := c.ready
		c.mu.Unlock()

		conn, _, err := websocket.DefaultDialer.DialContext(c.ctx, c.wsURL(), nil)
		if err == nil {
			c.mu.Lock()
			c.conn = conn
			c.mu.Unlock()
			go c.reader(conn)
			select {
			case <-ready:
				c.gen.Add(1)
				log.Printf("[hermes] connected (generation %d)", c.gen.Load())
				return nil
			case <-time.After(15 * time.Second):
				conn.Close()
				err = errors.New("no gateway.ready within 15s")
			case <-c.ctx.Done():
				conn.Close()
				return c.ctx.Err()
			}
		}
		if c.ctx.Err() != nil {
			return c.ctx.Err()
		}
		wait := time.Duration(min(attempt, 10)) * time.Second
		log.Printf("[hermes] connect failed (%v); retry in %s", err, wait)
		select {
		case <-time.After(wait):
		case <-c.ctx.Done():
			return c.ctx.Err()
		}
	}
}

func (c *Client) reader(conn *websocket.Conn) {
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			c.mu.Lock()
			lost := c.conn == conn
			if lost {
				c.conn = nil
			}
			for id, ch := range c.pending {
				ch <- frame{Error: &rpcError{Code: -1, Message: "connection lost"}}
				delete(c.pending, id)
			}
			c.mu.Unlock()
			if lost && c.ctx != nil && c.ctx.Err() == nil {
				log.Printf("[hermes] connection lost (%v); reconnecting", err)
				go func() { _ = c.connect() }()
			}
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
		c.mu.Lock()
		once, ready := c.readyOnce, c.ready
		c.mu.Unlock()
		if once != nil {
			once.Do(func() { close(ready) })
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

// Generation increments on every successful (re)connect.
func (c *Client) Generation() int64 { return c.gen.Load() }

func (c *Client) Connected() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.conn != nil
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
	data, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": id, "method": method, "params": params})
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

// Session identifies a live agent session: the UI-side id used for RPCs and the durable
// state.db id used by REST routes (history).
type Session struct {
	ID     string
	Stored string
}

// CreateSession opens a fresh agent session (profile "" = the home's default companion).
func (c *Client) CreateSession(ctx context.Context, profile string) (Session, error) {
	params := map[string]any{"messages": []any{}}
	if profile != "" {
		params["profile"] = profile
	}
	res, err := c.Call(ctx, "session.create", params)
	if err != nil {
		return Session{}, err
	}
	var out struct {
		SessionID string `json:"session_id"`
		Stored    string `json:"stored_session_id"`
	}
	if err := json.Unmarshal(res, &out); err != nil || out.SessionID == "" {
		return Session{}, fmt.Errorf("session.create: bad result %s", string(res))
	}
	return Session{ID: out.SessionID, Stored: out.Stored}, nil
}

// Submit sends a user prompt; the reply streams as events on the session.
func (c *Client) Submit(ctx context.Context, sid, text string) error {
	_, err := c.Call(ctx, "prompt.submit", map[string]any{"session_id": sid, "text": text})
	return err
}

// History fetches the latest `limit` stored messages of a session via hermes serve's REST API.
// A session with no persisted rows yet yields an empty list.
func (c *Client) History(ctx context.Context, stored string, limit int) ([]map[string]any, error) {
	if stored == "" {
		return nil, nil
	}
	u := fmt.Sprintf("http://%s:%d/api/sessions/%s/messages?limit=%d&order=latest", c.host, c.port, url.PathEscape(stored), limit)
	req, _ := http.NewRequestWithContext(ctx, "GET", u, nil)
	req.Header.Set("X-Hermes-Session-Token", c.token)
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == 404 {
		return nil, nil
	}
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("history: HTTP %d: %.200s", resp.StatusCode, string(body))
	}
	var out struct {
		Messages []map[string]any `json:"messages"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	return out.Messages, nil
}
