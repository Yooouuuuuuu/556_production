package api

import (
	"net/http"
	"strings"

	"github.com/Yooouuuuuuu/556_production/556d/internal/companions"
	"github.com/Yooouuuuuuu/556_production/556d/internal/hermesapi"
)

// Roster + selection. Chat, history, memory and the companion settings all act on the
// SELECTED companion (the one the chat window shows); the avatar follows it.
//   GET  /api/companions                 roster with active state and channels
//   POST /api/companions/{name}/start    start her: one `hermes gateway run` (API server + her channels)
//   POST /api/companions/{name}/stop     stop her
//   GET  /api/selected | PUT {"name"}    which companion the windows are on (persisted)

func (a *API) companionsHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, POST, OPTIONS") {
		return
	}
	rest := strings.Trim(strings.TrimPrefix(r.URL.Path, "/api/companions"), "/")
	if rest == "" {
		if r.Method != http.MethodGet {
			writeJSON(w, 405, map[string]any{"error": "GET only"})
			return
		}
		writeJSON(w, 200, map[string]any{"companions": a.mgr.List(), "selected": a.selectedName()})
		return
	}
	name, action, _ := strings.Cut(rest, "/")
	if r.Method != http.MethodPost {
		writeJSON(w, 405, map[string]any{"error": "POST only"})
		return
	}
	switch action {
	case "start":
		info, err := a.mgr.Start(name)
		if err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		if a.selectedName() == "" {
			a.setSelected(name) // first start also selects her
		}
		go a.openConversation(name) // her ONE conversation is opened by the start, never by a message
		a.emit(map[string]any{"type": "companion.lifecycle", "companion": name, "active": true})
		writeJSON(w, 200, map[string]any{"companion": info})
	case "stop":
		if err := a.mgr.Stop(name); err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		a.forgetSession(name)
		a.emit(map[string]any{"type": "companion.lifecycle", "companion": name, "active": false})
		writeJSON(w, 200, map[string]any{"companion": a.mgr.Info(name)})
	default:
		writeJSON(w, 404, map[string]any{"error": "unknown action " + action})
	}
}

func (a *API) selectedHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, PUT, OPTIONS") {
		return
	}
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, 200, map[string]any{"selected": a.selectedName()})
	case http.MethodPut:
		var body struct {
			Name string `json:"name"`
		}
		if err := decodeJSON(r, &body); err != nil || !a.mgr.Exists(body.Name) {
			writeJSON(w, 400, map[string]any{"error": "unknown companion"})
			return
		}
		a.setSelected(body.Name)
		writeJSON(w, 200, map[string]any{"selected": body.Name, "companion": a.mgr.Info(body.Name)})
	default:
		writeJSON(w, 405, map[string]any{"error": "method not allowed"})
	}
}

func (a *API) selectedName() string { return a.settings.Get().SelectedCompanion }

func (a *API) setSelected(name string) {
	a.settings.SetSelected(name, a.mgr.Dir(name))
	info := a.mgr.Info(name)
	a.emit(map[string]any{"type": "companion.selected", "companion": name, "display_name": info.DisplayName,
		"avatar_model_url": "/" + strings.TrimPrefix(info.AvatarModel, "/")})
}

// target resolves which companion a request addresses: ?companion= / X-556-Companion, else the
// selected one. She must be active to have a Hermes client.
func (a *API) target(r *http.Request) (string, *hermesapi.Client, error) {
	name := r.URL.Query().Get("companion")
	if name == "" {
		name = r.Header.Get("X-556-Companion")
	}
	if name == "" {
		name = a.selectedName()
	}
	if name == "" {
		return "", nil, errNoCompanion
	}
	cl := a.mgr.Client(name)
	if cl == nil {
		return name, nil, errNotActive(name)
	}
	return name, cl, nil
}

type companionError string

func (e companionError) Error() string { return string(e) }

const errNoCompanion = companionError("no companion selected — pick one on the roster and start her")

func errNotActive(name string) error { return companionError(name + " is not active — start her on the roster") }

var _ = companions.Info{}
