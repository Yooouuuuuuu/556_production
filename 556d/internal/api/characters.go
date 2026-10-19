package api

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

// The create-character page (設定 → 角色 → 新角色) drives the soul skill (tools/soul_writer.py,
// docs/prompt/prompt.md §2.9) through 556d. A character package lives under <root>/characters/<id>/:
// describe/*.md in the person's words, profile.json (numbers and choices: proposed by the skill,
// confirmed by the person), and the generated outputs (SOUL.md, seeds.jsonl, people/, psyche.json,
// build/). The skill runs as a subprocess of the venv's python — one job per package at a time, its
// output in build/run.log — and install runs install-character.ps1 + seed-memories.py the same way.
//   GET  /api/characters                     packages + the describe template prompts
//   POST /api/characters                     {id, display_name, pronoun, avatar, from_example} → init
//   GET  /api/characters/{id}                describe texts, profile, build outputs, SOUL, job state
//   PUT  /api/characters/{id}/describe       {files: {stem: text}}
//   PUT  /api/characters/{id}/profile        {profile: {...}} (confirmed values; proposals are kept)
//   POST /api/characters/{id}/run            {phase, model, yes, force} → background job
//   POST /api/characters/{id}/install        → background job (profile created, files copied, seeds loaded)
//   GET  /api/characters/{id}/job            {running, kind, phase, model, started_at, exit_code, log}

var charID = regexp.MustCompile(`^[a-z0-9_-]+$`)

var describeStems = []string{"01-她是誰", "02-背景", "03-發生過的事", "04-說話的方式", "05-怎麼想", "06-跟人相處", "07-喜好", "08-立場", "09-身邊的人", "10-其他"}

var skillPhases = []string{"intake", "structure", "thinking", "voice", "reactions", "parts", "assemble", "verify"}

type charJob struct {
	mu        sync.Mutex
	running   bool
	kind      string // run | install
	phase     string
	model     string
	startedAt time.Time
	exitCode  int
	log       strings.Builder
	err       string
}

func (a *API) charactersDir() string { return filepath.Join(a.mgr.Root(), "characters") }

func (a *API) venvPython() string {
	return filepath.Join(filepath.Dir(a.mgr.HermesExe()), "python.exe")
}

func (a *API) charJob(id string) *charJob {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.jobs == nil {
		a.jobs = map[string]*charJob{}
	}
	j, ok := a.jobs[id]
	if !ok {
		j = &charJob{}
		a.jobs[id] = j
	}
	return j
}

// describeTemplate reads the template prompts (the HTML comment of each templates/character/describe/*.md).
func (a *API) describeTemplate() map[string]string {
	out := map[string]string{}
	dir := filepath.Join(a.mgr.Root(), "templates", "character", "describe")
	for _, stem := range describeStems {
		b, err := os.ReadFile(filepath.Join(dir, stem+".md"))
		if err != nil {
			continue
		}
		s := string(b)
		if i := strings.Index(s, "<!--"); i >= 0 {
			if j := strings.Index(s[i:], "-->"); j >= 0 {
				out[stem] = strings.TrimSpace(s[i+4 : i+j])
				continue
			}
		}
		out[stem] = ""
	}
	return out
}

var htmlComment = regexp.MustCompile(`(?s)<!--.*?-->`)

// readDescribe returns the person's words per stem (template prompts and the title line stripped).
func readDescribe(dir string) map[string]string {
	out := map[string]string{}
	for _, stem := range describeStems {
		b, err := os.ReadFile(filepath.Join(dir, "describe", stem+".md"))
		if err != nil {
			out[stem] = ""
			continue
		}
		s := htmlComment.ReplaceAllString(strings.TrimPrefix(string(b), "\ufeff"), "")
		var lines []string
		for _, ln := range strings.Split(s, "\n") {
			if strings.HasPrefix(ln, "# ") {
				continue
			}
			lines = append(lines, strings.TrimRight(ln, "\r"))
		}
		out[stem] = strings.TrimSpace(strings.Join(lines, "\n"))
	}
	return out
}

func readJSONFile(p string) any {
	b, err := os.ReadFile(p)
	if err != nil {
		return nil
	}
	var v any
	if json.Unmarshal([]byte(strings.TrimPrefix(string(b), "\ufeff")), &v) != nil {
		return nil
	}
	return v
}

func readTextFile(p string) string {
	b, err := os.ReadFile(p)
	if err != nil {
		return ""
	}
	return strings.TrimPrefix(string(b), "\ufeff")
}

func fileExists(p string) bool {
	st, err := os.Stat(p)
	return err == nil && !st.IsDir()
}

func shortSHA(p string) string {
	b, err := os.ReadFile(p)
	if err != nil {
		return ""
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])[:16]
}

// staleInputs lists the inputs that changed since soul.lock.json was written: the SOUL, seeds and psyche.json
// on disk were made from an older description or older confirmed numbers.
func staleInputs(dir string) []string {
	lock, _ := readJSONFile(filepath.Join(dir, "soul.lock.json")).(map[string]any)
	inputs, _ := lock["inputs"].(map[string]any)
	if inputs == nil {
		return []string{}
	}
	var out []string
	for rel, v := range inputs {
		want, _ := v.(string)
		if shortSHA(filepath.Join(dir, filepath.FromSlash(rel))) != want {
			out = append(out, rel)
		}
	}
	sort.Strings(out)
	if out == nil {
		out = []string{}
	}
	return out
}

// packageSummary is one row of the list: what is filled, which phases ran, whether she is installed.
func (a *API) packageSummary(id string) map[string]any {
	dir := filepath.Join(a.charactersDir(), id)
	cj, _ := readJSONFile(filepath.Join(dir, "companion.json")).(map[string]any)
	desc := readDescribe(dir)
	filled := 0
	for _, v := range desc {
		if v != "" {
			filled++
		}
	}
	var phases []string
	for _, ph := range skillPhases {
		if ph == "assemble" {
			if fileExists(filepath.Join(dir, "SOUL.md")) {
				phases = append(phases, ph)
			}
			continue
		}
		if fileExists(filepath.Join(dir, "build", ph+".json")) {
			phases = append(phases, ph)
		}
	}
	if phases == nil {
		phases = []string{}
	}
	j := a.charJob(id)
	j.mu.Lock()
	running, kind := j.running, j.kind
	j.mu.Unlock()
	display, _ := cj["display_name"].(string)
	avatar, _ := cj["avatar_model"].(string)
	return map[string]any{
		"id": id, "display_name": display, "avatar_model": avatar, "describe_filled": filled, "describe_total": len(describeStems),
		"phases": phases, "has_soul": fileExists(filepath.Join(dir, "SOUL.md")), "installed": a.mgr.Exists(id),
		"running": running, "job_kind": kind, "lock": readJSONFile(filepath.Join(dir, "soul.lock.json")),
		"stale": staleInputs(dir),
	}
}

func (a *API) charactersHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, POST, PUT, OPTIONS") {
		return
	}
	rest := strings.Trim(strings.TrimPrefix(r.URL.Path, "/api/characters"), "/")
	if rest == "" {
		switch r.Method {
		case http.MethodGet:
			entries, _ := os.ReadDir(a.charactersDir())
			var ids []string
			for _, e := range entries {
				if e.IsDir() && charID.MatchString(e.Name()) && (fileExists(filepath.Join(a.charactersDir(), e.Name(), "companion.json")) || fileExists(filepath.Join(a.charactersDir(), e.Name(), "SOUL.md"))) {
					ids = append(ids, e.Name())
				}
			}
			sort.Strings(ids)
			list := make([]map[string]any, 0, len(ids))
			for _, id := range ids {
				list = append(list, a.packageSummary(id))
			}
			writeJSON(w, 200, map[string]any{"characters": list, "template": a.describeTemplate(), "models": []string{"gemini", "claude", "gemini-pro", "opus"}, "phases": skillPhases})
		case http.MethodPost:
			a.createCharacter(w, r)
		default:
			writeJSON(w, 405, map[string]any{"error": "GET or POST"})
		}
		return
	}
	id, action, _ := strings.Cut(rest, "/")
	if !charID.MatchString(id) {
		writeJSON(w, 400, map[string]any{"error": "bad id"})
		return
	}
	dir := filepath.Join(a.charactersDir(), id)
	if st, err := os.Stat(dir); err != nil || !st.IsDir() {
		writeJSON(w, 404, map[string]any{"error": "no such character package: " + id})
		return
	}
	switch {
	case action == "" && r.Method == http.MethodGet:
		a.characterDetail(w, id, dir)
	case action == "describe" && r.Method == http.MethodPut:
		var body struct {
			Files map[string]string `json:"files"`
		}
		if err := decodeJSON(r, &body); err != nil {
			writeJSON(w, 400, map[string]any{"error": "bad json"})
			return
		}
		_ = os.MkdirAll(filepath.Join(dir, "describe"), 0o755)
		n := 0
		for _, stem := range describeStems {
			text, ok := body.Files[stem]
			if !ok {
				continue
			}
			title := stem
			if i := strings.Index(stem, "-"); i >= 0 {
				title = stem[i+1:]
			}
			content := "# " + title + "\n" + strings.TrimSpace(strings.ReplaceAll(text, "\r\n", "\n")) + "\n"
			if err := os.WriteFile(filepath.Join(dir, "describe", stem+".md"), []byte(content), 0o644); err != nil {
				writeJSON(w, 500, map[string]any{"error": err.Error()})
				return
			}
			n++
		}
		writeJSON(w, 200, map[string]any{"saved": n, "character": a.packageSummary(id)})
	case action == "profile" && r.Method == http.MethodPut:
		var body struct {
			Profile map[string]any `json:"profile"`
		}
		if err := decodeJSON(r, &body); err != nil || body.Profile == nil {
			writeJSON(w, 400, map[string]any{"error": "bad json"})
			return
		}
		cur, _ := readJSONFile(filepath.Join(dir, "profile.json")).(map[string]any)
		if cur == nil {
			cur = map[string]any{}
		}
		for k, v := range body.Profile { // the page sends the confirmed groups; proposals and anything else stay
			cur[k] = v
		}
		out, _ := json.MarshalIndent(cur, "", "  ")
		if err := os.WriteFile(filepath.Join(dir, "profile.json"), append(out, '\n'), 0o644); err != nil {
			writeJSON(w, 500, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]any{"profile": cur})
	case action == "run" && r.Method == http.MethodPost:
		var body struct {
			Phase string `json:"phase"`
			From  string `json:"from"` // run from this phase to the end (the page: intake alone, then the rest)
			Model string `json:"model"`
			Yes   bool   `json:"yes"`
			Force bool   `json:"force"`
		}
		if err := decodeJSON(r, &body); err != nil {
			writeJSON(w, 400, map[string]any{"error": "bad json"})
			return
		}
		if body.Phase == "" {
			body.Phase = "all"
		}
		ok := body.Phase == "all"
		fromOK := body.From == ""
		for _, ph := range skillPhases {
			ok = ok || ph == body.Phase
			fromOK = fromOK || ph == body.From
		}
		ok = ok && fromOK
		if !ok || (body.Model != "" && !regexp.MustCompile(`^[A-Za-z0-9./_-]+$`).MatchString(body.Model)) {
			writeJSON(w, 400, map[string]any{"error": "bad phase or model"})
			return
		}
		if body.Model == "" {
			body.Model = "gemini"
		}
		args := []string{filepath.Join(a.mgr.Root(), "tools", "soul_writer.py"), "run", id, "--phase", body.Phase, "--model", body.Model}
		if body.From != "" {
			args = append(args, "--from", body.From)
		}
		if body.Yes {
			args = append(args, "--yes")
		}
		if body.Force {
			args = append(args, "--force")
		}
		if err := a.startCharJob(id, "run", body.Phase, body.Model, a.venvPython(), args); err != nil {
			writeJSON(w, 409, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]any{"started": true, "job": a.jobView(id)})
	case action == "simple" && r.Method == http.MethodPost:
		// the simple path (prompt.md §2.10): profile.json's sliders, choices and three boxes → the files, no model
		var body struct {
			Force bool `json:"force"`
		}
		_ = decodeJSON(r, &body)
		args := []string{filepath.Join(a.mgr.Root(), "tools", "soul_writer.py"), "simple", id}
		if body.Force {
			args = append(args, "--force")
		}
		if err := a.startCharJob(id, "simple", "simple", "", a.venvPython(), args); err != nil {
			writeJSON(w, 409, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]any{"started": true, "job": a.jobView(id)})
	case action == "install" && r.Method == http.MethodPost:
		if !fileExists(filepath.Join(dir, "SOUL.md")) {
			writeJSON(w, 400, map[string]any{"error": "no SOUL.md yet — run the skill first"})
			return
		}
		var ib struct {
			Force bool `json:"force"`
		}
		_ = decodeJSON(r, &ib)
		if st := staleInputs(dir); len(st) > 0 && !ib.Force {
			writeJSON(w, 409, map[string]any{"error": "inputs changed since the files were generated (" + strings.Join(st, ", ") + ") — rerun 6 and 7 first, or force", "stale": st})
			return
		}
		if a.mgr.Info(id).Active {
			writeJSON(w, 409, map[string]any{"error": "stop the character before reinstalling"})
			return
		}
		ps := filepath.Join(a.mgr.Root(), "install-character.ps1")
		seed := filepath.Join(a.mgr.Root(), "tools", "seed-memories.py")
		// one shell command: install (creates the profile when missing), then the seeds (embedder up, she is not running)
		script := fmt.Sprintf("& '%s' -Name '%s'; if ($LASTEXITCODE -ne 0 -and $?) { }; & '%s' '%s' '%s'", ps, id, a.venvPython(), seed, id)
		if err := a.startCharJob(id, "install", "", "", "powershell.exe", []string{"-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script}); err != nil {
			writeJSON(w, 409, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]any{"started": true, "job": a.jobView(id)})
	case action == "job" && r.Method == http.MethodGet:
		writeJSON(w, 200, map[string]any{"job": a.jobView(id)})
	default:
		writeJSON(w, 404, map[string]any{"error": "unknown action"})
	}
}

func (a *API) createCharacter(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ID          string `json:"id"`
		DisplayName string `json:"display_name"`
		Pronoun     string `json:"pronoun"`
		Avatar      string `json:"avatar"`
		FromExample bool   `json:"from_example"`
	}
	if err := decodeJSON(r, &body); err != nil || !charID.MatchString(body.ID) || strings.TrimSpace(body.DisplayName) == "" {
		writeJSON(w, 400, map[string]any{"error": "id (lowercase letters, digits, _ -) and display_name are required"})
		return
	}
	if st, err := os.Stat(filepath.Join(a.charactersDir(), body.ID)); err == nil && st.IsDir() {
		writeJSON(w, 409, map[string]any{"error": "a package with this id already exists"})
		return
	}
	if a.mgr.Exists(body.ID) {
		writeJSON(w, 409, map[string]any{"error": "a profile with this id already exists under home/profiles"})
		return
	}
	args := []string{filepath.Join(a.mgr.Root(), "tools", "soul_writer.py"), "init", body.ID, "--display", strings.TrimSpace(body.DisplayName)}
	if body.Pronoun == "他" {
		args = append(args, "--pronoun", "他")
	}
	if body.Avatar != "" && !strings.ContainsAny(body.Avatar, " \"'") {
		args = append(args, "--avatar", body.Avatar)
	}
	if body.FromExample {
		args = append(args, "--from-example")
	}
	cmd := exec.Command(a.venvPython(), args...)
	cmd.Dir = a.mgr.Root()
	cmd.Env = append(os.Environ(), "PYTHONIOENCODING=utf-8", "PYTHONUTF8=1")
	out, err := cmd.CombinedOutput()
	if err != nil {
		writeJSON(w, 500, map[string]any{"error": strings.TrimSpace(string(out))})
		return
	}
	writeJSON(w, 200, map[string]any{"character": a.packageSummary(body.ID), "output": strings.TrimSpace(string(out))})
}

func (a *API) characterDetail(w http.ResponseWriter, id, dir string) {
	build := map[string]any{}
	for _, ph := range []string{"intake", "structure", "thinking", "voice", "reactions", "parts", "verify"} {
		if v := readJSONFile(filepath.Join(dir, "build", ph+".json")); v != nil {
			build[ph] = v
		}
	}
	var people []string
	if entries, err := os.ReadDir(filepath.Join(dir, "people")); err == nil {
		for _, e := range entries {
			if !e.IsDir() && strings.HasSuffix(e.Name(), ".md") {
				people = append(people, strings.TrimSuffix(e.Name(), ".md"))
			}
		}
	}
	if people == nil {
		people = []string{}
	}
	seeds := 0
	if b, err := os.ReadFile(filepath.Join(dir, "seeds.jsonl")); err == nil {
		for _, ln := range strings.Split(string(b), "\n") {
			if strings.TrimSpace(ln) != "" {
				seeds++
			}
		}
	}
	writeJSON(w, 200, map[string]any{
		"character": a.packageSummary(id),
		"describe":  readDescribe(dir),
		"profile":   readJSONFile(filepath.Join(dir, "profile.json")),
		"build":     build,
		"check":     readTextFile(filepath.Join(dir, "build", "check.md")),
		"verify":    readTextFile(filepath.Join(dir, "build", "verify.md")),
		"soul":      readTextFile(filepath.Join(dir, "SOUL.md")),
		"seeds":     seeds,
		"people":    people,
		"job":       a.jobView(id),
	})
}

func (a *API) jobView(id string) map[string]any {
	j := a.charJob(id)
	j.mu.Lock()
	defer j.mu.Unlock()
	logText := j.log.String()
	if len(logText) > 6000 {
		logText = "…" + logText[len(logText)-6000:]
	}
	var started any
	if !j.startedAt.IsZero() {
		started = j.startedAt.Unix()
	}
	return map[string]any{"running": j.running, "kind": j.kind, "phase": j.phase, "model": j.model, "started_at": started,
		"exit_code": j.exitCode, "error": j.err, "log": logText}
}

// startCharJob runs one subprocess per package at a time; its combined output goes to the job log and
// to build/run.log so the page can follow it and a crash leaves a trace.
func (a *API) startCharJob(id, kind, phase, model, exe string, args []string) error {
	j := a.charJob(id)
	j.mu.Lock()
	if j.running {
		j.mu.Unlock()
		return fmt.Errorf("a %s job is already running for %s", j.kind, id)
	}
	j.running, j.kind, j.phase, j.model, j.startedAt, j.exitCode, j.err = true, kind, phase, model, time.Now(), 0, ""
	j.log.Reset()
	j.mu.Unlock()
	cmd := exec.Command(exe, args...)
	cmd.Dir = a.mgr.Root()
	cmd.Env = append(os.Environ(), "PYTHONIOENCODING=utf-8", "PYTHONUTF8=1")
	pr, pw := io.Pipe()
	cmd.Stdout, cmd.Stderr = pw, pw
	if err := cmd.Start(); err != nil {
		j.mu.Lock()
		j.running, j.err = false, err.Error()
		j.mu.Unlock()
		return err
	}
	logPath := filepath.Join(a.charactersDir(), id, "build", "run.log")
	_ = os.MkdirAll(filepath.Dir(logPath), 0o755)
	go func() {
		f, _ := os.Create(logPath)
		sc := bufio.NewScanner(pr)
		sc.Buffer(make([]byte, 64*1024), 1024*1024)
		for sc.Scan() {
			line := sc.Text()
			j.mu.Lock()
			j.log.WriteString(line + "\n")
			j.mu.Unlock()
			if f != nil {
				_, _ = f.WriteString(line + "\n")
			}
		}
		if f != nil {
			_ = f.Close()
		}
	}()
	go func() {
		err := cmd.Wait()
		_ = pw.Close()
		j.mu.Lock()
		j.running = false
		if err != nil {
			if ee, ok := err.(*exec.ExitError); ok {
				j.exitCode = ee.ExitCode()
			} else {
				j.exitCode = -1
				j.err = err.Error()
			}
		}
		j.mu.Unlock()
		a.emit(map[string]any{"type": "character.job", "character": id, "kind": kind, "running": false, "exit_code": j.exitCode})
	}()
	a.emit(map[string]any{"type": "character.job", "character": id, "kind": kind, "running": true})
	return nil
}
