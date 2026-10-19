// Package shim is the OpenAI-compatible model router: Hermes sends model="auto/<lane>",
// routing.json maps lanes to backends (single name or an ordered fallback list), and
// backends without native tool calling get the Nous <tool_call> text protocol injected
// and parsed back. Port of shim/shim.py; parity is enforced by golden tests.
package shim

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"sync"
	"time"
)

type Backend struct {
	BaseURL     string `toml:"base_url"`
	Model       string `toml:"model"`
	NativeTools bool   `toml:"native_tools"`
}

type Config struct {
	Port        int                `toml:"port"`
	RoutingFile string             `toml:"routing_file"`
	Backends    map[string]Backend `toml:"backends"`
	Timeout     int                `toml:"timeout_seconds"`
}

type routing struct {
	Default string         `json:"default"`
	Lanes   map[string]any `json:"lanes"`
}

type Shim struct {
	cfg    Config
	client *http.Client
	mu     sync.Mutex
	rmtime time.Time
	rdata  routing
}

func New(cfg Config) *Shim {
	if cfg.Timeout == 0 {
		cfg.Timeout = 600
	}
	return &Shim{cfg: cfg, client: &http.Client{Timeout: time.Duration(cfg.Timeout) * time.Second},
		rdata: routing{Default: "qwen", Lanes: map[string]any{}}}
}

func (s *Shim) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/models", s.models)
	mux.HandleFunc("/v1/chat/completions", s.chat)
	return mux
}

// ListenAndServe runs until ctx is cancelled.
func (s *Shim) ListenAndServe(ctx context.Context) error {
	srv := &http.Server{Addr: fmt.Sprintf("127.0.0.1:%d", s.cfg.Port), Handler: s.Handler()}
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdownCtx)
	}()
	log.Printf("[shim] listening on :%d", s.cfg.Port)
	err := srv.ListenAndServe()
	if err == http.ErrServerClosed {
		return nil
	}
	return err
}

// routing re-reads routing.json when its mtime changes (hot reload, like the Python shim).
func (s *Shim) routing() routing {
	s.mu.Lock()
	defer s.mu.Unlock()
	st, err := os.Stat(s.cfg.RoutingFile)
	if err != nil {
		return s.rdata
	}
	if !st.ModTime().Equal(s.rmtime) {
		if b, err := os.ReadFile(s.cfg.RoutingFile); err == nil {
			var r routing
			if json.Unmarshal(b, &r) == nil {
				if r.Lanes == nil {
					r.Lanes = map[string]any{}
				}
				s.rdata = r
				s.rmtime = st.ModTime()
			}
		}
	}
	return s.rdata
}

type pick struct {
	name string
	be   Backend
}

// pickBackends resolves a lane to its ordered fallback chain.
func (s *Shim) pickBackends(model string) (string, []pick) {
	r := s.routing()
	lane := model
	if strings.HasPrefix(model, "auto/") {
		lane = strings.SplitN(model, "/", 2)[1]
	}
	spec, ok := r.Lanes[lane]
	if !ok {
		spec = r.Default
	}
	var names []string
	switch v := spec.(type) {
	case string:
		names = []string{v}
	case []any:
		for _, x := range v {
			names = append(names, str(x))
		}
	}
	var chain []pick
	for _, n := range names {
		if be, ok := s.cfg.Backends[n]; ok {
			chain = append(chain, pick{n, be})
		}
	}
	if len(chain) == 0 {
		if be, ok := s.cfg.Backends[r.Default]; ok {
			chain = []pick{{r.Default, be}}
		}
	}
	return lane, chain
}

func (s *Shim) models(w http.ResponseWriter, _ *http.Request) {
	set := map[string]bool{"tasks": true, "probe": true}
	for l := range s.routing().Lanes {
		set[l] = true
	}
	lanes := make([]string, 0, len(set))
	for l := range set {
		lanes = append(lanes, l)
	}
	sort.Strings(lanes)
	data := make([]any, 0, len(lanes))
	for _, l := range lanes {
		data = append(data, map[string]any{"id": "auto/" + l, "object": "model", "owned_by": "556d-shim"})
	}
	writeJSON(w, 200, map[string]any{"object": "list", "data": data})
}

type upstreamError struct {
	code   int
	detail string
}

func (e *upstreamError) Error() string { return fmt.Sprintf("HTTP %d: %s", e.code, e.detail) }

func (s *Shim) upstream(be Backend, body map[string]any) (map[string]any, error) {
	req, err := http.NewRequest("POST", be.BaseURL+"/chat/completions", bytes.NewBufferString(marshal(body)))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		d := string(raw)
		if len(d) > 300 {
			d = d[:300]
		}
		return nil, &upstreamError{resp.StatusCode, d}
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("bad upstream JSON: %w", err)
	}
	return out, nil
}

func deepCopy(m map[string]any) map[string]any {
	b, _ := json.Marshal(m)
	var out map[string]any
	_ = json.Unmarshal(b, &out)
	return out
}

func firstChoice(resp map[string]any) (map[string]any, map[string]any) {
	choices, _ := resp["choices"].([]any)
	if len(choices) == 0 {
		return nil, nil
	}
	ch, _ := choices[0].(map[string]any)
	msg, _ := ch["message"].(map[string]any)
	return ch, msg
}

func (s *Shim) chat(w http.ResponseWriter, r *http.Request) {
	rawBody, _ := io.ReadAll(r.Body)
	var original map[string]any
	if err := json.Unmarshal(rawBody, &original); err != nil {
		writeJSON(w, 400, map[string]any{"error": "bad request: " + err.Error()})
		return
	}
	var raw rawParts
	_ = json.Unmarshal(rawBody, &raw)
	wantStream, _ := original["stream"].(bool)
	lane, chain := s.pickBackends(str(original["model"]))
	var lastCode int
	var lastDetail string
	for idx, p := range chain {
		attempts := 4 // emulated backends fail intermittently (~50%): retry
		if p.be.NativeTools {
			attempts = 1
		}
		for att := 1; att <= attempts; att++ {
			t0 := time.Now()
			req := deepCopy(original)
			req["model"] = p.be.Model
			req["stream"] = false
			var resp map[string]any
			var err error
			if p.be.NativeTools {
				filterSystemMessages(req) // prompt hygiene on the passthrough path too
				resp, err = s.upstream(p.be, req)
				if err == nil {
					log.Printf("[shim] lane=%s -> %s passthrough %.1fs", lane, p.name, time.Since(t0).Seconds())
				}
			} else {
				nTools := len(raw.Tools)
				req = toTextProtocol(req, raw)
				resp, err = s.upstream(p.be, req)
				if err == nil {
					ch, msg := firstChoice(resp)
					if msg == nil {
						msg = map[string]any{}
					}
					visible, scratch := stripThink(str(msg["content"])) // her hidden scratch never leaves the shim
					if scratch != "" {
						if rs := []rune(scratch); len(rs) > 400 {
							scratch = string(rs[:400]) + "…"
						}
						log.Printf("[shim] lane=%s scratch: %q", lane, scratch)
					}
					calls, cleaned := parseToolCalls(visible, time.Now)
					calls, cleaned = unwrapReplyFunction(calls, cleaned) // the proxy's own reply function is text, not a tool
					broken := len(calls) == 0 && (strings.TrimSpace(cleaned) == "" ||
						strings.HasPrefix(strings.TrimSpace(cleaned), "[openmini/") ||
						strings.Contains(cleaned, "returned no text"))
					if broken {
						lastCode, lastDetail = 502, p.name+" empty/glitch response"
						head := strings.TrimSpace(str(msg["content"]))
						if rs := []rune(head); len(rs) > 160 {
							head = string(rs[:160]) + "…"
						}
						log.Printf("[shim] lane=%s -> %s EMPTY (attempt %d/%d) %.1fs finish=%v body=%q", lane, p.name, att, attempts, time.Since(t0).Seconds(), ch["finish_reason"], head)
						continue
					}
					if len(calls) > 0 {
						tcs := make([]any, len(calls))
						for i, c := range calls {
							tcs[i] = c
						}
						msg["tool_calls"] = tcs
						if cleaned == "" {
							msg["content"] = nil
						} else {
							msg["content"] = cleaned
						}
						if ch != nil {
							ch["finish_reason"] = "tool_calls"
						}
					}
					if ch != nil {
						ch["message"] = msg
					}
					log.Printf("[shim] lane=%s -> %s tools_in=%d tool_calls_out=%d attempt=%d %.1fs",
						lane, p.name, nTools, len(calls), att, time.Since(t0).Seconds())
					logToolNames(raw)
				}
			}
			if err != nil {
				if ue, ok := err.(*upstreamError); ok {
					lastCode, lastDetail = ue.code, ue.detail
					log.Printf("[shim] lane=%s -> %s HTTP %d: %s (attempt %d/%d)", lane, p.name, ue.code, ue.detail, att, attempts)
				} else {
					lastCode, lastDetail = 502, err.Error()
					log.Printf("[shim] lane=%s -> %s ERROR %v (attempt %d/%d)", lane, p.name, err, att, attempts)
				}
				continue
			}
			s.deliver(w, resp, wantStream)
			return
		}
		if idx+1 < len(chain) {
			log.Printf("[shim] lane=%s: %s exhausted -> falling back", lane, p.name)
		}
	}
	if lastCode == 0 {
		lastCode, lastDetail = 502, "no backend available"
	}
	writeJSON(w, lastCode, map[string]any{"error": map[string]any{
		"message": fmt.Sprintf("all backends failed for lane '%s': %s", lane, lastDetail)}})
}

// deliver writes the JSON response, or a fake-SSE stream (role chunk, one full-delta chunk,
// finish chunk) when the client asked for stream=true.
func (s *Shim) deliver(w http.ResponseWriter, resp map[string]any, wantStream bool) {
	if !wantStream {
		writeJSON(w, 200, resp)
		return
	}
	ch, msg := firstChoice(resp)
	base := map[string]any{"id": resp["id"], "object": "chat.completion.chunk", "created": resp["created"], "model": resp["model"]}
	if base["id"] == nil {
		base["id"] = "shim"
	}
	if base["created"] == nil {
		base["created"] = time.Now().Unix()
	}
	fin := "stop"
	if ch != nil && ch["finish_reason"] != nil {
		fin = str(ch["finish_reason"])
	}
	chunk := func(delta map[string]any, finish any, usage any) map[string]any {
		c := map[string]any{}
		for k, v := range base {
			c[k] = v
		}
		c["choices"] = []any{map[string]any{"index": 0, "delta": delta, "finish_reason": finish}}
		if usage != nil {
			c["usage"] = usage
		}
		return c
	}
	delta := map[string]any{}
	if msg != nil {
		if c := str(msg["content"]); c != "" {
			delta["content"] = c
		}
		if tcs, ok := msg["tool_calls"].([]any); ok && len(tcs) > 0 {
			out := make([]any, len(tcs))
			for i, t := range tcs {
				tc, _ := t.(map[string]any)
				fn, _ := tc["function"].(map[string]any)
				out[i] = map[string]any{"index": i, "id": tc["id"], "type": "function",
					"function": map[string]any{"name": fn["name"], "arguments": fn["arguments"]}}
			}
			delta["tool_calls"] = out
		}
	}
	payloads := []map[string]any{
		chunk(map[string]any{"role": "assistant"}, nil, nil),
		chunk(delta, nil, nil),
		chunk(map[string]any{}, fin, resp["usage"]),
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.WriteHeader(200)
	fl, _ := w.(http.Flusher)
	for _, p := range payloads {
		_, _ = io.WriteString(w, "data: "+marshal(p)+"\n\n")
	}
	_, _ = io.WriteString(w, "data: [DONE]\n\n")
	if fl != nil {
		fl.Flush()
	}
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_, _ = io.WriteString(w, marshal(v))
}
