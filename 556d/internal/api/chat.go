// Package api is the UI-facing surface of 556d — the hub every client talks to:
//   - OpenAI-compatible /v1/chat/completions (stream or JSON) backed by the REAL companion: a
//     persistent hermes serve session with SOUL, memory and tools;
//   - hub events on the bridge WebSocket so every connected window/channel sees the same
//     conversation (chat.user / chat.delta / chat.complete / chat.error / companion.state);
//   - /api/history, /api/settings, /api/companion, /api/restart-hermes;
//   - the small /api/* set the transitional Artemis web-chat SPA expects.
//
// Turns are serialized per companion: several clients may send at once, they queue.
package api

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/Yooouuuuuuu/556_production/556d/internal/bridge"
	"github.com/Yooouuuuuuu/556_production/556d/internal/hermes"
	"github.com/Yooouuuuuuu/556_production/556d/internal/supervisor"
)

type API struct {
	hermes   *hermes.Client
	bridge   *bridge.Bridge
	sup      *supervisor.Supervisor
	settings *SettingsStore
	profile  string
	mu       sync.Mutex
	session  hermes.Session
	gen      int64      // hermes connection generation the session belongs to
	turn     sync.Mutex // one turn at a time per companion
}

func New(h *hermes.Client, b *bridge.Bridge, sup *supervisor.Supervisor, profile, hermesHome string) *API {
	return &API{hermes: h, bridge: b, sup: sup, settings: NewSettingsStore(hermesHome), profile: profile}
}

// Register mounts the API. The 0.3.0 app is the only UI; the transitional web-chat SPA is gone.
func (a *API) Register(mux *http.ServeMux) {
	mux.HandleFunc("/v1/chat/completions", a.chat)
	mux.HandleFunc("/v1/models", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]any{"object": "list", "data": []any{map[string]any{"id": "556", "object": "model", "owned_by": "556-production"}}})
	})
	mux.HandleFunc("/api/history", a.history)
	mux.HandleFunc("/api/settings", a.settingsHandler)
	mux.HandleFunc("/api/companion", a.companion)
	mux.HandleFunc("/api/restart-hermes", a.restartHermes)
	mux.HandleFunc("/api/chat", a.chat) // same handler; the app and probes use this path
}

// sessionFor returns the live Hermes session, creating one when none exists or when Hermes
// reconnected (its sessions are per process).
func (a *API) sessionFor(ctx context.Context) (hermes.Session, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.session.ID != "" && a.gen == a.hermes.Generation() {
		return a.session, nil
	}
	s, err := a.hermes.CreateSession(ctx, a.profile)
	if err != nil {
		return hermes.Session{}, err
	}
	a.session, a.gen = s, a.hermes.Generation()
	log.Printf("[api] hermes session %s (stored %s)", s.ID, s.Stored)
	return s, nil
}

func (a *API) emit(ev map[string]any) {
	if a.bridge != nil {
		a.bridge.Broadcast(ev)
	}
}

type chatRequest struct {
	Model    string `json:"model"`
	Stream   bool   `json:"stream"`
	Messages []struct {
		Role    string `json:"role"`
		Content any    `json:"content"`
	} `json:"messages"`
}

func cors(w http.ResponseWriter, r *http.Request, methods string) bool {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-556-Client")
	w.Header().Set("Access-Control-Allow-Methods", methods)
	if r.Method == http.MethodOptions {
		w.WriteHeader(204)
		return true
	}
	return false
}

func (a *API) chat(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	body, _ := io.ReadAll(r.Body)
	var req chatRequest
	if err := json.Unmarshal(body, &req); err != nil {
		writeJSON(w, 400, map[string]any{"error": "bad request: " + err.Error()})
		return
	}
	// Hermes owns the conversation history; only the newest user message is forwarded.
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
	source := r.Header.Get("X-556-Client")
	if source == "" {
		source = "http"
	}

	a.turn.Lock()
	defer a.turn.Unlock()
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()
	sess, err := a.sessionFor(ctx)
	if err != nil {
		writeJSON(w, 502, map[string]any{"error": "hermes: " + err.Error()})
		return
	}
	events, unsub := a.hermes.Subscribe(sess.ID)
	defer unsub()
	if err := a.hermes.Submit(ctx, sess.ID, text); err != nil {
		writeJSON(w, 502, map[string]any{"error": "hermes: " + err.Error()})
		return
	}
	a.emit(map[string]any{"type": "chat.user", "text": text, "source": source})
	a.emit(map[string]any{"type": "companion.state", "talking": true})

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
					a.emit(map[string]any{"type": "chat.delta", "text": t})
					if sse != nil {
						sse(map[string]any{"content": t}, nil, nil)
					}
				}
			case "message.complete":
				if t, _ := ev.Payload["text"].(string); t != "" && full.Len() == 0 {
					full.WriteString(t)
					a.emit(map[string]any{"type": "chat.delta", "text": t})
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
				a.emit(map[string]any{"type": "chat.error", "message": msg})
				if full.Len() == 0 {
					full.WriteString("（她好像遇到了問題：" + msg + "）")
				}
				status = "error"
				done = true
			case "tool.start":
				log.Printf("[api] tool: %v", ev.Payload["name"])
			case "approval.request", "clarify.request":
				log.Printf("[api] %s (companion toolset should not need this): %v", ev.Type, ev.Payload)
			}
		case <-ctx.Done():
			status = "timeout"
			done = true
		}
	}

	reply := full.String()
	a.emit(map[string]any{"type": "chat.complete", "text": reply, "status": status, "usage": usage})
	a.emit(map[string]any{"type": "companion.state", "talking": false})
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

// history returns the last N turns (2N messages) of the live session, normalized.
func (a *API) history(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, OPTIONS") {
		return
	}
	turns := a.settings.Get().ContextTurns
	if v, err := strconv.Atoi(r.URL.Query().Get("limit")); err == nil && v > 0 {
		turns = v
	}
	ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	sess, err := a.sessionFor(ctx)
	if err != nil {
		writeJSON(w, 502, map[string]any{"error": "hermes: " + err.Error()})
		return
	}
	rows, err := a.hermes.History(ctx, sess.Stored, turns*2)
	if err != nil {
		writeJSON(w, 502, map[string]any{"error": err.Error()})
		return
	}
	out := make([]map[string]any, 0, len(rows))
	for _, m := range rows {
		role, _ := m["role"].(string)
		if role != "user" && role != "assistant" {
			continue
		}
		text := contentText(m["content"])
		if text == "" {
			text = contentText(m["text"])
		}
		if strings.TrimSpace(text) == "" {
			continue
		}
		out = append(out, map[string]any{"role": role, "text": text, "ts": m["timestamp"]})
	}
	writeJSON(w, 200, map[string]any{"session_id": sess.Stored, "turns": turns, "messages": out})
}

func (a *API) settingsHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, PUT, OPTIONS") {
		return
	}
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, 200, map[string]any{"settings": a.settings.Get(),
			"notes": map[string]any{"memory_language": "effective in the kokoro engine (Path C); the mem0 provider has no prompt hook"}})
	case http.MethodPut:
		body, _ := io.ReadAll(r.Body)
		next, ap, err := a.settings.Update(body)
		if err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]any{"settings": next, "restart_required": ap.RestartRequired, "reembed_required": ap.ReembedRequired})
	default:
		writeJSON(w, 405, map[string]any{"error": "method not allowed"})
	}
}

func (a *API) companion(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, OPTIONS") {
		return
	}
	s := a.settings.Get()
	writeJSON(w, 200, map[string]any{
		"name": s.CompanionName, "profile": a.profile,
		"avatar_model_url": "/" + strings.TrimPrefix(s.AvatarModel, "/"),
		"hermes_connected":  a.hermes.Connected(),
	})
}

func (a *API) restartHermes(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, 405, map[string]any{"error": "POST only"})
		return
	}
	if err := a.sup.Restart("hermes"); err != nil {
		writeJSON(w, 500, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, 202, map[string]any{"ok": true, "note": "hermes serve restarting; sessions are recreated on demand"})
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
