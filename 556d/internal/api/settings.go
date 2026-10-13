package api

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"gopkg.in/yaml.v3"

	"github.com/Yooouuuuuuu/556_production/556d/internal/companions"
)

// Settings are the user-facing knobs the app edits. They live in home/settings.json (owned by
// 556d); the ones Hermes reads are applied into home/config.yaml and home/mem0.json on save.
type Settings struct {
	SelectedCompanion string `json:"selected_companion"` // which companion the windows are on (roster selection)
	CompanionName     string `json:"companion_name"`     // display name of the SELECTED companion (companion.json)
	ProducerName      string `json:"producer_name"`   // the user; lives in the prompt layer (USER.md, kokoro.json), never as the memory subject
	ReplyLanguage     string `json:"reply_language"`  // "" = follow the Producer; en | zh-CN | zh-TW | ja (prompt layer: USER.md)
	MirrorToTelegram  bool   `json:"mirror_to_telegram"` // (c) echo app exchanges into the Producer's Telegram DM (plain text, no LLM)
	AvatarModel       string `json:"avatar_model"` // path under assets/live2d, e.g. hiyori/Hiyori.model3.json
	ShowAvatarOnStart bool   `json:"show_avatar_on_start"`
	MemoryLanguage    string `json:"memory_language"` // effective in the kokoro engine (Path C); mem0 has no prompt hook
	ModelLane         string `json:"model_lane"`      // -> config.yaml model.default
	ContextTurns      int    `json:"context_turns"`   // -> config.yaml compression.protect_last_n
	EmbedderModel     string `json:"embedder_model"`  // -> mem0.json embedder model (re-embed required)
}

func defaultSettings() Settings {
	return Settings{
		SelectedCompanion: "",
		CompanionName:     "",
		ProducerName:      "",
		ReplyLanguage:     "",
		MirrorToTelegram:  true,
		AvatarModel:       "hiyori/Hiyori.model3.json",
		ShowAvatarOnStart: true,
		MemoryLanguage:    "zh-TW",
		ModelLane:         "auto/556",
		ContextTurns:      20,
		EmbedderModel:     "bge-m3",
	}
}

type SettingsStore struct {
	mu      sync.Mutex
	home    string
	profile string // the selected companion ("" = none)
	profileDirPath string
	cur     Settings
}

func NewSettingsStore(hermesHome string) *SettingsStore {
	s := &SettingsStore{home: hermesHome, cur: defaultSettings()}
	if b, err := os.ReadFile(s.path()); err == nil {
		_ = json.Unmarshal(b, &s.cur)
	}
	return s
}

func (s *SettingsStore) path() string { return filepath.Join(s.home, "settings.json") }

// profileDir is the HERMES_HOME of the selected companion ("" when none is selected).
func (s *SettingsStore) profileDir() string { return s.profileDirPath }

// SetSelected binds the store to a companion: companion_name / avatar_model are read from her
// companion.json and later saves write there. Persisted in settings.json.
func (s *SettingsStore) SetSelected(name, dir string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.profile, s.profileDirPath = name, dir
	s.cur.SelectedCompanion = name
	if dir != "" {
		cj := companions.ReadCompanionJSON(dir)
		if display, _ := cj["display_name"].(string); display != "" {
			s.cur.CompanionName = display
		}
		if avatar, _ := cj["avatar_model"].(string); avatar != "" {
			s.cur.AvatarModel = avatar
		}
	}
	b, _ := json.MarshalIndent(s.cur, "", "  ")
	_ = os.WriteFile(s.path(), b, 0o644)
}

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
	if next.SelectedCompanion != s.cur.SelectedCompanion {
		next.SelectedCompanion = s.cur.SelectedCompanion // selection changes go through /api/selected
	}
	if s.profileDirPath != "" && (next.CompanionName != s.cur.CompanionName || next.AvatarModel != s.cur.AvatarModel) {
		cj := companions.ReadCompanionJSON(s.profileDirPath)
		cj["display_name"], cj["avatar_model"] = next.CompanionName, next.AvatarModel
		if err := companions.WriteCompanionJSON(s.profileDirPath, cj); err != nil {
			return s.cur, Applied{}, err
		}
	}
	if s.profileDirPath != "" && (next.ProducerName != s.cur.ProducerName || next.ReplyLanguage != s.cur.ReplyLanguage || next.MemoryLanguage != s.cur.MemoryLanguage || next.EmbedderModel != s.cur.EmbedderModel) {
		if err := s.applyKokoro(next); err != nil {
			return s.cur, Applied{}, err
		}
		if err := s.applyUserMD(next); err != nil {
			return s.cur, Applied{}, err
		}
		ap.RestartRequired = true // USER.md and kokoro.json are read at agent start
	}
	b, _ := json.MarshalIndent(next, "", "  ")
	if err := os.WriteFile(s.path(), b, 0o644); err != nil {
		return s.cur, Applied{}, err
	}
	s.cur = next
	return next, ap, nil
}

// applyConfigYAML edits the SELECTED companion's config.yaml in place (comments preserved via
// yaml.Node): her model lane and the context window are hers, not the agency's.
func (s *SettingsStore) applyConfigYAML(v Settings) error {
	dir := s.profileDir()
	if dir == "" {
		dir = s.home
	}
	p := filepath.Join(dir, "config.yaml")
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

// applyMem0 rewrites the embedder model in home/mem0.json (legacy Path A; skipped when absent).
func (s *SettingsStore) applyMem0(v Settings) error {
	p := filepath.Join(s.home, "mem0.json")
	raw, err := os.ReadFile(p)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
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

// applyKokoro writes the prompt-layer values into the bound profile's kokoro.json:
// producer_name (never the memory subject), memory language, embedder model.
func (s *SettingsStore) applyKokoro(v Settings) error {
	if s.profileDir() == "" {
		return nil
	}
	p := filepath.Join(s.profileDir(), "kokoro.json")
	raw, err := os.ReadFile(p)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // no kokoro engine on this profile
		}
		return err
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		return err
	}
	m["producer_name"] = v.ProducerName
	m["language"] = v.MemoryLanguage
	if emb, ok := m["embedder"].(map[string]any); ok {
		emb["model"] = v.EmbedderModel
	}
	out, _ := json.MarshalIndent(m, "", "  ")
	return os.WriteFile(p, out, 0o644)
}

// applyUserMD keeps one managed line in the profile's memories/USER.md (Hermes injects the
// file every turn): the Producer's name. Everything else in the file is left alone.
func (s *SettingsStore) applyUserMD(v Settings) error {
	if s.profileDir() == "" {
		return nil
	}
	dir := filepath.Join(s.profileDir(), "memories")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	p := filepath.Join(dir, "USER.md")
	raw, _ := os.ReadFile(p)
	nameLine := "- 名字：（尚未設定，先叫「製作人」）"
	if strings.TrimSpace(v.ProducerName) != "" {
		nameLine = "- 名字：" + strings.TrimSpace(v.ProducerName) + "（請這樣稱呼他）"
	}
	langLine := "- 回覆語言：跟著製作人（他用什麼語言就用什麼語言回覆）"
	switch v.ReplyLanguage {
	case "en":
		langLine = "- 回覆語言：English（請一律用英文回覆）"
	case "zh-CN":
		langLine = "- 回覆語言：简体中文（请一律用简体中文回复）"
	case "zh-TW":
		langLine = "- 回覆語言：繁體中文（請一律用繁體中文回覆）"
	case "ja":
		langLine = "- 回覆語言：日本語（必ず日本語で返答すること）"
	}
	lines := strings.Split(strings.ReplaceAll(string(raw), "\r\n", "\n"), "\n")
	managed := []struct{ prefixes []string; line string }{
		{[]string{"- 名字：", "- 稱呼："}, nameLine},
		{[]string{"- 回覆語言："}, langLine},
	}
	if len(lines) == 0 || !strings.HasPrefix(lines[0], "# ") {
		lines = append([]string{"# 製作人"}, lines...)
	}
	for _, m := range managed {
		done := false
		for i, l := range lines {
			for _, pre := range m.prefixes {
				if strings.HasPrefix(l, pre) {
					lines[i] = m.line
					done = true
					break
				}
			}
			if done {
				break
			}
		}
		if !done {
			lines = append(lines[:1], append([]string{m.line}, lines[1:]...)...)
		}
	}
	return os.WriteFile(p, []byte(strings.TrimRight(strings.Join(lines, "\n"), "\n")+"\n"), 0o644)
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
