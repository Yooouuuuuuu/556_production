package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"path/filepath"
	"strconv"
	"sync"
	"time"

	"github.com/Yooouuuuuuu/556_production/556d/internal/memory"
)

// Memory page API (view + delete only, by design — edits happen in conversation so dedup and
// re-embedding run in the engine). Reads the selected companion's KeepsakeDB file directly;
// deletes go through the store's command queue to the owning Hermes process.

var (
	memMu     sync.Mutex
	memStores = map[string]*memory.Store{}
)

// memoryStoreFor resolves the store of a companion: home/profiles/<p>/memory/<p>.db
// (kokoro.json's db is memory/{profile}.db inside her HERMES_HOME).
func (a *API) memoryStoreFor(name string) *memory.Store {
	memMu.Lock()
	defer memMu.Unlock()
	if st := memStores[name]; st != nil {
		return st
	}
	st := memory.New(filepath.Join(a.mgr.Dir(name), "memory", name+".db"))
	memStores[name] = st
	return st
}

func (a *API) memoryTarget(r *http.Request) (string, *memory.Store, error) {
	name := r.URL.Query().Get("companion")
	if name == "" {
		name = r.Header.Get("X-556-Companion")
	}
	if name == "" {
		name = a.selectedName()
	}
	if name == "" || !a.mgr.Exists(name) {
		return "", nil, errNoCompanion
	}
	return name, a.memoryStoreFor(name), nil
}

func (a *API) memoryList(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, OPTIONS") {
		return
	}
	if r.Method != http.MethodGet {
		http.Error(w, "GET only", http.StatusMethodNotAllowed)
		return
	}
	name, st, err := a.memoryTarget(r)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"exists": false, "companion": "", "memories": []any{}, "tags": []any{}, "note": err.Error()})
		return
	}
	if !st.Exists() {
		writeJSON(w, http.StatusOK, map[string]any{"exists": false, "companion": name, "path": st.Path(), "memories": []any{}, "tags": []any{}})
		return
	}
	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	items, err := st.List(r.Context(), q.Get("q"), q.Get("tag"), q.Get("archived") == "1", limit, q.Get("layer"))
	if err != nil {
		writeError(w, err)
		return
	}
	tags, _ := st.Tags(r.Context())
	stats, _ := st.Stats(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{"exists": true, "companion": name, "stats": stats, "tags": tags, "memories": items})
}

func (a *API) memoryDelete(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		IDs    []int64 `json:"ids"`
		Reason string  `json:"reason"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || len(body.IDs) == 0 {
		writeError(w, errors.New("body must be {ids: [..], reason?: string}"))
		return
	}
	if body.Reason == "" {
		body.Reason = "deleted from the 556 memory page"
	}
	_, st, err := a.memoryTarget(r)
	if err != nil {
		writeError(w, err)
		return
	}
	if !st.Exists() {
		writeError(w, memory.ErrNoStore)
		return
	}
	status, count, cmdID, err := st.Delete(r.Context(), body.IDs, body.Reason, "556-app", 4*time.Second)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": status, "count": count, "command_id": cmdID})
}

func writeError(w http.ResponseWriter, err error) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusBadRequest)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
}
