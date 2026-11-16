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

// When she lets a message go (when-to-reply.md) her row is a silence marker: the history shows no bubble for it,
// and a reaction she put on your message rides on your row.
func TestNoReplyRowsHideAndHerReactionRidesOnYourMessage(t *testing.T) {
	for s, want := range map[string]bool{"NO_REPLY": true, " no_reply ": true, "[SILENT]": true, "*NO_REPLY*": true,
		"好啦 NO_REPLY": false, "晚安": false, "": false} {
		if IsNoReply(s) != want {
			t.Fatalf("IsNoReply(%q) = %v", s, !want)
		}
	}
	dir := t.TempDir()
	tr := &Transcript{path: filepath.Join(dir, "state.db")}
	db, err := sql.Open("sqlite", "file:"+filepath.ToSlash(tr.path))
	if err != nil {
		t.Fatal(err)
	}
	for _, q := range []string{
		`CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL,
			platform_message_id TEXT, display_metadata TEXT, active INTEGER DEFAULT 1, _compressed_summary INTEGER DEFAULT 0)`,
		`INSERT INTO messages (session_id, role, content, timestamp) VALUES ('s', 'user', '在幹嘛', 1), ('s', 'assistant', '在畫畫', 2)`,
		`INSERT INTO messages (session_id, role, content, timestamp, display_metadata) VALUES
			('s', 'user', '好啦 晚安', 3, '{"reactions":[{"emoji":"🥰","author":"agent","at":4}]}')`,
		`INSERT INTO messages (session_id, role, content, timestamp) VALUES ('s', 'assistant', 'NO_REPLY', 4)`,
	} {
		if _, err := db.Exec(q); err != nil {
			t.Fatal(err)
		}
	}
	db.Close()
	msgs, err := tr.Messages("s", 50, "telegram")
	if err != nil {
		t.Fatal(err)
	}
	if len(msgs) != 3 || msgs[2].Text != "好啦 晚安" || msgs[2].Reaction != "🥰" || msgs[0].Reaction != "" {
		t.Fatalf("expected three rows, the last one yours with her 🥰 and no NO_REPLY bubble: %+v", msgs)
	}
	id, emoji, err := tr.LastUserReaction("s")
	if err != nil || id != 3 || emoji != "🥰" {
		t.Fatalf("LastUserReaction = %d %q %v", id, emoji, err)
	}
}
