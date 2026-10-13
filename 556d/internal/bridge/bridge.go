// Package bridge is the avatar hub: a WebSocket fan-out to every open Live2D viewer/pet,
// the Artemis-compatible HTTP control API (/api/message, /api/motion, ...), audio caching
// for lip-sync, and static serving of the viewer, its libraries, models and the Cubism core.
// Port of ui/live2d/live2d-bridge.mjs minus GPT-SoVITS management (TTS slice later).
package bridge

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type Config struct {
	StaticDir  string `toml:"static_dir"`  // viewer html/js (ui/live2d)
	AssetsDir  string `toml:"assets_dir"`  // models (assets/live2d) served under /<model>/
	VendorDir  string `toml:"vendor_dir"`  // vendor/live2d (cubism core)
	AudioCache string `toml:"audio_cache"` // cached wav/mp3 for speak_audio
}

type Bridge struct {
	cfg     Config
	start   time.Time
	mu      sync.Mutex
	clients map[*websocket.Conn]struct{}
	up      websocket.Upgrader
}

func New(cfg Config) *Bridge {
	_ = os.MkdirAll(cfg.AudioCache, 0o755)
	return &Bridge{
		cfg:     cfg,
		start:   time.Now(),
		clients: map[*websocket.Conn]struct{}{},
		up:      websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }},
	}
}

// Broadcast sends one JSON event to every connected viewer.
func (b *Bridge) Broadcast(event map[string]any) {
	msg, _ := json.Marshal(event)
	b.mu.Lock()
	defer b.mu.Unlock()
	for c := range b.clients {
		if err := c.WriteMessage(websocket.TextMessage, msg); err != nil {
			c.Close()
			delete(b.clients, c)
		}
	}
}

func (b *Bridge) clientCount() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(b.clients)
}

// Register mounts every bridge route on mux.
func (b *Bridge) Register(mux *http.ServeMux) {
	mux.HandleFunc("/ws", b.ws)
	mux.HandleFunc("/api/status", b.api(func(q map[string]string) (any, map[string]any) {
		return map[string]any{"ok": true, "clients": b.clientCount(), "uptime": time.Since(b.start).Seconds()}, nil
	}))
	mux.HandleFunc("/api/expression", b.api(func(q map[string]string) (any, map[string]any) {
		name := or(q["name"], "neutral")
		return map[string]any{"ok": true, "type": "expression", "name": name}, map[string]any{"type": "expression", "name": name}
	}))
	mux.HandleFunc("/api/motion", b.api(func(q map[string]string) (any, map[string]any) {
		name := or(q["name"], "idle")
		return map[string]any{"ok": true, "type": "motion", "name": name}, map[string]any{"type": "motion", "name": name}
	}))
	mux.HandleFunc("/api/message", b.api(func(q map[string]string) (any, map[string]any) {
		dur, _ := strconv.Atoi(or(q["duration"], "5000"))
		return map[string]any{"ok": true, "type": "message", "text": q["text"], "duration": dur},
			map[string]any{"type": "message", "text": q["text"], "duration": dur}
	}))
	mux.HandleFunc("/api/speak", b.api(func(q map[string]string) (any, map[string]any) {
		action := or(q["action"], "start")
		ev := map[string]any{"type": "speak_end"}
		if action == "start" {
			ev = map[string]any{"type": "speak_start", "text": q["text"]}
		}
		return map[string]any{"ok": true, "type": "speak", "action": action}, ev
	}))
	mux.HandleFunc("/api/reset", b.api(func(q map[string]string) (any, map[string]any) {
		return map[string]any{"ok": true, "type": "reset"}, map[string]any{"type": "reset"}
	}))
	mux.HandleFunc("/api/emotion", func(w http.ResponseWriter, r *http.Request) {
		q := query(r)
		if q["expression"] != "" {
			b.Broadcast(map[string]any{"type": "expression", "name": q["expression"]})
		}
		if q["motion"] != "" {
			b.Broadcast(map[string]any{"type": "motion", "name": q["motion"]})
		}
		if q["text"] != "" {
			b.Broadcast(map[string]any{"type": "message", "text": q["text"]})
		}
		writeJSON(w, 200, map[string]any{"ok": true, "expression": q["expression"], "motion": q["motion"], "text": q["text"]})
	})
	mux.HandleFunc("/api/speak_audio", b.speakAudio)
	mux.HandleFunc("/api/sovits", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, 200, map[string]any{"ok": false, "running": false, "message": "TTS not built yet (0.2.x media slice)"})
	})
	mux.HandleFunc("/api/models", b.models)
	mux.HandleFunc("/api/switch-model", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, 501, map[string]any{"ok": false, "error": "model switching moves to the talent switcher (frontend rewrite)"})
	})
	mux.HandleFunc("/cache/audio/", b.serveAudio)
	mux.HandleFunc("/", b.static)
}

// api wraps a handler that returns (http response, optional broadcast event).
func (b *Bridge) api(fn func(q map[string]string) (any, map[string]any)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if cors(w, r) {
			return
		}
		resp, ev := fn(query(r))
		if ev != nil {
			b.Broadcast(ev)
		}
		writeJSON(w, 200, resp)
	}
}

func (b *Bridge) ws(w http.ResponseWriter, r *http.Request) {
	c, err := b.up.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	b.mu.Lock()
	b.clients[c] = struct{}{}
	n := len(b.clients)
	b.mu.Unlock()
	log.Printf("[bridge] viewer connected (%d)", n)
	defer func() {
		b.mu.Lock()
		delete(b.clients, c)
		n := len(b.clients)
		b.mu.Unlock()
		c.Close()
		log.Printf("[bridge] viewer disconnected (%d)", n)
	}()
	for {
		_, msg, err := c.ReadMessage()
		if err != nil {
			return
		}
		var ev map[string]any
		if json.Unmarshal(msg, &ev) == nil {
			log.Printf("[bridge] viewer event: %v", ev["type"])
		}
	}
}

var audioNameRE = regexp.MustCompile(`^[a-f0-9-]+\.(wav|mp3|ogg|webm)$`)

func (b *Bridge) speakAudio(w http.ResponseWriter, r *http.Request) {
	if cors(w, r) {
		return
	}
	q := query(r)
	if or(q["action"], "start") != "start" {
		b.Broadcast(map[string]any{"type": "speak_audio", "action": "end"})
		writeJSON(w, 200, map[string]any{"ok": true})
		return
	}
	audioURL := ""
	if q["audio_path"] != "" {
		name, err := b.cacheAudio(q["audio_path"])
		if err != nil {
			writeJSON(w, 500, map[string]any{"ok": false, "error": err.Error()})
			return
		}
		audioURL = "/cache/audio/" + name
	}
	full := ""
	if audioURL != "" {
		full = "http://" + r.Host + audioURL
	}
	b.Broadcast(map[string]any{"type": "speak_audio", "action": "start", "audio_url": full, "text": q["text"]})
	writeJSON(w, 200, map[string]any{"ok": true, "audio_url": audioURL})
}

// cacheAudio copies a local audio file into the cache under a random name and prunes old
// entries (max 50 files / 30 minutes), like the Node bridge.
func (b *Bridge) cacheAudio(src string) (string, error) {
	in, err := os.Open(src)
	if err != nil {
		return "", err
	}
	defer in.Close()
	buf := make([]byte, 16)
	_, _ = rand.Read(buf)
	name := hex.EncodeToString(buf) + strings.ToLower(filepath.Ext(src))
	out, err := os.Create(filepath.Join(b.cfg.AudioCache, name))
	if err != nil {
		return "", err
	}
	defer out.Close()
	if _, err := io.Copy(out, in); err != nil {
		return "", err
	}
	b.pruneAudio()
	return name, nil
}

func (b *Bridge) pruneAudio() {
	entries, err := os.ReadDir(b.cfg.AudioCache)
	if err != nil {
		return
	}
	type f struct {
		name string
		mod  time.Time
	}
	var files []f
	for _, e := range entries {
		if info, err := e.Info(); err == nil && !e.IsDir() {
			files = append(files, f{e.Name(), info.ModTime()})
		}
	}
	sort.Slice(files, func(i, j int) bool { return files[i].mod.Before(files[j].mod) })
	now := time.Now()
	var keep []f
	for _, x := range files {
		if now.Sub(x.mod) > 30*time.Minute {
			_ = os.Remove(filepath.Join(b.cfg.AudioCache, x.name))
		} else {
			keep = append(keep, x)
		}
	}
	for len(keep) > 50 {
		_ = os.Remove(filepath.Join(b.cfg.AudioCache, keep[0].name))
		keep = keep[1:]
	}
}

func (b *Bridge) serveAudio(w http.ResponseWriter, r *http.Request) {
	name := strings.TrimPrefix(r.URL.Path, "/cache/audio/")
	if !audioNameRE.MatchString(name) {
		http.Error(w, "Forbidden", 403)
		return
	}
	http.ServeFile(w, r, filepath.Join(b.cfg.AudioCache, name))
}

// models lists every model3.json under assets_dir, keyed by its top-level folder.
func (b *Bridge) models(w http.ResponseWriter, r *http.Request) {
	if cors(w, r) {
		return
	}
	var models []map[string]any
	entries, _ := os.ReadDir(b.cfg.AssetsDir)
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		var found []string
		_ = filepath.WalkDir(filepath.Join(b.cfg.AssetsDir, e.Name()), func(p string, d os.DirEntry, err error) error {
			if err == nil && !d.IsDir() && strings.HasSuffix(p, ".model3.json") {
				rel, _ := filepath.Rel(b.cfg.AssetsDir, p)
				found = append(found, filepath.ToSlash(rel))
			}
			return nil
		})
		models = append(models, map[string]any{"name": e.Name(), "models": found})
	}
	writeJSON(w, 200, map[string]any{"ok": true, "models": models})
}

// static resolves, in order: node_modules aliases, the cubism core from vendor/, model
// folders from assets/, then files from the viewer directory.
func (b *Bridge) static(w http.ResponseWriter, r *http.Request) {
	if cors(w, r) {
		return
	}
	p := r.URL.Path
	switch {
	case p == "/favicon.ico":
		w.WriteHeader(204)
		return
	case p == "/pixi.min.js":
		serveFile(w, r, filepath.Join(b.cfg.StaticDir, "node_modules", "pixi.js", "dist", "pixi.min.js"), true)
		return
	case p == "/live2dcubismcore.min.js":
		serveFile(w, r, filepath.Join(b.cfg.VendorDir, "live2dcubismcore.min.js"), true)
		return
	}
	if p == "/" {
		p = "/index.html"
	}
	clean := filepath.Clean(filepath.FromSlash(p))
	// model folders live in assets/: /<folder>/... where <folder> exists there
	if parts := strings.SplitN(strings.TrimPrefix(p, "/"), "/", 2); len(parts) == 2 {
		if st, err := os.Stat(filepath.Join(b.cfg.AssetsDir, parts[0])); err == nil && st.IsDir() {
			serveUnder(w, r, b.cfg.AssetsDir, clean)
			return
		}
	}
	serveUnder(w, r, b.cfg.StaticDir, clean)
}

func serveUnder(w http.ResponseWriter, r *http.Request, root, clean string) {
	full := filepath.Join(root, clean)
	absRoot, _ := filepath.Abs(root)
	absFull, _ := filepath.Abs(full)
	if absFull != absRoot && !strings.HasPrefix(absFull, absRoot+string(filepath.Separator)) {
		http.Error(w, "Forbidden", 403)
		return
	}
	serveFile(w, r, full, false)
}

// serveFile streams a file without http.ServeFile's index.html→"./" redirect (the viewer,
// pet and avatar launchers address /index.html directly).
func serveFile(w http.ResponseWriter, r *http.Request, path string, cacheable bool) {
	st, err := os.Stat(path)
	if err != nil || st.IsDir() {
		http.NotFound(w, r)
		return
	}
	f, err := os.Open(path)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	if cacheable {
		w.Header().Set("Cache-Control", "public, max-age=3600")
	} else {
		w.Header().Set("Cache-Control", "no-store")
	}
	http.ServeContent(w, r, filepath.Base(path), st.ModTime(), f)
}

func cors(w http.ResponseWriter, r *http.Request) bool {
	h := w.Header()
	h.Set("Access-Control-Allow-Origin", "*")
	h.Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	h.Set("Access-Control-Allow-Headers", "Content-Type")
	if r.Method == http.MethodOptions {
		w.WriteHeader(204)
		return true
	}
	return false
}

func query(r *http.Request) map[string]string {
	out := map[string]string{}
	for k, v := range r.URL.Query() {
		if len(v) > 0 {
			out[k] = v[0]
		}
	}
	return out
}

func or(a, b string) string {
	if a != "" {
		return a
	}
	return b
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

var _ = fmt.Sprintf
