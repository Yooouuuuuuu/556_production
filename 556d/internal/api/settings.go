package api

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sync"

	"gopkg.in/yaml.v3"
)

// Settings are the user-facing knobs the app edits. They live in home/settings.json (owned by
// 556d); the ones Hermes reads are applied into home/config.yaml and home/mem0.json on save.
type Settings struct {
	CompanionName     string `json:"companion_name"`
	AvatarModel       string `json:"avatar_model"` // path under assets/live2d, e.g. hiyori/Hiyori.model3.json
	ShowAvatarOnStart bool   `json:"show_avatar_on_start"`
	MemoryLanguage    string `json:"memory_language"` // effective in the kokoro engine (Path C); mem0 has no prompt hook
	ModelLane         string `json:"model_lane"`      // -> config.yaml model.default
	ContextTurns      int    `json:"context_turns"`   // -> config.yaml compression.protect_last_n
	EmbedderModel     string `json:"embedder_model"`  // -> mem0.json embedder model (re-embed required)
}

func defaultSettings() Settings {
	return Settings{
		CompanionName:     "",
		AvatarModel:       "hiyori/Hiyori.model3.json",
		ShowAvatarOnStart: true,
		MemoryLanguage:    "zh-TW",
		ModelLane:         "auto/556",
		ContextTurns:      20,
		EmbedderModel:     "bge-m3",
	}
}

type SettingsStore struct {
	mu   sync.Mutex
	home string
	cur  Settings
}

func NewSettingsStore(hermesHome string) *SettingsStore {
	s := &SettingsStore{home: hermesHome, cur: defaultSettings()}
	if b, err := os.ReadFile(s.path()); err == nil {
		_ = json.Unmarshal(b, &s.cur)
	}
	return s
}

func (s *SettingsStore) path() string { return filepath.Join(s.home, "settings.json") }

func (s *SettingsStore) Get() Settings {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.cur
}

// Applied reports which side effects a save produced.
type Applied struct {
	RestartRequired bool `json:"restart_required"`
	ReembedRequired bool `json:"reembed_required"`
}

// Update merges a partial JSON patch, persists, and applies Hermes-facing values.
func (s *SettingsStore) Update(patch json.RawMessage) (Settings, Applied, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	next := s.cur
	if err := json.Unmarshal(patch, &next); err != nil {
		return s.cur, Applied{}, err
	}
	if next.ContextTurns < 2 || next.ContextTurns > 200 {
		return s.cur, Applied{}, errors.New("context_turns must be 2..200")
	}
	var ap Applied
	if next.ModelLane != s.cur.ModelLane || next.ContextTurns != s.cur.ContextTurns {
		if err := s.applyConfigYAML(next); err != nil {
			return s.cur, Applied{}, err
		}
		ap.RestartRequired = true
	}
	if next.EmbedderModel != s.cur.EmbedderModel {
		if err := s.applyMem0(next); err != nil {
			return s.cur, Applied{}, err
		}
		ap.RestartRequired, ap.ReembedRequired = true, true
	}
	b, _ := json.MarshalIndent(next, "", "  ")
	if err := os.WriteFile(s.path(), b, 0o644); err != nil {
		return s.cur, Applied{}, err
	}
	s.cur = next
	return next, ap, nil
}

// applyConfigYAML edits home/config.yaml in place (comments preserved via yaml.Node).
func (s *SettingsStore) applyConfigYAML(v Settings) error {
	p := filepath.Join(s.home, "config.yaml")
	raw, err := os.ReadFile(p)
	if err != nil {
		return err
	}
	var doc yaml.Node
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return err
	}
	if doc.Kind != yaml.DocumentNode || len(doc.Content) == 0 {
		return errors.New("config.yaml: unexpected document")
	}
	root := doc.Content[0]
	setScalar(root, []string{"model", "default"}, v.ModelLane)
	setScalar(root, []string{"compression", "protect_last_n"}, itoa(v.ContextTurns))
	out, err := yaml.Marshal(&doc)
	if err != nil {
		return err
	}
	return os.WriteFile(p, out, 0o644)
}

// applyMem0 rewrites the embedder model in home/mem0.json.
func (s *SettingsStore) applyMem0(v Settings) error {
	p := filepath.Join(s.home, "mem0.json")
	raw, err := os.ReadFile(p)
	if err != nil {
		return err
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		return err
	}
	oss, _ := m["oss"].(map[string]any)
	emb, _ := oss["embedder"].(map[string]any)
	cfg, _ := emb["config"].(map[string]any)
	if cfg == nil {
		return errors.New("mem0.json: no oss.embedder.config")
	}
	cfg["model"] = v.EmbedderModel
	out, _ := json.MarshalIndent(m, "", "  ")
	return os.WriteFile(p, out, 0o644)
}

// setScalar sets root[path...] = value, creating mapping nodes along the way.
func setScalar(root *yaml.Node, path []string, value string) {
	node := root
	for i, key := range path {
		if node.Kind != yaml.MappingNode {
			node.Kind, node.Tag, node.Content = yaml.MappingNode, "!!map", nil
		}
		var found *yaml.Node
		for j := 0; j+1 < len(node.Content); j += 2 {
			if node.Content[j].Value == key {
				found = node.Content[j+1]
				break
			}
		}
		if found == nil {
			k := &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!str", Value: key}
			var val *yaml.Node
			if i == len(path)-1 {
				val = &yaml.Node{Kind: yaml.ScalarNode, Value: value}
			} else {
				val = &yaml.Node{Kind: yaml.MappingNode, Tag: "!!map"}
			}
			node.Content = append(node.Content, k, val)
			found = val
		}
		if i == len(path)-1 {
			found.Kind, found.Tag, found.Value, found.Content = yaml.ScalarNode, "", value, nil
			return
		}
		node = found
	}
}

func itoa(n int) string {
	b, _ := json.Marshal(n)
	return string(b)
}
