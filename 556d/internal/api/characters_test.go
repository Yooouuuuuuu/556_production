package api

import (
	"os"
	"path/filepath"
	"testing"
)

// templates/life/*.json are the sample days the new-character page offers; each is served with its file stem as id,
// in file-name order, and a file that is not a JSON object is skipped. No folder is an empty list, never null.
func TestLoadLifeSamples(t *testing.T) {
	if got := loadLifeSamples(filepath.Join(t.TempDir(), "none")); got == nil || len(got) != 0 {
		t.Fatalf("missing folder must be an empty list: %#v", got)
	}
	dir := t.TempDir()
	_ = os.WriteFile(filepath.Join(dir, "b.json"), []byte(`{"name":"乙","schedule":{"wake":9}}`), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "a.json"), []byte(`{"name":"甲","projects":[]}`), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "bad.json"), []byte(`[1,2]`), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "notes.txt"), []byte(`x`), 0o644)
	got := loadLifeSamples(dir)
	if len(got) != 2 || got[0]["id"] != "a" || got[0]["name"] != "甲" || got[1]["id"] != "b" {
		t.Fatalf("samples: %#v", got)
	}
	if got[1]["schedule"].(map[string]any)["wake"] != 9.0 {
		t.Fatalf("sample content lost: %#v", got[1])
	}
}

// A change to one part of profile.json names the first phase that reads it, not the whole skill: her day → assemble,
// the thinking numbers → parts; an untouched profile is not stale.
func TestStaleInputsNamesTheProfileSection(t *testing.T) {
	dir := t.TempDir()
	_ = os.MkdirAll(filepath.Join(dir, "describe"), 0o755)
	_ = os.WriteFile(filepath.Join(dir, "describe", "01.md"), []byte("x"), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "profile.json"), []byte(`{"life":null,"thinking":{"rationality":0.3},"proposed":{"a":1}}`), 0o644)
	lock := `{"inputs":{"describe/01.md":"` + shortSHA(filepath.Join(dir, "describe", "01.md")) + `"},
	  "profile_sections":{"parts":{"thinking":{"rationality":0.3},"big5":null},"assemble":{"life":null,"closeness":null}}}`
	_ = os.WriteFile(filepath.Join(dir, "soul.lock.json"), []byte(lock), 0o644)
	if got := staleInputs(dir); len(got) != 0 {
		t.Fatalf("untouched: %v", got)
	}
	_ = os.WriteFile(filepath.Join(dir, "profile.json"), []byte(`{"life":{"schedule":{"wake":5}},"thinking":{"rationality":0.3},"proposed":{"a":2}}`), 0o644)
	if got := staleInputs(dir); len(got) != 1 || got[0] != "profile.json:assemble" {
		t.Fatalf("her day changed: %v", got)
	}
	_ = os.WriteFile(filepath.Join(dir, "profile.json"), []byte(`{"life":null,"thinking":{"rationality":0.9}}`), 0o644)
	if got := staleInputs(dir); len(got) != 1 || got[0] != "profile.json:parts" {
		t.Fatalf("thinking changed: %v", got)
	}
}
