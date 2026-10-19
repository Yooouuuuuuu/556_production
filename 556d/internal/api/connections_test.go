package api

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Yooouuuuuuu/556_production/556d/internal/models"
)

func TestWriteProfileConfigPinsHerToTheShim(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.yaml")
	// what `hermes profile create` leaves behind on a fresh machine: some other provider, no plugins, no toolsets
	_ = os.WriteFile(p, []byte("model:\n  provider: openai\n  default: gpt-4o\nagent: {}\n"), 0o644)
	if err := writeProfileConfig(p, 55601); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(p)
	s := string(b)
	for _, want := range []string{"provider: custom", "base_url: http://127.0.0.1:55601/v1", "default: auto/556",
		"provider: kokoro", "memory_enabled: false", "user_profile_enabled: false", "psyche", "api_server: []", "telegram: []", "cli: []"} {
		if !strings.Contains(s, want) {
			t.Fatalf("missing %q in\n%s", want, s)
		}
	}
	if strings.Contains(s, "gpt-4o") || strings.Contains(s, "provider: openai") {
		t.Fatalf("the foreign provider survived:\n%s", s)
	}
	// idempotent: a second run changes nothing
	before, _ := os.Stat(p)
	if err := writeProfileConfig(p, 55601); err != nil {
		t.Fatal(err)
	}
	after, _ := os.Stat(p)
	if !before.ModTime().Equal(after.ModTime()) {
		t.Fatal("rewrote an unchanged file")
	}
}

func TestWriteKokoroAndPsycheFromConnections(t *testing.T) {
	dir := t.TempDir()
	kp := filepath.Join(dir, "kokoro.json")
	_ = os.WriteFile(kp, []byte(`{"subject":"你","llm":{"timeout":120},"embedder":{"base_url":"http://old/v1","model":"old"}}`), 0o644)
	err := writeKokoroConnections(kp, models.Endpoint{BaseURL: "http://127.0.0.1:18765/v1", Model: "m", APIKey: "k"},
		models.Embedder{Kind: models.EmbedLlama, Port: 55602, Model: "bge-m3", Dims: 1024})
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]any
	b, _ := os.ReadFile(kp)
	_ = json.Unmarshal(b, &m)
	llm := m["llm"].(map[string]any)
	emb := m["embedder"].(map[string]any)
	if llm["base_url"] != "http://127.0.0.1:18765/v1" || llm["model"] != "m" || llm["api_key"] != "k" || llm["timeout"] != 120.0 {
		t.Fatalf("llm: %v", llm)
	}
	if emb["base_url"] != "http://127.0.0.1:55602/v1" || emb["model"] != "bge-m3" || emb["dims"] != 1024.0 || emb["api_key"] != nil {
		t.Fatalf("embedder: %v", emb)
	}
	if m["subject"] != "你" {
		t.Fatal("the rest of the file must survive")
	}
	pp := filepath.Join(dir, "psyche.json")
	_ = os.WriteFile(pp, []byte(`{"character":{"pronoun":"她"},"time":{"timezone_offset_h":0}}`), 0o644)
	if err := writePsycheZone(pp, "Asia/Taipei"); err != nil {
		t.Fatal(err)
	}
	b, _ = os.ReadFile(pp)
	_ = json.Unmarshal(b, &m)
	if m["time"].(map[string]any)["timezone_offset_h"] != 8.0 || m["character"].(map[string]any)["pronoun"] != "她" {
		t.Fatalf("psyche: %v", m)
	}
	if err := writePsycheZone(filepath.Join(dir, "none.json"), "Asia/Taipei"); err != nil {
		t.Fatal("a profile without psyche.json is fine")
	}
}
