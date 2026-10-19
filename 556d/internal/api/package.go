package api

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
)

// The character package (characters/<id>/) is the character; her profile (home/profiles/<id>/) is built from
// it (DECISIONS 2026-10-19). Before every start 556d copies the authored files over — SOUL.md, psyche.json,
// people/*.md — so an edit in the package wins and a profile can be rebuilt from nothing. people/你.md is copied
// only when the profile has none: Settings maintains it afterwards (your name, reply language). A profile without
// a package (a hand-made one) is left alone. Backing a character up = the package + memory/<id>.db + psyche.db +
// state.db (what she remembers, how she feels, what was said).
func syncProfileFromPackage(root, name, dir string) ([]string, error) {
	pkg := filepath.Join(root, "characters", name)
	if st, err := os.Stat(filepath.Join(pkg, "SOUL.md")); err != nil || st.IsDir() {
		return nil, nil
	}
	var copied []string
	copyIf := func(src, dst string, onlyIfMissing bool) error {
		b, err := os.ReadFile(src)
		if err != nil {
			if os.IsNotExist(err) {
				return nil
			}
			return err
		}
		if cur, err := os.ReadFile(dst); err == nil {
			if onlyIfMissing || bytes.Equal(cur, b) {
				return nil
			}
		}
		if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(dst, b, 0o644); err != nil {
			return err
		}
		copied = append(copied, filepath.Base(dst))
		return nil
	}
	for _, f := range []string{"SOUL.md", "psyche.json"} {
		if err := copyIf(filepath.Join(pkg, f), filepath.Join(dir, f), false); err != nil {
			return copied, err
		}
	}
	entries, _ := os.ReadDir(filepath.Join(pkg, "people"))
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".md") {
			continue
		}
		if err := copyIf(filepath.Join(pkg, "people", e.Name()), filepath.Join(dir, "people", e.Name()), e.Name() == "你.md"); err != nil {
			return copied, err
		}
	}
	return copied, nil
}

// packageFile is a file of the character's package, "" when she has no package.
func (a *API) packageFile(name, rel string) string {
	p := filepath.Join(a.mgr.Root(), "characters", name, rel)
	if _, err := os.Stat(filepath.Join(a.mgr.Root(), "characters", name, "SOUL.md")); err != nil {
		return ""
	}
	return p
}
