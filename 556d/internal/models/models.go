// Package models holds the model connections of one 556 install: home/models.json, edited in
// 設定 → 模型連線. One master endpoint and three jobs that either follow it or carry their own —
// 對話 (what Hermes talks to, through the shim), 記憶 (kokoro's observe and psyche's appraisal) and 寫靈魂
// (the soul skill and the fidelity probe) — plus the embedder and the timezone.
//
// Nothing here has a default. A missing piece is an error the app shows and 556d refuses to start a
// character on; the code never guesses a URL, a model or a zone (DECISIONS 2026-10-19, "no hidden defaults").
package models

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const (
	UseMaster = "master"
	UseCustom = "custom"

	MethodOpenAI = "openai" // an OpenAI-compatible /v1 endpoint: local servers, proxies, the vendors themselves

	EmbedLlama  = "llama"  // 556d runs llama-server with a GGUF file and serves /v1/embeddings locally
	EmbedOpenAI = "openai" // an OpenAI-compatible /v1/embeddings endpoint somewhere else
)

var Jobs = []string{"chat", "memory", "soul"}

// Endpoint is one OpenAI-compatible connection.
type Endpoint struct {
	Method  string `json:"method"`
	BaseURL string `json:"base_url"`
	APIKey  string `json:"api_key,omitempty"`
	Model   string `json:"model"`
}

// Use is a job's choice: follow the master, or its own endpoint.
type Use struct {
	Use string `json:"use"`
	Endpoint
}

// Embedder is where vectors come from.
type Embedder struct {
	Kind    string `json:"kind"`
	Exe     string `json:"exe,omitempty"`  // llama: llama-server executable (relative to the repo root or absolute)
	File    string `json:"file,omitempty"` // llama: the GGUF model file
	Port    int    `json:"port,omitempty"` // llama: the local port 556d serves it on
	BaseURL string `json:"base_url,omitempty"`
	APIKey  string `json:"api_key,omitempty"`
	Model   string `json:"model"`          // the model name sent with every embeddings request
	Dims    int    `json:"dims,omitempty"` // vector size; 0 = let the store take it from the first vector
}

type Config struct {
	Master   Endpoint `json:"master"`
	Chat     Use      `json:"chat"`
	Memory   Use      `json:"memory"`
	Soul     Use      `json:"soul"`
	Embedder Embedder `json:"embedder"`
	Timezone string   `json:"timezone"` // IANA zone, e.g. Asia/Taipei
}

func Path(home string) string { return filepath.Join(home, "models.json") }

// Load reads the file; exists is false when there is none yet (an empty Config, nothing configured).
func Load(path string) (Config, bool, error) {
	var c Config
	b, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return c, false, nil
		}
		return c, false, err
	}
	if err := json.Unmarshal(b, &c); err != nil {
		return c, true, fmt.Errorf("%s: %w", filepath.Base(path), err)
	}
	return c.normalized(), true, nil
}

func Save(path string, c Config) error {
	b, _ := json.MarshalIndent(c.normalized(), "", "  ")
	return os.WriteFile(path, b, 0o600)
}

func (c Config) normalized() Config {
	trim := func(e *Endpoint) {
		e.Method = strings.TrimSpace(e.Method)
		if e.Method == "" {
			e.Method = MethodOpenAI
		}
		e.BaseURL = strings.TrimRight(strings.TrimSpace(e.BaseURL), "/")
		e.Model = strings.TrimSpace(e.Model)
		e.APIKey = strings.TrimSpace(e.APIKey)
	}
	trim(&c.Master)
	for _, u := range []*Use{&c.Chat, &c.Memory, &c.Soul} {
		u.Use = strings.TrimSpace(u.Use)
		if u.Use != UseCustom {
			u.Use = UseMaster
		}
		trim(&u.Endpoint)
	}
	c.Embedder.Kind = strings.TrimSpace(c.Embedder.Kind)
	c.Embedder.BaseURL = strings.TrimRight(strings.TrimSpace(c.Embedder.BaseURL), "/")
	c.Embedder.Model = strings.TrimSpace(c.Embedder.Model)
	c.Embedder.Exe = strings.TrimSpace(c.Embedder.Exe)
	c.Embedder.File = strings.TrimSpace(c.Embedder.File)
	c.Timezone = strings.TrimSpace(c.Timezone)
	return c
}

func (c Config) use(job string) Use {
	switch job {
	case "chat":
		return c.Chat
	case "memory":
		return c.Memory
	default:
		return c.Soul
	}
}

// Resolve is the endpoint a job actually uses.
func (c Config) Resolve(job string) Endpoint {
	u := c.use(job)
	if u.Use == UseCustom {
		return u.Endpoint
	}
	return c.Master
}

// Missing lists, in the user's words, what is not set yet; empty means every job can run.
func (c Config) Missing() []string {
	out := []string{} // never nil: the UI reads .length on it
	need := func(label string, e Endpoint) {
		if e.BaseURL == "" {
			out = append(out, label+"：網址")
		}
		if e.Model == "" {
			out = append(out, label+"：模型")
		}
	}
	masterNeeded := false
	for job, label := range map[string]string{"chat": "對話", "memory": "記憶", "soul": "寫靈魂"} {
		u := c.use(job)
		if u.Use == UseCustom {
			need(label+"（自訂）", u.Endpoint)
		} else {
			masterNeeded = true
		}
	}
	if masterNeeded {
		need("主設定", c.Master)
	}
	e := c.Embedder
	switch e.Kind {
	case EmbedLlama:
		if e.Exe == "" {
			out = append(out, "向量：llama-server 路徑")
		}
		if e.File == "" {
			out = append(out, "向量：模型檔")
		}
		if e.Port <= 0 {
			out = append(out, "向量：port")
		}
	case EmbedOpenAI:
		if e.BaseURL == "" {
			out = append(out, "向量：網址")
		}
	default:
		out = append(out, "向量：方式")
	}
	if e.Model == "" {
		out = append(out, "向量：模型名稱")
	}
	if c.Timezone == "" {
		out = append(out, "時區")
	} else if _, err := time.LoadLocation(c.Timezone); err != nil {
		out = append(out, "時區（不是有效的 IANA 名稱）")
	}
	sort.Strings(out)
	return out
}

func (c Config) Ready() bool { return len(c.Missing()) == 0 }

// ErrNotConfigured is what a start answers while something is missing.
func ErrNotConfigured(missing []string) error {
	return errors.New("模型連線未設定（設定 → 模型連線）：" + strings.Join(missing, "、"))
}

// Masked is the config as the UI sees it: keys replaced by a flag.
func (c Config) Masked() map[string]any {
	ep := func(e Endpoint) map[string]any {
		return map[string]any{"method": e.Method, "base_url": e.BaseURL, "api_key_set": e.APIKey != "", "model": e.Model}
	}
	use := func(u Use) map[string]any {
		m := ep(u.Endpoint)
		m["use"] = u.Use
		return m
	}
	emb := map[string]any{"kind": c.Embedder.Kind, "exe": c.Embedder.Exe, "file": c.Embedder.File, "port": c.Embedder.Port,
		"base_url": c.Embedder.BaseURL, "api_key_set": c.Embedder.APIKey != "", "model": c.Embedder.Model, "dims": c.Embedder.Dims}
	return map[string]any{"master": ep(c.Master), "chat": use(c.Chat), "memory": use(c.Memory), "soul": use(c.Soul),
		"embedder": emb, "timezone": c.Timezone}
}

// Merge applies what the UI sent over what is stored: an empty api_key keeps the stored one (the UI never
// sees keys, so it cannot send them back).
func Merge(cur, next Config) Config {
	keep := func(dst *Endpoint, old Endpoint) {
		if dst.APIKey == "" {
			dst.APIKey = old.APIKey
		}
	}
	keep(&next.Master, cur.Master)
	keep(&next.Chat.Endpoint, cur.Chat.Endpoint)
	keep(&next.Memory.Endpoint, cur.Memory.Endpoint)
	keep(&next.Soul.Endpoint, cur.Soul.Endpoint)
	if next.Embedder.APIKey == "" {
		next.Embedder.APIKey = cur.Embedder.APIKey
	}
	return next.normalized()
}

// URL is the embeddings endpoint kokoro and the seed tool talk to.
func (e Embedder) URL() string {
	if e.Kind == EmbedLlama {
		return fmt.Sprintf("http://127.0.0.1:%d/v1", e.Port)
	}
	return e.BaseURL
}

// OffsetHours is the zone's current UTC offset — what psyche.json's time.timezone_offset_h takes.
func OffsetHours(tz string, now time.Time) (float64, error) {
	loc, err := time.LoadLocation(tz)
	if err != nil {
		return 0, err
	}
	_, off := now.In(loc).Zone()
	return float64(off) / 3600, nil
}

// Probe asks an endpoint what models it serves (GET /models). The list is what the UI offers in the model
// picker; a server that does not list is reported as such, and the user types the name.
func Probe(ctx context.Context, e Endpoint) ([]string, error) {
	base := strings.TrimRight(strings.TrimSpace(e.BaseURL), "/")
	if base == "" {
		return nil, errors.New("沒有網址")
	}
	req, err := http.NewRequestWithContext(ctx, "GET", base+"/models", nil)
	if err != nil {
		return nil, err
	}
	if e.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+e.APIKey)
	}
	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	if err != nil {
		return nil, fmt.Errorf("連不上：%v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	var body struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, fmt.Errorf("回應不是模型清單：%v", err)
	}
	ids := []string{} // never nil: an endpoint that lists nothing is an empty list, not null
	for _, d := range body.Data {
		if d.ID != "" {
			ids = append(ids, d.ID)
		}
	}
	sort.Strings(ids)
	return ids, nil
}
