package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"gopkg.in/yaml.v3"

	"github.com/Yooouuuuuuu/556_production/556d/internal/models"
	"github.com/Yooouuuuuuu/556_production/556d/internal/shim"
)

// Model connections (home/models.json; 設定 → 全域 → 模型連線):
//   GET  /api/connections         the config with keys masked, what is still missing, the embedder's state
//   PUT  /api/connections         replace (an empty api_key keeps the stored one); applied at once to the shim,
//                                 the embedder and the clock; running characters need a restart
//   POST /api/connections/probe   {base_url, api_key?, job?}: GET <base_url>/models — the model picker's list;
//                                 an empty api_key uses the stored key of that job (or the master's)
// Before a character starts, prepareProfile writes what she needs from this file into her own files: the
// shim as her model (config.yaml), the memory and embedder endpoints (kokoro.json), the zone (psyche.json).
// Nothing starts while something is missing.

func (a *API) connectionsPath() string { return models.Path(a.settings.home) }

func (a *API) connections() (models.Config, bool, error) { return models.Load(a.connectionsPath()) }

// LoadConnections applies the stored file at boot (or says what is missing); main calls it once.
func (a *API) LoadConnections() {
	c, exists, err := a.connections()
	switch {
	case err != nil:
		log.Printf("[connections] %v", err)
	case !exists:
		log.Printf("[connections] home/models.json missing: set 設定 → 全域 → 模型連線 before starting a character")
	case !c.Ready():
		log.Printf("[connections] incomplete: %v", c.Missing())
		a.applyConnections(c)
	default:
		a.applyConnections(c)
	}
}

// applyConnections pushes the parts 556d itself runs: the shim's backend, the local embedder, the clock zone.
func (a *API) applyConnections(c models.Config) {
	if a.Shim != nil {
		chat := c.Resolve("chat")
		if chat.BaseURL != "" && chat.Model != "" {
			a.Shim.SetBackend(&shim.Backend{BaseURL: chat.BaseURL, Model: chat.Model, APIKey: chat.APIKey})
		} else {
			a.Shim.SetBackend(nil)
		}
	}
	if a.Embedder != nil {
		a.Embedder.Apply(c.Embedder)
	}
	if c.Timezone != "" {
		if _, err := time.LoadLocation(c.Timezone); err == nil {
			a.mgr.Timezone = c.Timezone
		}
	}
}

func (a *API) connectionsHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, PUT, OPTIONS") {
		return
	}
	cur, exists, err := a.connections()
	if err != nil {
		writeJSON(w, 500, map[string]any{"error": err.Error()})
		return
	}
	view := func(c models.Config) map[string]any {
		out := map[string]any{"exists": exists, "connections": c.Masked(), "missing": c.Missing(),
			"methods": []string{models.MethodOpenAI}, "embedder_kinds": []string{models.EmbedLlama, models.EmbedOpenAI}}
		if a.Embedder != nil {
			out["embedder_status"] = a.Embedder.Status()
		}
		return out
	}
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, 200, view(cur))
	case http.MethodPut:
		var next models.Config
		if err := decodeJSON(r, &next); err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		merged := models.Merge(cur, next)
		if err := models.Save(a.connectionsPath(), merged); err != nil {
			writeJSON(w, 500, map[string]any{"error": err.Error()})
			return
		}
		exists = true
		a.applyConnections(merged)
		restart := false
		for _, info := range a.mgr.List() {
			if info.Active {
				restart = true
			}
		}
		out := view(merged)
		out["restart_required"] = restart
		log.Printf("[connections] saved (missing: %v)", merged.Missing())
		writeJSON(w, 200, out)
	default:
		writeJSON(w, 405, map[string]any{"error": "GET or PUT"})
	}
}

func (a *API) connectionsProbe(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, 405, map[string]any{"error": "POST only"})
		return
	}
	var body struct {
		BaseURL string `json:"base_url"`
		APIKey  string `json:"api_key"`
		Job     string `json:"job"` // chat | memory | soul | master | embedder: whose stored key to use when none is sent
	}
	if err := decodeJSON(r, &body); err != nil {
		writeJSON(w, 400, map[string]any{"error": err.Error()})
		return
	}
	key := body.APIKey
	if key == "" {
		if cur, _, _ := a.connections(); true {
			switch body.Job {
			case "chat", "memory", "soul":
				u := map[string]models.Use{"chat": cur.Chat, "memory": cur.Memory, "soul": cur.Soul}[body.Job]
				if u.Use == models.UseCustom {
					key = u.APIKey
				} else {
					key = cur.Master.APIKey
				}
			case "embedder":
				key = cur.Embedder.APIKey
			default:
				key = cur.Master.APIKey
			}
		}
	}
	ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	ids, err := models.Probe(ctx, models.Endpoint{BaseURL: body.BaseURL, APIKey: key})
	if err != nil {
		writeJSON(w, 200, map[string]any{"ok": false, "error": err.Error(), "models": []string{}})
		return
	}
	writeJSON(w, 200, map[string]any{"ok": true, "models": ids})
}

// prepareProfile writes a character's files from the connections before she starts; an error means she
// must not start (the roster shows it).
func (a *API) prepareProfile(name string) error {
	c, exists, err := a.connections()
	if err != nil {
		return err
	}
	if !exists || !c.Ready() {
		return models.ErrNotConfigured(c.Missing())
	}
	dir := a.mgr.Dir(name)
	if err := writeProfileConfig(filepath.Join(dir, "config.yaml"), a.ShimPort); err != nil {
		return fmt.Errorf("config.yaml: %w", err)
	}
	if err := writeKokoroConnections(filepath.Join(dir, "kokoro.json"), c.Resolve("memory"), c.Embedder); err != nil {
		return fmt.Errorf("kokoro.json: %w", err)
	}
	if err := writePsycheZone(filepath.Join(dir, "psyche.json"), c.Timezone); err != nil {
		return fmt.Errorf("psyche.json: %w", err)
	}
	a.applyConnections(c)
	return nil
}

// writeProfileConfig pins her config.yaml to 556: the shim is her model, kokoro her memory, psyche her
// inner life, no toolset at baseline. The file is hers (Hermes wrote the rest); only these keys are set.
func writeProfileConfig(path string, shimPort int) error {
	if shimPort <= 0 {
		return errors.New("shim port unknown")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var doc yaml.Node
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return err
	}
	if doc.Kind != yaml.DocumentNode || len(doc.Content) == 0 {
		return errors.New("unexpected yaml document")
	}
	root := doc.Content[0]
	changed := false
	want := func(path []string, value, tag string) {
		if n := yamlFind(root, path); n != nil && n.Kind == yaml.ScalarNode && n.Value == value {
			return
		}
		setYAMLScalar(root, path, value, tag)
		changed = true
	}
	want([]string{"model", "provider"}, "custom", "!!str")
	want([]string{"model", "base_url"}, fmt.Sprintf("http://127.0.0.1:%d/v1", shimPort), "!!str")
	want([]string{"model", "default"}, shim.Lane, "!!str")
	want([]string{"memory", "provider"}, "kokoro", "!!str")
	want([]string{"memory", "memory_enabled"}, "false", "!!bool")
	want([]string{"memory", "user_profile_enabled"}, "false", "!!bool")
	// plugins.enabled must list psyche (kokoro is activated by memory.provider)
	var enabled []string
	hasPsyche := false
	if seq := yamlFind(root, []string{"plugins", "enabled"}); seq != nil && seq.Kind == yaml.SequenceNode {
		for _, n := range seq.Content {
			if n.Value != "" {
				enabled = append(enabled, n.Value)
			}
			if n.Value == "psyche" {
				hasPsyche = true
			}
		}
	}
	if !hasPsyche {
		setYAMLSequence(root, []string{"plugins", "enabled"}, append(enabled, "psyche"))
		changed = true
	}
	for _, platform := range toolPlatforms { // a list must exist per platform: without one Hermes uses its ~20 default tools
		if seq := yamlFind(root, []string{"platform_toolsets", platform}); seq == nil || seq.Kind != yaml.SequenceNode {
			setYAMLSequence(root, []string{"platform_toolsets", platform}, []string{})
			changed = true
		}
	}
	if !changed {
		return nil
	}
	out, err := yaml.Marshal(&doc)
	if err != nil {
		return err
	}
	return os.WriteFile(path, out, 0o644)
}

// writeKokoroConnections sets the memory LLM and the embedder in kokoro.json; the rest of the file is hers.
func writeKokoroConnections(path string, llm models.Endpoint, e models.Embedder) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		return err
	}
	timeout := 60.0
	if old, ok := m["llm"].(map[string]any); ok {
		if t, ok := old["timeout"].(float64); ok && t > 0 {
			timeout = t
		}
	}
	l := map[string]any{"base_url": llm.BaseURL, "model": llm.Model, "timeout": timeout}
	if llm.APIKey != "" {
		l["api_key"] = llm.APIKey
	}
	m["llm"] = l
	emb := map[string]any{"base_url": e.URL(), "model": e.Model}
	if e.APIKey != "" {
		emb["api_key"] = e.APIKey
	}
	if e.Dims > 0 {
		emb["dims"] = e.Dims
	}
	m["embedder"] = emb
	out, _ := json.MarshalIndent(m, "", "  ")
	return os.WriteFile(path, out, 0o644)
}

// writePsycheZone keeps the engine's clock in the configured zone (time.timezone_offset_h).
func writePsycheZone(path string, tz string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // no inner life on this profile
		}
		return err
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		return err
	}
	off, err := models.OffsetHours(tz, time.Now())
	if err != nil {
		return err
	}
	t, _ := m["time"].(map[string]any)
	if t == nil {
		t = map[string]any{}
	}
	if cur, ok := t["timezone_offset_h"].(float64); ok && cur == off {
		return nil
	}
	t["timezone_offset_h"] = off
	m["time"] = t
	out, _ := json.MarshalIndent(m, "", "  ")
	return os.WriteFile(path, out, 0o644)
}

// soulEndpoint is what the soul skill and the fidelity probe call; false while it is not configured.
func (a *API) soulEndpoint() (models.Endpoint, bool) {
	c, exists, err := a.connections()
	if err != nil || !exists {
		return models.Endpoint{}, false
	}
	e := c.Resolve("soul")
	return e, e.BaseURL != "" && e.Model != ""
}

func (a *API) soulModel() string {
	e, _ := a.soulEndpoint()
	return e.Model
}
