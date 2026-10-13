// Package hermesapi is 556d's client of a companion's Hermes gateway API server (the
// OpenAI-compatible platform inside `hermes gateway run`). The app talks to her through this,
// exactly as Telegram talks to her through its adapter: one Hermes process per character.
package hermesapi

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type Client struct {
	BaseURL string // http://127.0.0.1:<port>
	Key     string // API_SERVER_KEY
	http    *http.Client
	model   string
}

func New(baseURL, key string) *Client {
	return &Client{BaseURL: strings.TrimRight(baseURL, "/"), Key: key, http: &http.Client{Timeout: 0}}
}

func (c *Client) req(ctx context.Context, method, path string, body any) (*http.Request, error) {
	var rd io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		rd = bytes.NewReader(b)
	}
	r, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, rd)
	if err != nil {
		return nil, err
	}
	if body != nil {
		r.Header.Set("Content-Type", "application/json")
	}
	if c.Key != "" {
		r.Header.Set("Authorization", "Bearer "+c.Key)
	}
	return r, nil
}

// Healthy probes /health with a short timeout.
func (c *Client) Healthy() bool {
	ctx, cancel := context.WithTimeout(context.Background(), 1500*time.Millisecond)
	defer cancel()
	r, err := c.req(ctx, http.MethodGet, "/health", nil)
	if err != nil {
		return false
	}
	resp, err := c.http.Do(r)
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode < 300
}

// Model returns the alias the API server advertises (first /v1/models entry), cached.
func (c *Client) Model(ctx context.Context) string {
	if c.model != "" {
		return c.model
	}
	r, err := c.req(ctx, http.MethodGet, "/v1/models", nil)
	if err == nil {
		if resp, err := c.http.Do(r); err == nil {
			defer resp.Body.Close()
			var out struct {
				Data []struct {
					ID string `json:"id"`
				} `json:"data"`
			}
			if json.NewDecoder(resp.Body).Decode(&out) == nil && len(out.Data) > 0 {
				c.model = out.Data[0].ID
			}
		}
	}
	if c.model == "" {
		c.model = "hermes"
	}
	return c.model
}

type Result struct {
	Reply     string
	SessionID string
	Usage     any
	Status    string // stop | length | error (OpenAI finish_reason, "error" on transport/envelope errors)
	Err       string
}

// Chat sends one user message into the conversation named by sessionKey (continuing sessionID
// when known) and returns the final reply. One non-stream request: the API server's SSE path
// only relays deltas the model streamed, and with the shim answering in one chunk none arrive,
// so the body is the reliable carrier. Returns the session id Hermes used (X-Hermes-Session-Id).
func (c *Client) Chat(ctx context.Context, text, sessionKey, sessionID, system string) (Result, error) {
	msgs := []map[string]any{}
	if strings.TrimSpace(system) != "" { // an ephemeral hint for this turn only (SOUL stays hers)
		msgs = append(msgs, map[string]any{"role": "system", "content": system})
	}
	msgs = append(msgs, map[string]any{"role": "user", "content": text})
	body := map[string]any{
		"model":    c.Model(ctx),
		"stream":   false,
		"messages": msgs,
	}
	r, err := c.req(ctx, http.MethodPost, "/v1/chat/completions", body)
	if err != nil {
		return Result{}, err
	}
	if sessionKey != "" {
		r.Header.Set("X-Hermes-Session-Key", sessionKey)
	}
	if sessionID != "" {
		r.Header.Set("X-Hermes-Session-Id", sessionID)
	}
	resp, err := c.http.Do(r)
	if err != nil {
		return Result{}, err
	}
	defer resp.Body.Close()
	res := Result{SessionID: resp.Header.Get("X-Hermes-Session-Id"), Status: "stop"}
	data, err := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	if err != nil {
		return res, err
	}
	var out struct {
		Choices []struct {
			Message      map[string]any `json:"message"`
			FinishReason string         `json:"finish_reason"`
		} `json:"choices"`
		Usage any `json:"usage"`
		Error *struct {
			Message string `json:"message"`
		} `json:"error"`
		Hermes map[string]any `json:"hermes"`
	}
	if jerr := json.Unmarshal(data, &out); jerr != nil {
		if resp.StatusCode >= 300 {
			return res, fmt.Errorf("hermes api: HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(data[:min(len(data), 4096)])))
		}
		return res, fmt.Errorf("hermes api: bad JSON: %w", jerr)
	}
	if out.Error != nil {
		res.Status, res.Err = "error", out.Error.Message
		return res, fmt.Errorf("hermes api: HTTP %d: %s", resp.StatusCode, out.Error.Message)
	}
	if resp.StatusCode >= 300 {
		return res, fmt.Errorf("hermes api: HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(data[:min(len(data), 4096)])))
	}
	res.Usage = out.Usage
	if len(out.Choices) > 0 {
		res.Reply = contentText(out.Choices[0].Message["content"])
		if fr := out.Choices[0].FinishReason; fr != "" {
			res.Status = fr
		}
	}
	if e := resp.Header.Get("X-Hermes-Error"); e != "" {
		res.Err = e
	} else if m, _ := out.Hermes["error"].(string); m != "" {
		res.Err = m
	}
	return res, nil
}

// CreateSession opens an empty session with a chosen id and source (POST /api/sessions). 409
// (already exists) counts as success.
func (c *Client) CreateSession(ctx context.Context, id, source string) error {
	r, err := c.req(ctx, http.MethodPost, "/api/sessions", map[string]any{"id": id, "source": source})
	if err != nil {
		return err
	}
	resp, err := c.http.Do(r)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 && resp.StatusCode != http.StatusConflict {
		data, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("hermes api: HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(data)))
	}
	return nil
}

func contentText(c any) string {
	switch v := c.(type) {
	case string:
		return v
	case []any:
		var sb strings.Builder
		for _, p := range v {
			if pm, ok := p.(map[string]any); ok {
				if t, _ := pm["text"].(string); t != "" {
					sb.WriteString(t)
				}
			}
		}
		return sb.String()
	case map[string]any:
		if t, _ := v["text"].(string); t != "" {
			return t
		}
	}
	return ""
}
