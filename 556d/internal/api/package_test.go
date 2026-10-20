package api

import (
	"os"
	"path/filepath"
	"testing"
)

func TestTheProfileIsBuiltFromThePackage(t *testing.T) {
	root := t.TempDir()
	pkg := filepath.Join(root, "characters", "a")
	prof := filepath.Join(root, "home", "profiles", "a")
	for d := range map[string]bool{filepath.Join(pkg, "people"): true, filepath.Join(prof, "people"): true} {
		_ = os.MkdirAll(d, 0o755)
	}
	_ = os.WriteFile(filepath.Join(pkg, "SOUL.md"), []byte("# 角色甲\n新的"), 0o644)
	_ = os.WriteFile(filepath.Join(pkg, "psyche.json"), []byte(`{"character":{"pronoun":"她"}}`), 0o644)
	_ = os.WriteFile(filepath.Join(pkg, "people", "你.md"), []byte("skill's 你"), 0o644)
	_ = os.WriteFile(filepath.Join(pkg, "people", "b.md"), []byte("角色乙"), 0o644)
	_ = os.WriteFile(filepath.Join(prof, "SOUL.md"), []byte("# 角色甲\n舊的"), 0o644)
	_ = os.WriteFile(filepath.Join(prof, "people", "你.md"), []byte("settings-maintained 你"), 0o644)

	copied, err := syncProfileFromPackage(root, "a", prof)
	if err != nil {
		t.Fatal(err)
	}
	if len(copied) != 3 { // SOUL.md, psyche.json, b.md — not 你.md, which the profile already has
		t.Fatalf("copied %v", copied)
	}
	if b, _ := os.ReadFile(filepath.Join(prof, "SOUL.md")); string(b) != "# 角色甲\n新的" {
		t.Fatalf("SOUL not replaced: %q", b)
	}
	if b, _ := os.ReadFile(filepath.Join(prof, "people", "你.md")); string(b) != "settings-maintained 你" {
		t.Fatalf("你.md must stay the profile's: %q", b)
	}
	if b, _ := os.ReadFile(filepath.Join(prof, "people", "b.md")); string(b) != "角色乙" {
		t.Fatal("b.md not copied")
	}
	if again, _ := syncProfileFromPackage(root, "a", prof); len(again) != 0 {
		t.Fatalf("second run must copy nothing: %v", again)
	}
	if c, err := syncProfileFromPackage(root, "nobody", prof); c != nil || err != nil {
		t.Fatal("a profile without a package is left alone")
	}
}
