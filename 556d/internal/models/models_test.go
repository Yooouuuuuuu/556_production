package models

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"context"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func full() Config {
	return Config{
		Master:   Endpoint{BaseURL: "http://127.0.0.1:1234/v1/", Model: "vendor/model-a", APIKey: "k1"},
		Chat:     Use{Use: UseMaster},
		Memory:   Use{Use: UseMaster},
		Soul:     Use{Use: UseCustom, Endpoint: Endpoint{BaseURL: "http://x/v1", Model: "m2", APIKey: "k2"}},
		Embedder: Embedder{Kind: EmbedLlama, Exe: "bin/llama/llama-server.exe", File: "models/bge-m3-Q8_0.gguf", Port: 55602, Model: "bge-m3", Dims: 1024},
		Timezone: "Asia/Taipei",
	}
}

func TestNothingIsAssumed(t *testing.T) {
	var empty Config
	m := empty.Missing()
	if len(m) == 0 || !strings.Contains(strings.Join(m, " "), "主設定：網址") || !strings.Contains(strings.Join(m, " "), "向量：方式") || !strings.Contains(strings.Join(m, " "), "時區") {
		t.Fatalf("an empty config must name everything that is missing: %v", m)
	}
	c := full()
	if m := c.Missing(); len(m) != 0 {
		t.Fatalf("full config reported missing: %v", m)
	}
	if b, _ := json.Marshal(c.Missing()); string(b) != "[]" {
		t.Fatalf("an empty missing list must serialize as [], not null: %s", b)
	}
	c.Timezone = "Mars/Olympus"
	if m := c.Missing(); len(m) != 1 || !strings.Contains(m[0], "時區") {
		t.Fatalf("bad zone must be reported: %v", m)
	}
	c = full()
	c.Soul.Use = UseMaster
	c.Master.Model = ""
	if m := c.Missing(); len(m) != 1 || m[0] != "主設定：模型" {
		t.Fatalf("missing master model: %v", m)
	}
}

func TestResolveMergeAndMask(t *testing.T) {
	c := full()
	if c.Resolve("chat").Model != "vendor/model-a" || c.Resolve("soul").Model != "m2" {
		t.Fatal("resolve")
	}
	if c.Resolve("chat").BaseURL != "http://127.0.0.1:1234/v1/" { // not normalized until Save/Merge
		t.Fatal("raw base url")
	}
	// the UI sends no keys back: Merge keeps the stored ones and trims
	next := full()
	next.Master.APIKey, next.Soul.APIKey = "", ""
	next.Master.Model = " new-model "
	got := Merge(c, next)
	if got.Master.APIKey != "k1" || got.Soul.APIKey != "k2" || got.Master.Model != "new-model" || got.Master.BaseURL != "http://127.0.0.1:1234/v1" {
		t.Fatalf("merge: %+v", got)
	}
	m := got.Masked()
	b, _ := json.Marshal(m)
	if strings.Contains(string(b), "k1") || strings.Contains(string(b), "k2") || !strings.Contains(string(b), `"api_key_set":true`) {
		t.Fatalf("masked leaks or lacks the flag: %s", b)
	}
	if got.Embedder.URL() != "http://127.0.0.1:55602/v1" {
		t.Fatal("llama url")
	}
	off, err := OffsetHours("Asia/Taipei", time.Now())
	if err != nil || off != 8 {
		t.Fatalf("offset: %v %v", off, err)
	}
}

func TestLoadSaveRoundTrip(t *testing.T) {
	p := filepath.Join(t.TempDir(), "models.json")
	if _, exists, err := Load(p); exists || err != nil {
		t.Fatal("a missing file is 'not configured', not an error")
	}
	if err := Save(p, full()); err != nil {
		t.Fatal(err)
	}
	c, exists, err := Load(p)
	if !exists || err != nil || c.Master.APIKey != "k1" || c.Embedder.Port != 55602 || !c.Ready() {
		t.Fatalf("round trip: %v %v %+v", exists, err, c)
	}
}

func TestProbeListsModels(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/models" || r.Header.Get("Authorization") != "Bearer k" {
			w.WriteHeader(404)
			return
		}
		_, _ = w.Write([]byte(`{"object":"list","data":[{"id":"b"},{"id":"a"}]}`))
	}))
	defer srv.Close()
	ids, err := Probe(context.Background(), Endpoint{BaseURL: srv.URL + "/v1/", APIKey: "k"})
	if err != nil || strings.Join(ids, ",") != "a,b" {
		t.Fatalf("probe: %v %v", ids, err)
	}
	if _, err := Probe(context.Background(), Endpoint{BaseURL: srv.URL + "/nope"}); err == nil {
		t.Fatal("a 404 must be an error")
	}
}
