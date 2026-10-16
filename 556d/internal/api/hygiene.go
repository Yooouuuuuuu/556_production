package api

import (
	"errors"
	"log"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// Prompt hygiene, the config half (docs/prompt/prompt.md §2.8): the vendor guidance blocks that have a switch are
// switched off in her config.yaml, and the platform hints are replaced by one zh-TW line each, so her system
// prompt names no product, no machine and no file format. Applied before every start (idempotent: only a changed
// key rewrites the file); the shim drops the paragraphs that have no switch.

var platformHintZH = map[string]string{
	"api_server": "你在聊天視窗裡說話：純文字，不用 markdown（沒有星號、條列、標題、程式碼框）。像在傳訊息，簡短自然。",
	"telegram":   "你在 Telegram 上說話：純文字就好，不用 markdown，不用標題或表格。像在傳訊息，簡短自然。",
	"discord":    "你在 Discord 上說話：純文字就好，不用 markdown，不用標題或表格。像在傳訊息，簡短自然。",
}

// ensurePromptHygiene writes the switches and the hints into <dir>/config.yaml when they are not already there.
func ensurePromptHygiene(dir string) (bool, error) {
	path := filepath.Join(dir, "config.yaml")
	raw, err := os.ReadFile(path)
	if err != nil {
		return false, err
	}
	var doc yaml.Node
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return false, err
	}
	if doc.Kind != yaml.DocumentNode || len(doc.Content) == 0 {
		return false, errors.New("unexpected yaml document")
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
	for _, k := range []string{"task_completion_guidance", "parallel_tool_call_guidance", "environment_probe"} {
		want([]string{"agent", k}, "false", "!!bool")
	}
	for platform, text := range platformHintZH {
		want([]string{"platform_hints", platform, "replace"}, text, "!!str")
	}
	if !changed {
		return false, nil
	}
	out, err := yaml.Marshal(&doc)
	if err != nil {
		return false, err
	}
	if err := os.WriteFile(path, out, 0o644); err != nil {
		return false, err
	}
	log.Printf("[hygiene] %s: config.yaml — guidance switches off, platform hints in zh-TW", filepath.Base(dir))
	return true, nil
}
