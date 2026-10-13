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
	var out []rawMessage
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

// attribute marks each message's surface: a user message with a platform message id came
// through a channel; her reply belongs to the question before it.
func attribute(rows []rawMessage, channel, lastUserSource string) []Message {
	if channel == "" {
		channel = "channel"
	}
	out := make([]Message, 0, len(rows))
	for _, r := range rows {
		m := r.Message
		switch {
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
