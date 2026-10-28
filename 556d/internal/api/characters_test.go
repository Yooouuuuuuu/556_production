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
