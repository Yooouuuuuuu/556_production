package shim

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The shim has no built-in backend: until the app sets the chat connection every request is a 503 that
// names the setting, and the one lane always resolves to that connection (with its key on the wire).
func TestNoConnectionIsAnErrorNotAGuess(t *testing.T) {
	s := New(Config{Port: 0})
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("POST", "/v1/chat/completions", strings.NewReader(`{"model":"auto/556","messages":[{"role":"user","content":"hi"}]}`))
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != 503 || !strings.Contains(rec.Body.String(), "模型連線未設定") {
		t.Fatalf("want 503 naming the setting, got %d %s", rec.Code, rec.Body.String())
	}
	lane, chain := s.pickBackends("auto/556")
	if lane != "556" || len(chain) != 0 {
		t.Fatalf("unconfigured: %s %v", lane, chain)
	}
	var seenAuth, seenModel string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seenAuth = r.Header.Get("Authorization")
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		seenModel, _ = body["model"].(string)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"role":"assistant","content":"嗨"},"finish_reason":"stop"}]}`))
	}))
	defer up.Close()
	s.SetBackend(&Backend{BaseURL: up.URL + "/v1", Model: "m-1", APIKey: "secret"})
	rec = httptest.NewRecorder()
	req = httptest.NewRequest("POST", "/v1/chat/completions", strings.NewReader(`{"model":"auto/556","messages":[{"role":"user","content":"hi"}]}`))
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != 200 || seenAuth != "Bearer secret" || seenModel != "m-1" || !strings.Contains(rec.Body.String(), "嗨") {
		t.Fatalf("configured: %d auth=%q model=%q body=%s", rec.Code, seenAuth, seenModel, rec.Body.String())
	}
	rec = httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/models", nil))
	if !strings.Contains(rec.Body.String(), Lane) {
		t.Fatalf("models: %s", rec.Body.String())
	}
}
