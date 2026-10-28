package companions

import (
	"database/sql"
	"path/filepath"
	"testing"
)

// A resumed Hermes session replays the system prompt it stored when it opened; before a start 556d drops that stored
// prompt for the live sessions so the next turn rebuilds it from her current files. Ended sessions are left alone, and
// a profile without a state.db is simply "nothing to do".
func TestForgetStoredPromptsClearsLiveSessionsOnly(t *testing.T) {
	dir := t.TempDir()
	tr := &Transcript{path: filepath.Join(dir, "state.db")}
	if n, err := tr.ForgetStoredPrompts(); n != 0 || err != nil {
		t.Fatalf("no state.db yet must be 0, nil: %d %v", n, err)
	}
	db, err := sql.Open("sqlite", "file:"+filepath.ToSlash(tr.path))
	if err != nil {
		t.Fatal(err)
	}
	for _, q := range []string{
		`CREATE TABLE sessions (id TEXT PRIMARY KEY, ended_at REAL, system_prompt TEXT, system_prompt_hash TEXT)`,
		`CREATE TABLE system_prompts (hash TEXT PRIMARY KEY, prompt TEXT)`,
		`INSERT INTO system_prompts VALUES ('h-live', 'old prompt'), ('h-ended', 'older prompt')`,
		`INSERT INTO sessions VALUES ('live', NULL, NULL, 'h-live'), ('ended', 1.0, NULL, 'h-ended'), ('fresh', NULL, NULL, NULL)`,
	} {
		if _, err := db.Exec(q); err != nil {
			t.Fatal(err)
		}
	}
	db.Close()
	n, err := tr.ForgetStoredPrompts()
	if err != nil || n != 1 {
		t.Fatalf("expected the one live session with a stored prompt: n=%d err=%v", n, err)
	}
	db, _ = sql.Open("sqlite", "file:"+filepath.ToSlash(tr.path)+"?mode=ro")
	defer db.Close()
	var liveHash, endedHash sql.NullString
	_ = db.QueryRow(`SELECT system_prompt_hash FROM sessions WHERE id = 'live'`).Scan(&liveHash)
	_ = db.QueryRow(`SELECT system_prompt_hash FROM sessions WHERE id = 'ended'`).Scan(&endedHash)
	if liveHash.Valid || !endedHash.Valid {
		t.Fatalf("live session must lose its prompt, the ended one keeps it: live=%v ended=%v", liveHash, endedHash)
	}
	var bodies int
	_ = db.QueryRow(`SELECT COUNT(*) FROM system_prompts`).Scan(&bodies)
	if bodies != 1 {
		t.Fatalf("the unreferenced prompt body must be pruned, the referenced one kept: %d", bodies)
	}
	if n, err := tr.ForgetStoredPrompts(); n != 0 || err != nil {
		t.Fatalf("a second pass has nothing to clear: %d %v", n, err)
	}
}
