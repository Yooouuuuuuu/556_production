// Package companions is the roster: every Hermes profile under home/profiles/<name> is a
// character. Nothing starts by itself — the Producer starts and stops each one from the app
// (several can be active at once; closing the app stops all through the job object).
//
// ONE process per character: her `hermes gateway run`. It carries her channel adapters
// (Telegram / Discord when her .env holds tokens) AND Hermes's OpenAI-compatible API server,
// which is how the app talks to her — the app is one more client of her, same level as
// Telegram. Her memory (kokoro → KeepsakeDB) lives inside that process, single owner.
package companions

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/Yooouuuuuuu/556_production/556d/internal/hermesapi"
	"github.com/Yooouuuuuuu/556_production/556d/internal/supervisor"
)

type Info struct {
	Name            string   `json:"name"`         // profile directory name, e.g. "mane"
	DisplayName     string   `json:"display_name"` // companion.json display_name, else the name
	AvatarModel     string   `json:"avatar_model"` // path under assets/live2d
	Active          bool     `json:"active"`
	HermesConnected bool     `json:"hermes_connected"` // her API server answers /health
	Stopping        bool     `json:"stopping"`         // asked to finish up; gone when the process exits
	APIPort         int      `json:"api_port"`
	Channels        []string `json:"channels"` // detected from .env: telegram, discord
	Gateway         bool     `json:"gateway"`  // true whenever active: her gateway IS her process
	Dir             string   `json:"dir"`
}

// stopGrace is how long a companion may take to finish up (drain her turn, land the memory
// observe — kokoro waits for an in-flight one) before the supervisor kills her.
const stopGrace = 60 * time.Second

type live struct {
	cancel     context.CancelFunc
	finished   <-chan struct{} // closed when her process is gone for good
	stopping   bool
	startedAt  time.Time
	client     *hermesapi.Client
	port       int
	mu         sync.Mutex
	healthy    bool
	healthedAt time.Time
}

type Manager struct {
	parent    context.Context
	home      string
	hermesExe string
	root      string
	sup       *supervisor.Supervisor
	mu        sync.Mutex
	live      map[string]*live
}

func New(parent context.Context, home, hermesExe, root string, sup *supervisor.Supervisor) *Manager {
	return &Manager{parent: parent, home: home, hermesExe: hermesExe, root: root, sup: sup, live: map[string]*live{}}
}

func (m *Manager) profilesDir() string { return filepath.Join(m.home, "profiles") }

// Dir is a companion's HERMES_HOME.
func (m *Manager) Dir(name string) string { return filepath.Join(m.profilesDir(), name) }

func (m *Manager) Exists(name string) bool {
	if name == "" || strings.ContainsAny(name, `/\.`) {
		return false
	}
	st, err := os.Stat(filepath.Join(m.Dir(name), "config.yaml"))
	return err == nil && !st.IsDir()
}

// List scans home/profiles/*. A directory is a companion when it has a config.yaml and is not
// tombstoned (Hermes marks deleted profiles with a .deleted file).
func (m *Manager) List() []Info {
	entries, _ := os.ReadDir(m.profilesDir())
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if !e.IsDir() || strings.HasPrefix(e.Name(), ".") || !m.Exists(e.Name()) {
			continue
		}
		if _, err := os.Stat(filepath.Join(m.Dir(e.Name()), ".deleted")); err == nil {
			continue
		}
		names = append(names, e.Name())
	}
	sort.Strings(names)
	out := make([]Info, 0, len(names))
	for _, n := range names {
		out = append(out, m.Info(n))
	}
	return out
}

func (m *Manager) Info(name string) Info {
	dir := m.Dir(name)
	cj := ReadCompanionJSON(dir)
	display, _ := cj["display_name"].(string)
	avatar, _ := cj["avatar_model"].(string)
	if display == "" {
		display = name
	}
	if avatar == "" {
		avatar = "hiyori/Hiyori.model3.json"
	}
	info := Info{Name: name, DisplayName: display, AvatarModel: avatar, Channels: DetectChannels(dir), Dir: dir}
	m.mu.Lock()
	l := m.live[name]
	m.mu.Unlock()
	if l != nil {
		info.Active, info.Gateway, info.APIPort, info.Stopping = true, true, l.port, l.stopping
		info.HermesConnected = !l.stopping && l.health()
	}
	return info
}

// health probes her API server at most every 2 s (the roster polls often).
func (l *live) health() bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	if time.Since(l.healthedAt) < 2*time.Second {
		return l.healthy
	}
	l.healthy, l.healthedAt = l.client.Healthy(), time.Now()
	return l.healthy
}

// Start brings a companion up: her gateway with the API server enabled (+ her channel adapters
// when her .env holds tokens). The API key is hers, generated once into companion.json; the
// port is free at start and passed through the environment. Her .env can override both.
func (m *Manager) Start(name string) (Info, error) {
	if !m.Exists(name) {
		return Info{}, fmt.Errorf("no companion %q under %s", name, m.profilesDir())
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if l := m.live[name]; l != nil {
		if l.stopping {
			return Info{}, fmt.Errorf("%s is still finishing up; try again in a moment", name)
		}
		return m.infoLocked(name), nil
	}
	dir := m.Dir(name)
	env := readEnv(dir)
	key := env["API_SERVER_KEY"]
	if key == "" {
		cj := ReadCompanionJSON(dir)
		key, _ = cj["api_key"].(string)
		if len(key) < 16 {
			b := make([]byte, 24)
			_, _ = rand.Read(b)
			key = hex.EncodeToString(b)
			cj["api_key"] = key
			if err := WriteCompanionJSON(dir, cj); err != nil {
				return Info{}, fmt.Errorf("companion.json: %w", err)
			}
		}
	}
	port := 0
	if p, err := parsePort(env["API_SERVER_PORT"]); err == nil && p > 0 {
		port = p
	} else {
		fp, err := freePort()
		if err != nil {
			return Info{}, err
		}
		port = fp
	}
	ctx, cancel := context.WithCancel(m.parent)
	startedAt := time.Now()
	finished := m.sup.Run(ctx, supervisor.Spec{
		Name: "gateway:" + name,
		Exe:  m.hermesExe,
		Args: []string{"gateway", "run"},
		Env: []string{
			"HERMES_HOME=" + dir,
			"HERMES_DESKTOP=1",
			"API_SERVER_KEY=" + key, // enables Hermes's API server platform (gateway/config_env.py)
			"API_SERVER_HOST=127.0.0.1",
			"API_SERVER_PORT=" + fmt.Sprint(port),
		},
		Dir:    m.root,
		Health: fmt.Sprintf("http://127.0.0.1:%d/health", port),
		Stop:   func(cmd *exec.Cmd) bool { return writePlannedStop(dir, startedAt) },
		Grace:  stopGrace,
	})
	l := &live{cancel: cancel, finished: finished, startedAt: startedAt, client: hermesapi.New(fmt.Sprintf("http://127.0.0.1:%d", port), key), port: port}
	m.live[name] = l
	ch := DetectChannels(dir)
	log.Printf("[companions] %s started: gateway with API server :%d%s", name, port,
		map[bool]string{true: " + " + strings.Join(ch, ", "), false: ""}[len(ch) > 0])
	return m.infoLocked(name), nil
}

// Stop asks her to finish up (her in-flight memory write lands) and returns once her process
// is gone — normally a few seconds, at most the grace period plus the kill.
func (m *Manager) Stop(name string) error {
	m.mu.Lock()
	l := m.live[name]
	if l == nil {
		m.mu.Unlock()
		return fmt.Errorf("%s is not active", name)
	}
	if l.stopping {
		m.mu.Unlock()
		return fmt.Errorf("%s is already finishing up", name)
	}
	l.stopping = true
	m.mu.Unlock()
	m.awaitMemoryIdle(name, memoryIdleWait)
	l.cancel()
	m.awaitExit(name, l)
	return nil
}

func (m *Manager) awaitExit(name string, l *live) {
	t0 := time.Now()
	select {
	case <-l.finished:
	case <-time.After(stopGrace + 15*time.Second):
		log.Printf("[companions] %s: gave up waiting for her process", name)
	}
	m.mu.Lock()
	if m.live[name] == l {
		delete(m.live, name)
	}
	m.mu.Unlock()
	log.Printf("[companions] %s stopped (%.1fs)", name, time.Since(t0).Seconds())
}

// StopAll stops every active companion concurrently and returns when all are gone.
func (m *Manager) StopAll() {
	m.mu.Lock()
	var wg sync.WaitGroup
	for name, l := range m.live {
		if l.stopping {
			continue
		}
		l.stopping = true
		wg.Add(1)
		go func(name string, l *live) {
			defer wg.Done()
			m.awaitMemoryIdle(name, memoryIdleWait)
			l.cancel()
			m.awaitExit(name, l)
		}(name, l)
	}
	m.mu.Unlock()
	wg.Wait()
}

// memoryIdleWait bounds how long a stop waits for the memory pipeline to observe the last turn.
const memoryIdleWait = 30 * time.Second

// awaitMemoryIdle holds the stop until kokoro has observed the newest turn. Hermes queues the
// observe a few seconds after the reply; a stop in that window would kill the process before the
// write — kokoro's own shutdown wait only covers an observe already running. Compares the newest
// user message in her session store with the newest pipeline_log entry in her memory store
// (both read-only); no store yet, or no turn, means nothing to wait for.
func (m *Manager) awaitMemoryIdle(name string, max time.Duration) {
	dir := m.Dir(name)
	deadline := time.Now().Add(max)
	for {
		lastTurn := lastUserMessageAt(filepath.Join(dir, "state.db"))
		if lastTurn == 0 {
			return
		}
		if lastObserve(filepath.Join(dir, "memory", name+".db")) >= lastTurn {
			return
		}
		if time.Now().After(deadline) {
			log.Printf("[companions] %s: memory pipeline still busy after %s; stopping anyway", name, max)
			return
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func lastUserMessageAt(stateDB string) float64 {
	return scalarFloat(stateDB, "SELECT COALESCE(MAX(timestamp), 0) FROM messages WHERE role = 'user'")
}

func lastObserve(memoryDB string) float64 {
	return scalarFloat(memoryDB, "SELECT COALESCE(MAX(at), 0) FROM pipeline_log")
}

func scalarFloat(path, q string) float64 {
	if _, err := os.Stat(path); err != nil {
		return 0
	}
	db, err := (&Transcript{path: path}).open(true)
	if err != nil {
		return 0
	}
	defer db.Close()
	var v float64
	if err := db.QueryRow(q).Scan(&v); err != nil {
		return 0
	}
	return v
}

// writePlannedStop writes Hermes's planned-stop marker into her HERMES_HOME; the gateway's
// watcher (0.5 s poll) then drains and exits 0: in-flight turns finish, kokoro waits for its
// observe. The target must be her Python process — gateway.pid, written by the gateway itself —
// not the hermes.exe launcher we spawned; a record older than this start is stale (false = kill now).
func writePlannedStop(dir string, startedAt time.Time) bool {
	raw, err := os.ReadFile(filepath.Join(dir, "gateway.pid"))
	if err != nil {
		return false
	}
	var rec struct {
		Pid       int    `json:"pid"`
		Kind      string `json:"kind"`
		StartTime *int64 `json:"start_time"` // psutil create_time in centiseconds
	}
	if json.Unmarshal(raw, &rec) != nil || rec.Pid <= 0 || rec.Kind != "hermes-gateway" {
		return false
	}
	if rec.StartTime != nil && time.Unix(*rec.StartTime/100, 0).Before(startedAt.Add(-10*time.Second)) {
		return false // a previous life's record
	}
	marker := map[string]any{"target_pid": rec.Pid, "target_start_time": rec.StartTime, "stopper_pid": os.Getpid(),
		"written_at": time.Now().UTC().Format("2006-01-02T15:04:05.000000+00:00")}
	out, _ := json.Marshal(marker)
	p := filepath.Join(dir, ".gateway-planned-stop.json")
	if err := os.WriteFile(p+".tmp", out, 0o600); err != nil {
		return false
	}
	if err := os.Rename(p+".tmp", p); err != nil {
		_ = os.Remove(p + ".tmp")
		return false
	}
	return true
}

// Client returns the API client of an active companion (nil when she is off duty).
func (m *Manager) Client(name string) *hermesapi.Client {
	m.mu.Lock()
	defer m.mu.Unlock()
	if l := m.live[name]; l != nil {
		return l.client
	}
	return nil
}

func (m *Manager) infoLocked(name string) Info {
	dir := m.Dir(name)
	cj := ReadCompanionJSON(dir)
	display, _ := cj["display_name"].(string)
	avatar, _ := cj["avatar_model"].(string)
	if display == "" {
		display = name
	}
	if avatar == "" {
		avatar = "hiyori/Hiyori.model3.json"
	}
	info := Info{Name: name, DisplayName: display, AvatarModel: avatar, Channels: DetectChannels(dir), Dir: dir}
	if l := m.live[name]; l != nil {
		info.Active, info.Gateway, info.APIPort, info.Stopping = true, true, l.port, l.stopping
		info.HermesConnected = !l.stopping && l.health()
	}
	return info
}

// ReadCompanionJSON reads <dir>/companion.json as a map (display_name, avatar_model, api_key,
// app_session_id, …); empty map when absent.
func ReadCompanionJSON(dir string) map[string]any {
	m := map[string]any{}
	if raw, err := os.ReadFile(filepath.Join(dir, "companion.json")); err == nil {
		_ = json.Unmarshal(raw, &m)
	}
	return m
}

// WriteCompanionJSON writes the whole map back.
func WriteCompanionJSON(dir string, m map[string]any) error {
	out, _ := json.MarshalIndent(m, "", "  ")
	return os.WriteFile(filepath.Join(dir, "companion.json"), out, 0o600)
}

// SetCompanionField updates one key in companion.json.
func SetCompanionField(dir, key string, value any) error {
	m := ReadCompanionJSON(dir)
	m[key] = value
	return WriteCompanionJSON(dir, m)
}

// readEnv parses the profile's .env (KEY=VALUE, quotes stripped). Values never leave 556d.
func readEnv(dir string) map[string]string {
	out := map[string]string{}
	f, err := os.Open(filepath.Join(dir, ".env"))
	if err != nil {
		return out
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		out[strings.TrimSpace(k)] = strings.Trim(strings.TrimSpace(v), `"'`)
	}
	return out
}

// Env exposes selected .env values to 556d itself (the Telegram mirror needs her token and chat).
func (m *Manager) Env(name string) map[string]string { return readEnv(m.Dir(name)) }

// DetectChannels reads the profile's .env for channel bot tokens: TELEGRAM_BOT_TOKEN -> telegram,
// DISCORD_BOT_TOKEN -> discord. Never nil (the UI expects a JSON array).
func DetectChannels(dir string) []string {
	env := readEnv(dir)
	out := []string{}
	if env["TELEGRAM_BOT_TOKEN"] != "" {
		out = append(out, "telegram")
	}
	if env["DISCORD_BOT_TOKEN"] != "" {
		out = append(out, "discord")
	}
	return out
}

func parsePort(s string) (int, error) {
	var p int
	_, err := fmt.Sscanf(strings.TrimSpace(s), "%d", &p)
	return p, err
}

func freePort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}
