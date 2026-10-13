package api

import (
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// 狀態 page API: a read-only view of her psyche.db (the psyche plugin inside her Hermes process is
// the single writer; 556d only reads, like the memory page reads her KeepsakeDB file).

type psycheRow = map[string]any

func (a *API) psychePath(r *http.Request) (string, string, error) {
	name := r.URL.Query().Get("companion")
	if name == "" {
		name = r.Header.Get("X-556-Companion")
	}
	if name == "" {
		name = a.selectedName()
	}
	if name == "" || !a.mgr.Exists(name) {
		return "", "", errNoCompanion
	}
	return name, filepath.Join(a.mgr.Dir(name), "psyche.db"), nil
}

func (a *API) psycheHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, OPTIONS") {
		return
	}
	if r.Method != http.MethodGet {
		http.Error(w, "GET only", http.StatusMethodNotAllowed)
		return
	}
	name, path, err := a.psychePath(r)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": err.Error()})
		return
	}
	out := map[string]any{"companion": name, "exists": false}
	if st, err := os.Stat(path); err != nil || st.Size() == 0 {
		writeJSON(w, http.StatusOK, out)
		return
	}
	db, err := sql.Open("sqlite", "file:"+filepath.ToSlash(path)+"?mode=ro&_pragma=busy_timeout(5000)")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	defer db.Close()
	out["exists"] = true

	var hb sql.NullFloat64
	_ = db.QueryRow("SELECT heartbeat FROM owner WHERE id = 1").Scan(&hb)
	out["running"] = hb.Valid && float64(time.Now().Unix())-hb.Float64 < 20

	var state sql.NullString
	var snapAt sql.NullFloat64
	_ = db.QueryRow("SELECT state, at FROM snapshots ORDER BY tick DESC, id DESC LIMIT 1").Scan(&state, &snapAt)
	if state.Valid {
		out["snapshot"] = json.RawMessage(state.String)
		out["snapshot_at"] = snapAt.Float64
	}
	out["instances"] = psycheQuery(db, "SELECT id, born_at, type, target, cause, intensity0, half_life_h, stack_key, loop_id, resolved_at, resolved_by FROM instances ORDER BY born_at DESC LIMIT 60",
		"id", "born_at", "type", "target", "cause", "intensity0", "half_life_h", "stack_key", "loop_id", "resolved_at", "resolved_by")
	out["loops"] = psycheQuery(db, "SELECT id, what, origin, cue_time, importance, state, created_at, closed_at FROM loops ORDER BY created_at DESC LIMIT 40",
		"id", "what", "origin", "cue_time", "importance", "state", "created_at", "closed_at")
	out["events"] = psycheQuery(db, "SELECT id, at, kind, counterpart, payload FROM events ORDER BY id DESC LIMIT 60",
		"id", "at", "kind", "counterpart", "payload")
	out["appraisals"] = psycheQuery(db, "SELECT id, at, turn_id, platform, data, error, ms, applied_tick FROM appraisals ORDER BY id DESC LIMIT 20",
		"id", "at", "turn_id", "platform", "data", "error", "ms", "applied_tick")
	out["checks"] = psycheQuery(db, "SELECT id, at, platform, hits, excerpt FROM checks ORDER BY id DESC LIMIT 20", "id", "at", "platform", "hits", "excerpt")
	var nchecks sql.NullInt64
	_ = db.QueryRow("SELECT COUNT(*) FROM checks").Scan(&nchecks)
	out["checks_total"] = nchecks.Int64
	if raw, rerr := os.ReadFile(filepath.Join(filepath.Dir(path), "psyche.json")); rerr == nil {
		var m struct {
			Proactive struct {
				Vis *bool `json:"inter_agent_visibility"`
			} `json:"proactive"`
		}
		if json.Unmarshal([]byte(strings.TrimPrefix(string(raw), "\xEF\xBB\xBF")), &m) == nil && m.Proactive.Vis != nil {
			out["inter_agent_visibility"] = *m.Proactive.Vis
		}
	}
	writeJSON(w, http.StatusOK, out)
}

// isSilence: her answer to an event turn that means "not now" (events.py SILENCE).
func isSilence(s string) bool {
	s = strings.Trim(strings.TrimSpace(s), "「」\"'()（）")
	if s == "" || s == "沉默" {
		return true
	}
	for _, e := range []string{"Model generated invalid tool call", "does not exist. Available tools", "Tool '", "[error", "Error:"} {
		if strings.HasPrefix(s, e) || strings.Contains(s, e) {
			return true // a platform error, not her words
		}
	}
	return false
}

// hotPaths are the psyche.json keys the engine re-reads every tick; anything else needs her restart.
var hotPaths = []string{"proactive", "life.busyness_mode", "cares_about"}

func isHot(path string) bool {
	for _, h := range hotPaths {
		if path == h || strings.HasPrefix(path, h+".") || strings.HasPrefix(h, path+".") {
			return true
		}
	}
	return false
}

// mergeInto merges patch into dst recursively and reports whether a non-hot key changed.
func mergeInto(dst, patch map[string]any, prefix string) (restart bool) {
	for k, v := range patch {
		path := k
		if prefix != "" {
			path = prefix + "." + k
		}
		pm, pok := v.(map[string]any)
		dm, dok := dst[k].(map[string]any)
		if pok && dok {
			if mergeInto(dm, pm, path) {
				restart = true
			}
			continue
		}
		old, _ := json.Marshal(dst[k])
		new, _ := json.Marshal(v)
		if string(old) != string(new) {
			dst[k] = v
			if !isHot(path) {
				restart = true
			}
		}
	}
	return restart
}

// 主動 settings: GET/PUT psyche.json in her profile (written with defaults by the engine at her first start).
func (a *API) psycheSettingsHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, PUT, OPTIONS") {
		return
	}
	name, dbPath, err := a.psychePath(r)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": err.Error()})
		return
	}
	p := filepath.Join(filepath.Dir(dbPath), "psyche.json")
	cur := map[string]any{}
	exists := false
	if raw, rerr := os.ReadFile(p); rerr == nil {
		exists = json.Unmarshal([]byte(strings.TrimPrefix(string(raw), "\ufeff")), &cur) == nil
	}
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, http.StatusOK, map[string]any{"companion": name, "exists": exists, "settings": cur})
	case http.MethodPut:
		var patch map[string]any
		if derr := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&patch); derr != nil {
			http.Error(w, "bad json", http.StatusBadRequest)
			return
		}
		restart := mergeInto(cur, patch, "")
		out, _ := json.MarshalIndent(cur, "", "  ")
		if werr := os.WriteFile(p, append(out, '\n'), 0o644); werr != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]any{"error": werr.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"companion": name, "settings": cur, "restart_required": restart})
	default:
		http.Error(w, "GET or PUT", http.StatusMethodNotAllowed)
	}
}

// Commands for the engine (single writer): 556d only appends to the commands table, like memory deletes.
func (a *API) psycheCommandHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	name, dbPath, err := a.psychePath(r)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": err.Error()})
		return
	}
	var body struct {
		Op      string         `json:"op"`
		Payload map[string]any `json:"payload"`
	}
	if derr := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); derr != nil || body.Op == "" {
		http.Error(w, "bad json", http.StatusBadRequest)
		return
	}
	if st, serr := os.Stat(dbPath); serr != nil || st.Size() == 0 {
		writeJSON(w, http.StatusConflict, map[string]any{"error": "no psyche.db yet — start her once"})
		return
	}
	db, err := sql.Open("sqlite", "file:"+filepath.ToSlash(dbPath)+"?_pragma=busy_timeout(5000)")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	defer db.Close()
	pl, _ := json.Marshal(body.Payload)
	res, err := db.Exec("INSERT INTO commands(op, payload, requested_at, requested_by) VALUES (?, ?, ?, ?)", body.Op, string(pl), float64(time.Now().UnixNano())/1e9, "556d")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	id, _ := res.LastInsertId()
	writeJSON(w, http.StatusOK, map[string]any{"companion": name, "id": id, "queued": true})
}

// psycheQuery returns rows as maps; TEXT columns named payload/data are passed through as JSON.
func psycheQuery(db *sql.DB, q string, cols ...string) []psycheRow {
	rows, err := db.Query(q)
	if err != nil {
		return []psycheRow{}
	}
	defer rows.Close()
	out := []psycheRow{}
	for rows.Next() {
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			continue
		}
		m := psycheRow{}
		for i, c := range cols {
			v := vals[i]
			if b, ok := v.([]byte); ok {
				v = string(b)
			}
			if s, ok := v.(string); ok && (c == "payload" || c == "data" || c == "hits") && json.Valid([]byte(s)) {
				m[c] = json.RawMessage(s)
				continue
			}
			m[c] = v
		}
		out = append(out, m)
	}
	return out
}
