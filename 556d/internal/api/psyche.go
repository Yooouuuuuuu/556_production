package api

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
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
	writeJSON(w, http.StatusOK, out)
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
			if s, ok := v.(string); ok && (c == "payload" || c == "data") && json.Valid([]byte(s)) {
				m[c] = json.RawMessage(s)
				continue
			}
			m[c] = v
		}
		out = append(out, m)
	}
	return out
}
