package api

// Tools — what she can DO besides talking (0.5.0; baseline emptied in 0.8.6). Memory is not a tool any more: kokoro
// injects it every turn. Everything else is an
// extension switched on per character in Settings: it is written into her config.yaml as
// platform_toolsets for the app route and her channels, and a graceful restart applies it.
// No hot toggling by design (simple and stable).

import (
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

type Extension struct {
	Key         string   `json:"key"`
	Label       string   `json:"label"`
	Help        string   `json:"help"`
	Toolsets    []string `json:"toolsets"`
	ActsInWorld bool     `json:"acts_in_world"` // needs an approval path before it is safe to switch on
	Enabled     bool     `json:"enabled"`
}

// baselineToolsets is what every character has: nothing (option C, docs/prompt/around-the-soul.md §2, 2026-10-19).
// Memory is injected every turn by kokoro's prompt section and Memory block; the two kokoro tools were never
// called in 79 turns and the tools scaffold cost every character a preamble and three guidance blocks. An
// extension (查網路) brings the scaffold back for that character only.
var baselineToolsets = []string{}

// toolPlatforms are the Hermes platform keys her process serves: the app (API server) and Telegram.
var toolPlatforms = []string{"api_server", "telegram", "cli"}

// extensionCatalog is the list Settings shows. Order matters; keys are stable.
var extensionCatalog = []Extension{
	{Key: "web", Label: "查網路", Help: "web_search + web_extract。沒有金鑰也能用：Hermes 會輪替免費層（含 DuckDuckGo）。", Toolsets: []string{"web"}},
}

// companionToolsets reads platform_toolsets.<platform> from her config.yaml (nil = not set).
func companionToolsets(dir, platform string) ([]string, error) {
	raw, err := os.ReadFile(filepath.Join(dir, "config.yaml"))
	if err != nil {
		return nil, err
	}
	var doc yaml.Node
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return nil, err
	}
	if doc.Kind != yaml.DocumentNode || len(doc.Content) == 0 {
		return nil, nil
	}
	seq := yamlFind(doc.Content[0], []string{"platform_toolsets", platform})
	if seq == nil || seq.Kind != yaml.SequenceNode {
		return nil, nil
	}
	out := []string{}
	for _, n := range seq.Content {
		if n.Value != "" {
			out = append(out, n.Value)
		}
	}
	return out, nil
}

// writeToolsets sets platform_toolsets for every platform she serves and keeps Hermes's built-in
// memory writer off (kokoro is her memory; it injects USER.md itself).
func writeToolsets(dir string, toolsets []string) error {
	path := filepath.Join(dir, "config.yaml")
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
	for _, p := range toolPlatforms {
		setYAMLSequence(root, []string{"platform_toolsets", p}, toolsets)
	}
	setYAMLScalar(root, []string{"memory", "memory_enabled"}, "false", "!!bool")
	setYAMLScalar(root, []string{"memory", "user_profile_enabled"}, "false", "!!bool")
	out, err := yaml.Marshal(&doc)
	if err != nil {
		return err
	}
	return os.WriteFile(path, out, 0o644)
}

// yamlFind walks mapping keys and returns the node at path, whatever its kind (yamlGet is scalar-only).
func yamlFind(root *yaml.Node, path []string) *yaml.Node {
	node := root
	for _, key := range path {
		if node == nil || node.Kind != yaml.MappingNode {
			return nil
		}
		var next *yaml.Node
		for i := 0; i+1 < len(node.Content); i += 2 {
			if node.Content[i].Value == key {
				next = node.Content[i+1]
				break
			}
		}
		node = next
	}
	return node
}

// ensureYAMLMap walks path[:len-1] creating mapping nodes, and returns (parent mapping, last key).
func ensureYAMLMap(root *yaml.Node, path []string) (*yaml.Node, string) {
	cur := root
	for _, key := range path[:len(path)-1] {
		var next *yaml.Node
		for i := 0; i+1 < len(cur.Content); i += 2 {
			if cur.Content[i].Value == key {
				next = cur.Content[i+1]
				break
			}
		}
		if next == nil || next.Kind != yaml.MappingNode {
			next = &yaml.Node{Kind: yaml.MappingNode, Tag: "!!map"}
			cur.Content = append(cur.Content, &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!str", Value: key}, next)
		}
		cur = next
	}
	return cur, path[len(path)-1]
}

func setYAMLNode(root *yaml.Node, path []string, value *yaml.Node) {
	parent, key := ensureYAMLMap(root, path)
	for i := 0; i+1 < len(parent.Content); i += 2 {
		if parent.Content[i].Value == key {
			parent.Content[i+1] = value
			return
		}
	}
	parent.Content = append(parent.Content, &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!str", Value: key}, value)
}

func setYAMLSequence(root *yaml.Node, path []string, items []string) {
	seq := &yaml.Node{Kind: yaml.SequenceNode, Tag: "!!seq", Style: yaml.FlowStyle}
	for _, it := range items {
		seq.Content = append(seq.Content, &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!str", Value: it})
	}
	setYAMLNode(root, path, seq)
}

func setYAMLScalar(root *yaml.Node, path []string, value, tag string) {
	setYAMLNode(root, path, &yaml.Node{Kind: yaml.ScalarNode, Tag: tag, Value: value})
}

// extensionsFor marks each catalog entry enabled when every toolset of it is in her list.
func extensionsFor(current []string) []Extension {
	have := map[string]bool{}
	for _, t := range current {
		have[t] = true
	}
	out := make([]Extension, 0, len(extensionCatalog))
	for _, e := range extensionCatalog {
		e.Enabled = len(e.Toolsets) > 0
		for _, t := range e.Toolsets {
			if !have[t] {
				e.Enabled = false
			}
		}
		out = append(out, e)
	}
	return out
}

// toolsHandler — GET: baseline + extensions with state; PUT {"key","enabled"}: rewrite her
// toolsets (baseline ∪ enabled extensions) and report that a restart applies it.
func (a *API) toolsHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, PUT, OPTIONS") {
		return
	}
	name := r.URL.Query().Get("companion")
	if name == "" {
		name = a.selectedName()
	}
	if name == "" || !a.mgr.Exists(name) {
		writeJSON(w, 409, map[string]any{"error": errNoCompanion.Error()})
		return
	}
	dir := a.mgr.Dir(name)
	current, err := companionToolsets(dir, "api_server")
	if err != nil {
		writeJSON(w, 500, map[string]any{"error": err.Error()})
		return
	}
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, 200, map[string]any{"companion": name, "baseline": baselineToolsets,
			"configured": current != nil, "extensions": extensionsFor(current)})
	case http.MethodPut:
		var body struct {
			Key     string `json:"key"`
			Enabled bool   `json:"enabled"`
		}
		if err := decodeJSON(r, &body); err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		var target *Extension
		for i := range extensionCatalog {
			if extensionCatalog[i].Key == body.Key {
				target = &extensionCatalog[i]
			}
		}
		if target == nil {
			writeJSON(w, 404, map[string]any{"error": "unknown extension " + body.Key})
			return
		}
		enabled := map[string]bool{}
		for _, e := range extensionsFor(current) {
			enabled[e.Key] = e.Enabled
		}
		enabled[body.Key] = body.Enabled
		next := append([]string{}, baselineToolsets...)
		for _, e := range extensionCatalog {
			if enabled[e.Key] {
				next = append(next, e.Toolsets...)
			}
		}
		if err := writeToolsets(dir, next); err != nil {
			writeJSON(w, 500, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]any{"companion": name, "baseline": baselineToolsets, "configured": true,
			"extensions": extensionsFor(next), "toolsets": next, "restart_required": true,
			"note": strings.Join(next, ", ") + " — restart her to apply"})
	default:
		writeJSON(w, 405, map[string]any{"error": "method not allowed"})
	}
}
