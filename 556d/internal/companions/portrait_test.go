package companions

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// The one portrait per character: an image we can serve replaces whatever was there, anything else is refused,
// and a removal leaves the circle to her initial.
func TestPortraitSaveReplaceRemove(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "pkg")
	png := append([]byte("\x89PNG\r\n\x1a\n"), bytes.Repeat([]byte{0}, 64)...)
	jpg := append([]byte("\xff\xd8\xff\xe0"), bytes.Repeat([]byte{0}, 64)...)

	if p, _ := findPortrait(dir); p != "" {
		t.Fatal("nothing yet")
	}
	p, err := savePortrait(dir, png)
	if err != nil || filepath.Base(p) != "portrait.png" {
		t.Fatalf("png: %v %s", err, p)
	}
	if q, mt := findPortrait(dir); q != p || mt.IsZero() {
		t.Fatalf("find after save: %s %v", q, mt)
	}
	p2, err := savePortrait(dir, jpg)
	if err != nil || filepath.Base(p2) != "portrait.jpg" {
		t.Fatalf("jpeg: %v %s", err, p2)
	}
	if _, err := os.Stat(p); !os.IsNotExist(err) {
		t.Fatal("the old png must be gone: one portrait per character")
	}
	if _, err := savePortrait(dir, []byte("just text, not an image")); err == nil || !strings.Contains(err.Error(), "image") {
		t.Fatalf("text must be refused: %v", err)
	}
	if _, err := savePortrait(dir, nil); err == nil {
		t.Fatal("empty must be refused")
	}
	if _, err := savePortrait(dir, bytes.Repeat([]byte{0}, PortraitMax+1)); err == nil || !strings.Contains(err.Error(), "too big") {
		t.Fatalf("oversize must be refused: %v", err)
	}
	if q, _ := findPortrait(dir); filepath.Base(q) != "portrait.jpg" {
		t.Fatal("a refused upload must not disturb the stored one")
	}
	if n := removePortrait(dir); n != 1 {
		t.Fatalf("remove: %d", n)
	}
	if q, _ := findPortrait(dir); q != "" {
		t.Fatal("gone after remove")
	}
}

// The package is the character: a character with a package keeps the portrait there; one without, in her profile.
func TestPortraitLivesInThePackageWhenThereIsOne(t *testing.T) {
	root := t.TempDir()
	m := &Manager{root: root, home: filepath.Join(root, "home")}
	_ = os.MkdirAll(filepath.Join(root, "characters", "a"), 0o755)
	_ = os.MkdirAll(m.Dir("b"), 0o755)
	if got := m.portraitDir("a"); got != filepath.Join(root, "characters", "a") {
		t.Fatalf("a: %s", got)
	}
	if got := m.portraitDir("b"); got != m.Dir("b") {
		t.Fatalf("b: %s", got)
	}
	if m.PortraitURL("a") != "" {
		t.Fatal("no portrait, no url")
	}
	if _, err := m.SavePortrait("a", append([]byte("\x89PNG\r\n\x1a\n"), bytes.Repeat([]byte{0}, 16)...)); err != nil {
		t.Fatal(err)
	}
	if u := m.PortraitURL("a"); !strings.HasPrefix(u, "/api/companions/a/portrait?v=") {
		t.Fatalf("url: %s", u)
	}
	if m.RemovePortrait("a") != 1 || m.PortraitURL("a") != "" {
		t.Fatal("remove through the manager")
	}
}
