package companions

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	_ "modernc.org/sqlite" // pure Go, no cgo (same driver the memory page uses)
)

// Transcript is 556d's view of a companion's Hermes session store (state.db): which session is
// her conversation and what it holds, with each message's origin. Hermes owns the file; 556d
// reads it for routing and display, and writes exactly once per conversation (StampRouting).
//
// One conversation per character: Hermes keys a Telegram DM as
// agent:main:telegram:dm:<chat_id> (gateway/session.py build_session_key; the "agent:main"
// namespace holds while profile multiplexing is off). The app continues that same session by id,
// so Telegram and the app share one history; the memory engine never has to carry it.
type Transcript struct{ path string }

func (m *Manager) Transcript(name string) *Transcript {
	return &Transcript{path: filepath.Join(m.Dir(name), "state.db")}
}

// TelegramKey is the gateway's session key for her DM with you.
func TelegramKey(chatID string) string { return "agent:main:telegram:dm:" + chatID }

// TelegramChat is your DM with her: the home channel, else the first allowed user.
func TelegramChat(env map[string]string) string {
	if c := strings.TrimSpace(env["TELEGRAM_HOME_CHANNEL"]); c != "" {
		return c
	}
	return strings.TrimSpace(strings.Split(env["TELEGRAM_ALLOWED_USERS"], ",")[0])
}

func (t *Transcript) open(readOnly bool) (*sql.DB, error) {
	u := "file:" + filepath.ToSlash(t.path) + "?_pragma=busy_timeout(5000)"
	if readOnly {
		u += "&mode=ro"
	}
	db, err := sql.Open("sqlite", u)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	return db, nil
}

// LiveSession returns the open session Hermes routes (source, key) to, or "" when there is none.
func (t *Transcript) LiveSession(source, key string) (string, error) {
	if _, err := os.Stat(t.path); err != nil {
		return "", nil // no store yet: nothing is live
	}
	db, err := t.open(true)
	if err != nil {
		return "", err
	}
	defer db.Close()
	var id string
	err = db.QueryRow(`SELECT id FROM sessions WHERE source = ? AND session_key = ? AND ended_at IS NULL
		ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 1`, source, key).Scan(&id)
	if err == sql.ErrNoRows {
		return "", nil
	}
	return id, err
}

// StampRouting gives a session 556d created (POST /api/sessions) the routing identity the gateway
// recovers a peer's conversation by — sessions.source + session_key, hermes_state_gateway
// _PEER_BY_KEY_SQL — so her first Telegram message joins the conversation the app started instead
// of opening a second one. Only a row without a key is touched. If this ever fails (schema drift)
// she still answers; Telegram then opens its own session and the app follows it from there.
func (t *Transcript) StampRouting(id, source, key, chatID string) error {
	db, err := t.open(false)
	if err != nil {
		return err
	}
	defer db.Close()
	res, err := db.Exec(`UPDATE sessions SET source = ?, session_key = ?, chat_id = ?, chat_type = 'dm'
		WHERE id = ? AND session_key IS NULL`, source, key, chatID, id)
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n != 1 {
		return fmt.Errorf("session %s not stamped (%d rows)", id, n)
	}
	return nil
}

// AgentConversation is her conversation with another character (0.7.0 inter-agent messaging).
type AgentConversation struct {
	Counterpart string    `json:"counterpart"`
	SessionID   string    `json:"session_id"`
	LastTS      float64   `json:"last_ts"`
	Messages    []Message `json:"messages"`
}

// AgentConversations lists the sessions 556d keyed <prefix><name> with their last messages, read-only.
func (t *Transcript) AgentConversations(source, prefix string, perConv int) ([]AgentConversation, error) {
	if _, err := os.Stat(t.path); err != nil {
		return nil, nil
	}
	db, err := t.open(true)
	if err != nil {
		return nil, err
	}
	rows, err := db.Query(`SELECT id, session_key, COALESCE(last_activity_at, started_at, 0) FROM sessions
		WHERE source = ? AND session_key LIKE ? ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 20`, source, prefix+"%")
	if err != nil {
		db.Close()
		return nil, err
	}
	out := []AgentConversation{} // never nil: the renderer indexes it (JSON null blanked the 狀態 page)
	for rows.Next() {
		var c AgentConversation
		var key string
		if err := rows.Scan(&c.SessionID, &key, &c.LastTS); err != nil {
			continue
		}
		c.Counterpart = strings.TrimPrefix(key, prefix)
		out = append(out, c)
	}
	rows.Close()
	db.Close()
	for i := range out {
		msgs, err := t.Messages(out[i].SessionID, perConv, "")
		if err == nil {
			out[i].Messages = msgs
		}
	}
	return out, nil
}

// Message is one line of the conversation as the windows show it.
type Message struct {
	ID     int64   `json:"id"`
	Role   string  `json:"role"`
	Text   string  `json:"text"`
	TS     float64 `json:"ts"`
	Source string  `json:"source"` // "app", or the channel it came through (telegram); her reply inherits the question's source
}

type rawMessage struct {
	Message
	channel bool // Hermes stored a platform message id → it came through a channel adapter
}

// Messages returns the latest `limit` user/assistant messages, oldest first.
func (t *Transcript) Messages(sessionID string, limit int, channel string) ([]Message, error) {
	rows, err := t.query(`SELECT id, role, content, timestamp, platform_message_id IS NOT NULL FROM messages
		WHERE session_id = ? AND active = 1 AND _compressed_summary = 0 AND role IN ('user','assistant')
		ORDER BY id DESC LIMIT ?`, sessionID, limit*3)
	if err != nil {
		return nil, err
	}
	for i, j := 0, len(rows)-1; i < j; i, j = i+1, j-1 {
		rows[i], rows[j] = rows[j], rows[i]
	}
	if len(rows) > limit {
		rows = rows[len(rows)-limit:]
	}
	return attribute(rows, channel, "app"), nil
}

// After returns user/assistant messages with id > after, oldest first (the live follower).
// lastUserSource carries the attribution state across calls.
func (t *Transcript) After(sessionID string, after int64, channel, lastUserSource string) ([]Message, error) {
	rows, err := t.query(`SELECT id, role, content, timestamp, platform_message_id IS NOT NULL FROM messages
		WHERE session_id = ? AND id > ? AND active = 1 AND _compressed_summary = 0 AND role IN ('user','assistant')
		ORDER BY id ASC LIMIT 200`, sessionID, after)
	if err != nil {
		return nil, err
	}
	return attribute(rows, channel, lastUserSource), nil
}

// MaxID is the newest message id of a session (the follower starts from "now").
func (t *Transcript) MaxID(sessionID string) (int64, error) {
	db, err := t.open(true)
	if err != nil {
		return 0, err
	}
	defer db.Close()
	var id sql.NullInt64
	if err := db.QueryRow(`SELECT MAX(id) FROM messages WHERE session_id = ?`, sessionID).Scan(&id); err != nil {
		return 0, err
	}
	return id.Int64, nil
}

func (t *Transcript) query(q string, args ...any) ([]rawMessage, error) {
	db, err := t.open(true)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rs, err := db.Query(q, args...)
	if err != nil {
		return nil, err
	}
	defer rs.Close()
	out := []rawMessage{}
	for rs.Next() {
		var (
			m       rawMessage
			content sql.NullString
			ts      sql.NullFloat64
		)
		if err := rs.Scan(&m.ID, &m.Role, &content, &ts, &m.channel); err != nil {
			return nil, err
		}
		m.Text = strings.TrimSpace(contentText(content))
		if m.Text == "" {
			continue // tool-call-only assistant rows
		}
		m.TS = ts.Float64
		out = append(out, m)
	}
	return out, rs.Err()
}

// IsCue: the psyche engine's narrator cue, stored as a "user" row when the character speaks first.
// It is never the user's words; the app shows it only on request, styled as a note.
func IsCue(text string) bool { return strings.HasPrefix(strings.TrimSpace(text), "【事件】") }

// IsPlatformError: text the platform returned in place of her words (the model lane down, an invented
// tool, an agent error). Never shown as hers, never kept.
func IsPlatformError(s string) bool {
	s = strings.TrimSpace(s)
	for _, e := range []string{"Model generated invalid tool call", "does not exist. Available tools", "Tool '", "[error", "Error:",
		"API call failed", "all backends failed", "HTTP 502", "HTTP 503", "HTTP 500"} {
		if strings.HasPrefix(s, e) || strings.Contains(s, e) {
			return true
		}
	}
	return false
}

// IsSilence: her answer to a cue that means "not now" (events.py SILENCE), or a platform error
// returned in place of her words.
func IsSilence(s string) bool {
	s = strings.Trim(strings.TrimSpace(s), "「」\"'()（）")
	return s == "" || s == "沉默" || IsPlatformError(s)
}

// DiscardOrphans deactivates the trailing user rows of a session that never got an answer: a turn
// that failed (the model lane down), or a cue the platform could not answer. Hermes stores the user
// message before the call and nothing after a failure, so the row would otherwise re-enter her
// context on the next successful turn (and the app's history). text limits it to that one message
// (the newest match); before > 0 keeps rows newer than that epoch (turns still in flight).
func (t *Transcript) DiscardOrphans(sessionID, text string, before float64) (int, error) {
	db, err := t.open(false)
	if err != nil {
		return 0, err
	}
	defer db.Close()
	var lastA sql.NullInt64
	_ = db.QueryRow(`SELECT MAX(id) FROM messages WHERE session_id = ? AND role = 'assistant' AND active = 1`, sessionID).Scan(&lastA)
	rows, err := db.Query(`SELECT id, content, timestamp FROM messages WHERE session_id = ? AND role = 'user' AND active = 1 AND id > ? ORDER BY id`,
		sessionID, lastA.Int64)
	if err != nil {
		return 0, err
	}
	var ids []int64
	for rows.Next() {
		var id int64
		var c sql.NullString
		var ts sql.NullFloat64
		if rows.Scan(&id, &c, &ts) != nil {
			continue
		}
		if text != "" && strings.TrimSpace(contentText(c)) != strings.TrimSpace(text) {
			continue
		}
		if before > 0 && ts.Valid && ts.Float64 > before {
			continue
		}
		ids = append(ids, id)
	}
	rows.Close()
	if text != "" && len(ids) > 1 {
		ids = ids[len(ids)-1:]
	}
	n := 0
	for _, id := range ids {
		if _, err := db.Exec(`UPDATE messages SET active = 0 WHERE id = ?`, id); err == nil {
			n++
		}
	}
	return n, nil
}

// LastUserIsCue reports whether a session's newest user row is a narrator cue — an event turn in
// flight whose answer has not landed yet.
func (t *Transcript) LastUserIsCue(sessionID string) bool {
	db, err := t.open(true)
	if err != nil {
		return false
	}
	defer db.Close()
	var c sql.NullString
	_ = db.QueryRow(`SELECT content FROM messages WHERE session_id = ? AND role = 'user' AND active = 1 ORDER BY id DESC LIMIT 1`, sessionID).Scan(&c)
	return IsCue(contentText(c))
}

// attribute marks each message's surface: a user message with a platform message id came
// through a channel; her reply belongs to the question before it. A narrator cue is "cue", her
// answer to it "event" (silence or a platform error in that place is "cue" too: not her words).
func attribute(rows []rawMessage, channel, lastUserSource string) []Message {
	if channel == "" {
		channel = "channel"
	}
	out := make([]Message, 0, len(rows))
	for _, r := range rows {
		m := r.Message
		switch {
		case r.Role == "user" && IsCue(r.Text):
			m.Source = "cue"
			lastUserSource = "event"
		case r.Role == "assistant" && lastUserSource == "event" && IsSilence(r.Text):
			m.Source = "cue"
		case r.Role == "user" && r.channel:
			m.Source = channel
			lastUserSource = channel
		case r.Role == "user":
			m.Source = "app"
			lastUserSource = "app"
		default:
			m.Source = lastUserSource
		}
		out = append(out, m)
	}
	return out
}

// contentText flattens a stored content column: plain text, or a JSON list of parts.
func contentText(c sql.NullString) string {
	if !c.Valid {
		return ""
	}
	s := c.String
	if strings.HasPrefix(strings.TrimSpace(s), "[") {
		var parts []map[string]any
		if json.Unmarshal([]byte(s), &parts) == nil {
			var sb strings.Builder
			for _, p := range parts {
				if t, _ := p["text"].(string); t != "" {
					sb.WriteString(t)
				}
			}
			return sb.String()
		}
	}
	return s
}
