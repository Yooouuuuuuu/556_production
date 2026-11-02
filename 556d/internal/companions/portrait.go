package companions

import (
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

// Her portrait — the picture in her circle (the roster column, the pane header, her 角色 page). Without one the
// app shows the first character of her name. It lives in her package (characters/<id>/portrait.<ext>): the package
// is the character; a profile that has no package keeps it in the profile folder. One file, png / jpeg / webp /
// gif, at most PortraitMax bytes; the URL carries the file's mtime, so a new upload is never served from cache.

const PortraitMax = 4 << 20

var portraitExts = []string{".png", ".jpg", ".jpeg", ".webp", ".gif"}
var portraitExtOf = map[string]string{"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}

// portraitDir is where her portrait lives: the package when there is one, else the profile.
func (m *Manager) portraitDir(name string) string {
	pkg := filepath.Join(m.root, "characters", name)
	if st, err := os.Stat(pkg); err == nil && st.IsDir() {
		return pkg
	}
	return m.Dir(name)
}

// findPortrait returns the portrait file in dir and its mtime, or "" when there is none.
func findPortrait(dir string) (string, time.Time) {
	for _, ext := range portraitExts {
		p := filepath.Join(dir, "portrait"+ext)
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			return p, st.ModTime()
		}
	}
	return "", time.Time{}
}

// savePortrait writes data as the one portrait in dir (an older one goes), after checking it is an image we serve.
func savePortrait(dir string, data []byte) (string, error) {
	if len(data) == 0 {
		return "", errors.New("empty file")
	}
	if len(data) > PortraitMax {
		return "", fmt.Errorf("too big: at most %d MB", PortraitMax>>20)
	}
	ext, ok := portraitExtOf[http.DetectContentType(data)]
	if !ok {
		return "", errors.New("not a png / jpeg / webp / gif image")
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	removePortrait(dir)
	p := filepath.Join(dir, "portrait"+ext)
	return p, os.WriteFile(p, data, 0o644)
}

// removePortrait deletes whatever portrait file dir has; returns how many went.
func removePortrait(dir string) int {
	n := 0
	for _, ext := range portraitExts {
		if os.Remove(filepath.Join(dir, "portrait"+ext)) == nil {
			n++
		}
	}
	return n
}

// PortraitPath is her portrait file and its mtime ("" when none).
func (m *Manager) PortraitPath(name string) (string, time.Time) { return findPortrait(m.portraitDir(name)) }

// PortraitURL is what the app puts in <img src>: the route plus the mtime, or "" when she has no portrait.
func (m *Manager) PortraitURL(name string) string {
	p, mt := m.PortraitPath(name)
	if p == "" {
		return ""
	}
	return fmt.Sprintf("/api/companions/%s/portrait?v=%d", name, mt.Unix())
}

// SavePortrait stores an uploaded image as her portrait; RemovePortrait takes it away (the circle shows her initial again).
func (m *Manager) SavePortrait(name string, data []byte) (string, error) {
	return savePortrait(m.portraitDir(name), data)
}

func (m *Manager) RemovePortrait(name string) int { return removePortrait(m.portraitDir(name)) }
