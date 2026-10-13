// Package api is the UI-facing surface of 556d: an OpenAI-compatible /v1/chat/completions
// (streaming or not) backed by the REAL companion — a persistent hermes serve session with
// SOUL, memory and tools — plus the small /api/* set the Artemis web-chat SPA expects, so the
// existing web chat reaches her without changes. Every completed reply is mirrored to the
// avatar bridge as a speech bubble.
package api

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/Yooouuuuuuu/556_production/556d/internal/bridge"
	"github.com/Yooouuuuuuu/556_production/556d/internal/hermes"
)

type API struct {
	hermes  *hermes.Client
	bridge  *bridge.Bridge
	profile string
	mu      sync.Mutex
	session string // one live Hermes session per daemon lifetime (memory persists regardless)
	turn    sync.Mutex // Hermes runs one turn per session at a time
}

func New(h *hermes.Client, b *bridge.Bridge, profile string) *API {
	return &API{hermes: h, bridge: b, profile: profile}
}

// Register mounts the chat API and, when webChatDir is set, serves the web-chat SPA at /chat/.
func (a *API) Register(mux *http.ServeMux, webChatDir string) {
	if webChatDir != "" {
		fs := http.FileServer(http.Dir(webChatDir))
		mux.Handle("/chat/", http.StripPrefix("/chat/", fs))
		mux.HandleFunc("/chat", func(w http.ResponseWriter, r *http.Request) {
			http.Redirect(w, r, "/chat/", http.StatusMovedPermanently)
		})
	}
	mux.HandleFunc("/v1/chat/completions", a.chat)
	mux.HandleFunc("/v1/models", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]any{"object": "list", "data": []any{map[string]any{"id": "556", "object": "model", "owned_by": "556-production"}}})
	})
	// Artemis web-chat SPA compatibility (what ui/webchat_adapter.py used to provide)
	mux.HandleFunc("/api/chat", a.chat)
	mux.HandleFunc("/api/gateway-config", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]any{"baseUrl": "", "token": "", "models": []any{map[string]any{"id": "556", "name": "556 Production"}}})
	})
	mux.HandleFunc("/api/session-history", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]any{"messages": []any{}})
	})
	mux.HandleFunc("/api/mem0-search", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]any{"results": []any{}})
	})
}

func (a *API) sessionID(ctx context.Context) (string, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.session != "" {
		return a.session, nil
	}
	sid, err := a.hermes.CreateSession(ctx, a.profile)
	if err != nil {
		return "", err
	}
	a.session = sid
	log.Printf("[api] hermes session %s", sid)
	return sid, nil
}

type chatRequest struct {
	Model    string `json:"model"`
	Stream   bool   `json:"stream"`
	Messages []struct {
		Role    string `json:"role"`
		Content any    `json:"content"`
	} `json:"messages"`
}

func (a *API) chat(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
	w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
	if r.Method == http.MethodOptions {
		w.WriteHeader(204)
		return
	}
	body, _ := io.ReadAll(r.Body)
	var req chatRequest
	if err := json.Unmarshal(body, &req); err != nil {
		writeJSON(w, 400, map[string]any{"error": "bad request: " + err.Error()})
		return
	}
	// Hermes owns the conversation history; we only forward the newest user message.
	text := ""
	for i := len(req.Messages) - 1; i >= 0; i-- {
		if req.Messages[i].Role == "user" {
			text = contentText(req.Messages[i].Content)
			break
		}
	}
	if strings.TrimSpace(text) == "" {
		writeJSON(w, 400, map[string]any{"error": "no user message"})
		return
	}

	a.turn.Lock()
	defer a.turn.Unlock()
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()
	sid, err := a.sessionID(ctx)
	if err != nil {
		writeJSON(w, 502, map[string]any{"error": "hermes: " + err.Error()})
		return
	}
	events, unsub := a.hermes.Subscribe(sid)
	defer unsub()
	if err := a.hermes.Submit(ctx, sid, text); err != nil {
		writeJSON(w, 502, map[string]any{"error": "hermes: " + err.Error()})
		return
	}

	id := fmt.Sprintf("chatcmpl-556-%d", time.Now().UnixNano())
	created := time.Now().Unix()
	var sse func(delta map[string]any, finish any, usage any)
	if req.Stream {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.WriteHeader(200)
		fl, _ := w.(http.Flusher)
		sse = func(delta map[string]any, finish any, usage any) {
			c := map[string]any{"id": id, "object": "chat.completion.chunk", "created": created, "model": "556",
				"choices": []any{map[string]any{"index": 0, "delta": delta, "finish_reason": finish}}}
			if usage != nil {
				c["usage"] = usage
			}
			b, _ := json.Marshal(c)
			_, _ = io.WriteString(w, "data: "+string(b)+"\n\n")
			if fl != nil {
				fl.Flush()
			}
		}
		sse(map[string]any{"role": "assistant"}, nil, nil)
	}

	var full strings.Builder
	var usage any
	status := "stop"
	for done := false; !done; {
		select {
		case ev := <-events:
			switch ev.Type {
			case "message.delta":
				if t, _ := ev.Payload["text"].(string); t != "" {
					full.WriteString(t)
					if sse != nil {
						sse(map[string]any{"content": t}, nil, nil)
					}
				}
			case "message.complete":
				if t, _ := ev.Payload["text"].(string); t != "" && full.Len() == 0 {
					full.WriteString(t)
					if sse != nil {
						sse(map[string]any{"content": t}, nil, nil)
					}
				}
				usage = ev.Payload["usage"]
				if s, _ := ev.Payload["status"].(string); s == "error" {
					status = "error"
				}
				done = true
			case "error":
				msg, _ := ev.Payload["message"].(string)
				log.Printf("[api] hermes error: %s", msg)
				if full.Len() == 0 {
					full.WriteString("（她好像遇到了問題：" + msg + "）")
				}
				status = "error"
				done = true
			case "tool.start":
				log.Printf("[api] tool: %v", ev.Payload["name"])
			case "approval.request", "clarify.request":
				log.Printf("[api] %s needs a UI (not built yet): %v", ev.Type, ev.Payload)
			}
		case <-ctx.Done():
			status = "timeout"
			done = true
		}
	}

	reply := full.String()
	a.bubble(reply)
	if sse != nil {
		sse(map[string]any{}, status, usage)
		_, _ = io.WriteString(w, "data: [DONE]\n\n")
		if fl, ok := w.(http.Flusher); ok {
			fl.Flush()
		}
		return
	}
	writeJSON(w, 200, map[string]any{
		"id": id, "object": "chat.completion", "created": created, "model": "556",
		"choices": []any{map[string]any{"index": 0, "finish_reason": status,
			"message": map[string]any{"role": "assistant", "content": reply}}},
		"usage": usage,
	})
}

// bubble mirrors a reply onto the avatar (same behavior the Python adapter had).
func (a *API) bubble(text string) {
	if a.bridge == nil || strings.TrimSpace(text) == "" {
		return
	}
	runes := []rune(text)
	if len(runes) > 120 {
		text = string(runes[:120])
	}
	ms := max(4000, min(12000, len([]rune(text))*120))
	a.bridge.Broadcast(map[string]any{"type": "message", "text": text, "duration": ms})
}

func contentText(c any) string {
	switch v := c.(type) {
	case string:
		return v
	case []any: // OpenAI content parts
		var sb strings.Builder
		for _, p := range v {
			if pm, ok := p.(map[string]any); ok {
				if t, _ := pm["text"].(string); t != "" {
					sb.WriteString(t)
				}
			}
		}
		return sb.String()
	}
	return ""
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

var _ = url.QueryEscape
