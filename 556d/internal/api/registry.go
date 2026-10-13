package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

// The config registry: every knob the system has, declared once — where it lives (file + path),
// its type, who it belongs to (agency or the selected companion), whether it is a developer
// knob, and what changing it costs (restart her / restart the app / re-embed / reindex / migrate).
// Rule from the Producer (2026-10-02): nothing may be fixed in a config file; everything is
// editable from Settings — non-technical knobs directly, the rest behind the developer toggle.
// Limits: the TOML writer rewrites a `key = value` line without its inline comment; YAML keeps comments.
//
//   GET /api/config          every knob with its current value (secrets masked)
//   PUT /api/config {k: v}   write the given knobs; returns the effects to act on

type Knob struct {
	Key     string   `json:"key"`
	Group   string   `json:"group"`   // UI group id
	Label   string   `json:"label"`   // zh-TW label
	Help    string   `json:"help"`    // one line
	Type    string   `json:"type"`    // string | int | float | bool | select | secret
	Options []string `json:"options,omitempty"`
	Scope   string   `json:"scope"`   // agency | companion
	Dev     bool     `json:"dev"`     // developer-only knob
	Effect  string   `json:"effect"`  // none | restart_companion | restart_app | reembed | reindex | migrate_subject
	kind    string   // yaml | json | env | toml
	file    string   // relative to the scope root (profile dir / home / repo root)
	path    string   // dotted path (yaml/json/toml) or env KEY
	root    string   // "" = profile dir (companion) or home (agency); "repo" = repo root
	Default any      `json:"default,omitempty"`
	Value   any      `json:"value"`
	Set     *bool    `json:"set,omitempty"` // secrets: whether a value exists
}

func knobs() []Knob {
	c := func(key, group, label, help, typ, effect, kind, file, path string, opts ...string) Knob {
		return Knob{Key: key, Group: group, Label: label, Help: help, Type: typ, Scope: "companion", Dev: true,
			Effect: effect, kind: kind, file: file, path: path, Options: opts}
	}
	a := func(key, group, label, help, typ, effect, kind, file, path string, opts ...string) Knob {
		k := c(key, group, label, help, typ, effect, kind, file, path, opts...)
		k.Scope, k.root = "agency", "repo"
		return k
	}
	withDefault := func(k Knob, d any) Knob { k.Default = d; return k }
	return []Knob{
		// ---- her model (config.yaml)
		c("model.lane", "model", "模型路線（lane）", "shim 的 lane 名稱；對應 shim/routing.json", "string", "restart_companion", "yaml", "config.yaml", "model.default"),
		c("model.base_url", "model", "模型 API 位址", "OpenAI 相容端點（預設是 556d 的 shim）", "string", "restart_companion", "yaml", "config.yaml", "model.base_url"),
		c("model.context_length", "model", "模型上下文長度", "tokens", "int", "restart_companion", "yaml", "config.yaml", "model.context_length"),
		withDefault(c("model.streaming", "model", "串流回覆", "Hermes 與模型之間是否串流", "bool", "restart_companion", "yaml", "config.yaml", "model.streaming"), false),
		c("context.protect_last_n", "model", "對話視窗保留的輪數（X）", "壓縮時保留最後 X 輪；聊天視窗也顯示 X 輪", "int", "restart_companion", "yaml", "config.yaml", "compression.protect_last_n"),
		c("memory.provider", "model", "記憶提供者", "kokoro = KeepsakeDB；mem0 = 舊路線", "select", "restart_companion", "yaml", "config.yaml", "memory.provider", "kokoro", "mem0"),
		// ---- her channels
		c("telegram.token", "channels", "Telegram bot token", "她自己的 bot（BotFather）", "secret", "restart_companion", "env", ".env", "TELEGRAM_BOT_TOKEN"),
		c("telegram.allowed_users", "channels", "Telegram 允許的使用者 ID", "逗號分隔的數字 ID；空白 = 全部拒絕", "string", "restart_companion", "env", ".env", "TELEGRAM_ALLOWED_USERS"),
		c("telegram.home_channel", "channels", "Telegram 主要聊天室（home channel）", "她送通知／同步訊息的聊天室；通常是你的 DM（你的數字 ID）", "string", "restart_companion", "env", ".env", "TELEGRAM_HOME_CHANNEL"),
		c("telegram.allow_all", "channels", "Telegram 允許所有人", "true 會讓任何人都能跟她說話（不建議）", "string", "restart_companion", "env", ".env", "TELEGRAM_ALLOW_ALL_USERS"),
		withDefault(c("telegram.streaming", "channels", "Telegram 草稿串流", "關掉可避免訊息重複出現（Hermes 預設開）", "bool", "restart_companion", "yaml", "config.yaml", "display.platforms.telegram.streaming"), true),
		withDefault(c("telegram.restart_notice", "channels", "Telegram 啟停提示", "她上線／收工時 Hermes 會在 DM 發「Gateway shutting down」之類的提示；556 預設關", "bool", "restart_companion", "yaml", "config.yaml", "platforms.telegram.gateway_restart_notification"), false),
		c("discord.token", "channels", "Discord bot token", "之後再做；放了 token 她啟動時就會上線", "secret", "restart_companion", "env", ".env", "DISCORD_BOT_TOKEN"),
		c("discord.allowed_users", "channels", "Discord 允許的使用者 ID", "逗號分隔", "string", "restart_companion", "env", ".env", "DISCORD_ALLOWED_USERS"),
		// ---- her memory engine (kokoro.json)
		c("kokoro.subject", "memory", "記憶主詞", "每則關於你的記憶都以這個詞當主詞（預設 製作人）。改了會改寫並重新嵌入既有記憶。", "string", "migrate_subject", "json", "kokoro.json", "subject"),
		c("kokoro.tokenizer", "memory", "關鍵字分詞", "bigram（預設，繁中最準）或 jieba；改了會重建索引", "select", "reindex", "json", "kokoro.json", "tokenizer", "bigram", "jieba"),
		c("kokoro.context_k", "memory", "每輪注入的記憶數", "", "int", "restart_companion", "json", "kokoro.json", "context_k"),
		c("kokoro.max_candidates", "memory", "記憶管線候選數", "每輪給 L2 看的相似記憶數", "int", "restart_companion", "json", "kokoro.json", "max_candidates"),
		withDefault(c("kokoro.short_layer", "memory", "短期紀錄層", "每回合由同一次整理產生一行有日期的紀錄；關掉就只留長期事實", "bool", "restart_companion", "json", "kokoro.json", "short_layer"), true),
		withDefault(c("kokoro.short_k", "memory", "注入的短期紀錄數", "每回合搜尋短期層取前幾則（長期層用「注入記憶數」）", "int", "restart_companion", "json", "kokoro.json", "short_k"), 5),
		withDefault(c("kokoro.short_cap", "memory", "短期紀錄上限", "環形保留最新 N 則，舊的自動刪除", "int", "restart_companion", "json", "kokoro.json", "short_cap"), 1000),
		c("kokoro.consent_turns", "memory", "封存話題同意後開放的輪數", "", "int", "restart_companion", "json", "kokoro.json", "consent_turns"),
		c("kokoro.high", "memory", "[high] 門檻（cosine）", "", "float", "restart_companion", "json", "kokoro.json", "high"),
		c("kokoro.drop", "memory", "捨棄門檻（cosine）", "低於此值且關鍵字也沒命中就不注入", "float", "restart_companion", "json", "kokoro.json", "drop"),
		c("kokoro.rrf_k", "memory", "RRF k", "", "float", "restart_companion", "json", "kokoro.json", "rrf_k"),
		c("kokoro.oversample", "memory", "每路過取倍數", "", "int", "restart_companion", "json", "kokoro.json", "oversample"),
		c("kokoro.llm.base_url", "memory", "記憶管線模型 API", "L2 用的 OpenAI 相容端點", "string", "restart_companion", "json", "kokoro.json", "llm.base_url"),
		c("kokoro.llm.model", "memory", "記憶管線模型", "", "string", "restart_companion", "json", "kokoro.json", "llm.model"),
		c("kokoro.llm.api_key", "memory", "記憶管線 API key", "", "secret", "restart_companion", "json", "kokoro.json", "llm.api_key"),
		c("kokoro.llm.timeout", "memory", "記憶管線逾時（秒）", "", "float", "restart_companion", "json", "kokoro.json", "llm.timeout"),
		c("kokoro.llm_retries", "memory", "記憶管線重試次數", "空回覆／非 JSON 時重試", "int", "restart_companion", "json", "kokoro.json", "llm_retries"),
		c("kokoro.embedder.base_url", "memory", "嵌入模型 API", "", "string", "restart_companion", "json", "kokoro.json", "embedder.base_url"),
		c("kokoro.embedder.model", "memory", "嵌入模型", "改了要重新嵌入整個記憶庫", "string", "reembed", "json", "kokoro.json", "embedder.model"),
		c("kokoro.embedder.dims", "memory", "嵌入維度", "", "int", "reembed", "json", "kokoro.json", "embedder.dims"),
		c("kokoro.tools", "memory", "給她記憶工具", "kokoro_search / kokoro_forget", "bool", "restart_companion", "json", "kokoro.json", "tools"),
		c("kokoro.backup_dir", "memory", "記憶快照資料夾", "相對她的資料夾；可指向雲端同步資料夾", "string", "restart_companion", "json", "kokoro.json", "backup_dir"),
		c("kokoro.snapshot_text_only", "memory", "快照不含向量", "小很多；還原時重新嵌入", "bool", "restart_companion", "json", "kokoro.json", "snapshot_text_only"),
		c("kokoro.log_searches", "memory", "記錄每次檢索", "", "bool", "restart_companion", "json", "kokoro.json", "log_searches"),
		c("kokoro.log_pipeline", "memory", "記錄記憶管線決策", "", "bool", "restart_companion", "json", "kokoro.json", "log_pipeline"),
		c("kokoro.log_retention_days", "memory", "日誌保留天數", "", "int", "restart_companion", "json", "kokoro.json", "log_retention_days"),
		c("kokoro.slow_ms", "memory", "慢查詢警告門檻（ms）", "", "float", "restart_companion", "json", "kokoro.json", "slow_ms"),
		// ---- the agency backend (556d.toml, shim routing) — restart the app
		a("daemon.port", "backend", "556d 連接埠", "", "int", "restart_app", "toml", "556d.toml", "daemon.port"),
		a("daemon.profile", "backend", "預設開啟的成員", "設定檔沒有選擇時視窗開在誰身上", "string", "restart_app", "toml", "556d.toml", "daemon.profile"),
		a("shim.port", "backend", "shim 連接埠", "", "int", "restart_app", "toml", "556d.toml", "shim.port"),
		a("embedder.enabled", "backend", "啟動嵌入模型 sidecar", "", "bool", "restart_app", "toml", "556d.toml", "embedder.enabled"),
		a("embedder.port", "backend", "嵌入模型連接埠", "", "int", "restart_app", "toml", "556d.toml", "embedder.port"),
		a("embedder.model", "backend", "嵌入模型檔（GGUF）", "", "string", "restart_app", "toml", "556d.toml", "embedder.model"),
		a("hermes.exe", "backend", "Hermes 執行檔", "", "string", "restart_app", "toml", "556d.toml", "hermes.exe"),
		a("shim.lane.556", "backend", "lane 556 → 後端", "shim/routing.json", "string", "restart_app", "json", "shim/routing.json", "lanes.556"),
		a("shim.lane.pro", "backend", "lane pro → 後端", "", "string", "restart_app", "json", "shim/routing.json", "lanes.pro"),
		a("shim.lane.code", "backend", "lane code → 後端", "", "string", "restart_app", "json", "shim/routing.json", "lanes.code"),
		a("shim.default", "backend", "預設後端", "", "string", "restart_app", "json", "shim/routing.json", "default"),
	}
}

func (a *API) knobPath(k Knob) (string, error) {
	switch {
	case k.root == "repo":
		return filepath.Join(filepath.Dir(a.settings.home), filepath.FromSlash(k.file)), nil
	case k.Scope == "companion":
		dir := a.settings.profileDir()
		if dir == "" {
			return "", errors.New("no companion selected")
		}
		return filepath.Join(dir, k.file), nil
	default:
		return filepath.Join(a.settings.home, k.file), nil
	}
}

// ---------------------------------------------------------------- read
func readKnob(k Knob, path string) (any, bool) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, false
	}
	var v any
	var ok bool
	switch k.kind {
	case "yaml":
		var doc yaml.Node
		if yaml.Unmarshal(raw, &doc) != nil || doc.Kind != yaml.DocumentNode || len(doc.Content) == 0 {
			return nil, false
		}
		if n := yamlGet(doc.Content[0], strings.Split(k.path, ".")); n != nil {
			v, ok = n.Value, true
		}
	case "json":
		var m map[string]any
		if json.Unmarshal(raw, &m) != nil {
			return nil, false
		}
		v, ok = jsonGet(m, strings.Split(k.path, "."))
	case "env":
		for _, line := range strings.Split(string(raw), "\n") {
			line = strings.TrimSpace(line)
			if key, val, found := strings.Cut(line, "="); found && strings.TrimSpace(key) == k.path {
				v, ok = strings.Trim(strings.TrimSpace(val), `"'`), true
			}
		}
	case "toml":
		v, ok = tomlGet(string(raw), k.path)
	}
	if !ok {
		return nil, false
	}
	return coerce(k.Type, v), true
}

func coerce(typ string, v any) any {
	s := fmt.Sprint(v)
	switch typ {
	case "int":
		if f, ok := v.(float64); ok {
			return int(f)
		}
		n, err := strconv.Atoi(strings.TrimSpace(s))
		if err != nil {
			return v
		}
		return n
	case "float":
		f, err := strconv.ParseFloat(strings.TrimSpace(s), 64)
		if err != nil {
			return v
		}
		return f
	case "bool":
		if b, ok := v.(bool); ok {
			return b
		}
		return strings.EqualFold(strings.TrimSpace(s), "true")
	default:
		return s
	}
}

func yamlGet(node *yaml.Node, path []string) *yaml.Node {
	for _, key := range path {
		if node.Kind != yaml.MappingNode {
			return nil
		}
		var next *yaml.Node
		for j := 0; j+1 < len(node.Content); j += 2 {
			if node.Content[j].Value == key {
				next = node.Content[j+1]
				break
			}
		}
		if next == nil {
			return nil
		}
		node = next
	}
	if node.Kind != yaml.ScalarNode {
		return nil
	}
	return node
}

func jsonGet(m map[string]any, path []string) (any, bool) {
	var cur any = m
	for _, key := range path {
		mm, ok := cur.(map[string]any)
		if !ok {
			return nil, false
		}
		cur, ok = mm[key]
		if !ok {
			return nil, false
		}
	}
	return cur, true
}

var tomlSection = regexp.MustCompile(`^\s*\[([^\]]+)\]`)

func tomlGet(text, path string) (any, bool) {
	section, key, _ := strings.Cut(path, ".")
	in := false
	for _, line := range strings.Split(text, "\n") {
		if m := tomlSection.FindStringSubmatch(line); m != nil {
			in = m[1] == section
			continue
		}
		if !in {
			continue
		}
		k, v, found := strings.Cut(line, "=")
		if !found || strings.TrimSpace(k) != key {
			continue
		}
		v = strings.TrimSpace(v)
		if i := strings.Index(v, " #"); i >= 0 && !strings.HasPrefix(v, `"`) {
			v = strings.TrimSpace(v[:i])
		}
		if strings.HasPrefix(v, `"`) {
			if end := strings.LastIndex(v, `"`); end > 0 {
				v = v[1:end]
			}
		}
		return v, true
	}
	return nil, false
}

// ---------------------------------------------------------------- write
func writeKnob(k Knob, path string, value any) error {
	switch k.kind {
	case "yaml":
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
		setScalar(doc.Content[0], strings.Split(k.path, "."), fmt.Sprint(value))
		out, err := yaml.Marshal(&doc)
		if err != nil {
			return err
		}
		return os.WriteFile(path, out, 0o644)
	case "json":
		m := map[string]any{}
		if raw, err := os.ReadFile(path); err == nil {
			_ = json.Unmarshal(raw, &m)
		}
		cur := m
		parts := strings.Split(k.path, ".")
		for _, key := range parts[:len(parts)-1] {
			next, ok := cur[key].(map[string]any)
			if !ok {
				next = map[string]any{}
				cur[key] = next
			}
			cur = next
		}
		cur[parts[len(parts)-1]] = value
		out, _ := json.MarshalIndent(m, "", "  ")
		return os.WriteFile(path, out, 0o644)
	case "env":
		raw, _ := os.ReadFile(path)
		lines := strings.Split(strings.ReplaceAll(string(raw), "\r\n", "\n"), "\n")
		line := k.path + "=" + fmt.Sprint(value)
		done := false
		for i, l := range lines {
			if key, _, found := strings.Cut(l, "="); found && strings.TrimSpace(key) == k.path {
				lines[i], done = line, true
				break
			}
		}
		if !done {
			lines = append(lines, line)
		}
		return os.WriteFile(path, []byte(strings.TrimRight(strings.Join(lines, "\n"), "\n")+"\n"), 0o600)
	case "toml":
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		section, key, _ := strings.Cut(k.path, ".")
		lit := fmt.Sprint(value)
		if k.Type == "string" || k.Type == "select" || k.Type == "secret" {
			lit = strconv.Quote(lit)
		}
		lines := strings.Split(strings.ReplaceAll(string(raw), "\r\n", "\n"), "\n")
		in, done, secStart := false, false, -1
		for i, l := range lines {
			if m := tomlSection.FindStringSubmatch(l); m != nil {
				if in && !done { // leaving our section without finding the key: insert before this header
					lines = append(lines[:i], append([]string{key + " = " + lit}, lines[i:]...)...)
					done = true
					break
				}
				in = m[1] == section
				if in {
					secStart = i
				}
				continue
			}
			if !in {
				continue
			}
			if kk, _, found := strings.Cut(l, "="); found && strings.TrimSpace(kk) == key {
				lines[i], done = key+" = "+lit, true
				break
			}
		}
		if !done {
			if secStart < 0 {
				lines = append(lines, "", "["+section+"]", key+" = "+lit)
			} else {
				lines = append(lines, key+" = "+lit)
			}
		}
		return os.WriteFile(path, []byte(strings.TrimRight(strings.Join(lines, "\n"), "\n")+"\n"), 0o644)
	}
	return fmt.Errorf("unknown knob kind %q", k.kind)
}

// ---------------------------------------------------------------- HTTP
func (a *API) configHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, PUT, OPTIONS") {
		return
	}
	all := knobs()
	byKey := map[string]int{}
	for i, k := range all {
		byKey[k.Key] = i
	}
	switch r.Method {
	case http.MethodGet:
		out := make([]Knob, 0, len(all))
		for _, k := range all {
			p, err := a.knobPath(k)
			if err == nil {
				if v, ok := readKnob(k, p); ok {
					if k.Type == "secret" {
						set := fmt.Sprint(v) != ""
						k.Set, k.Value = &set, ""
					} else {
						k.Value = v
					}
				} else if k.Default != nil {
					k.Value = k.Default // not in the file yet: show the effective default
				}
			}
			out = append(out, k)
		}
		writeJSON(w, 200, map[string]any{"knobs": out, "companion": a.selectedName()})
	case http.MethodPut:
		var patch map[string]any
		if err := decodeJSON(r, &patch); err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		effects := map[string]bool{}
		var errs []string
		for key, val := range patch {
			i, ok := byKey[key]
			if !ok {
				errs = append(errs, key+": unknown knob")
				continue
			}
			k := all[i]
			if k.Type == "secret" && strings.TrimSpace(fmt.Sprint(val)) == "" {
				continue // empty secret = keep
			}
			p, err := a.knobPath(k)
			if err != nil {
				errs = append(errs, key+": "+err.Error())
				continue
			}
			if err := writeKnob(k, p, coerce(k.Type, val)); err != nil {
				errs = append(errs, key+": "+err.Error())
				continue
			}
			effects[k.Effect] = true
			if k.Effect == "reembed" || k.Effect == "reindex" || k.Effect == "migrate_subject" {
				effects["restart_companion"] = true // the engine applies it when she starts
			}
		}
		writeJSON(w, 200, map[string]any{"effects": effects, "errors": errs})
	default:
		writeJSON(w, 405, map[string]any{"error": "method not allowed"})
	}
}
