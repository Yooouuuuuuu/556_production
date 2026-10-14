// Package memory reads a KeepsakeDB store (her memory, home/memory/<profile>.db) for the app's
// memory page and sends deletes through the store's command queue.
//
// Rules (see KeepsakeDB docs/DESIGN.md "Ownership"): the Hermes process that runs the kokoro
// provider is the single writer and holds the dense cache; 556d only READS the SQLite file
// (WAL allows concurrent readers) and never touches the memories tables. A delete is a row in
// the `commands` table; the owner drains it before its next search and on a 1 s timer, so the
// app sees it done within a second or two, or "queued" if she is not running right now.
package memory

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite" // pure Go, no cgo: keeps the single-exe goal
)

var ErrNoStore = errors.New("memory store does not exist yet")

type Memory struct {
	ID            int64    `json:"id"`
	Text          string   `json:"text"`
	Tags          []string `json:"tags"`
	Archived      int      `json:"archived"` // 0 active, 1 archived (topic suppressed), 2 superseded
	Layer         string   `json:"layer"`    // long (facts) | short (dated notes)
	Superseded    bool     `json:"superseded"`
	ArchiveReason *string  `json:"archive_reason"`
	CreatedAt     float64  `json:"created_at"`
	UpdatedAt     float64  `json:"updated_at"`
}

type Stats struct {
	Memories   int    `json:"memories"` // long layer, active
	Short      int    `json:"short"`    // short layer, active
	Archived   int    `json:"archived"`
	Superseded int    `json:"superseded"`
	Tags       int    `json:"tags"`
	OwnerAlive bool   `json:"owner_alive"`
	Pending    int    `json:"pending_commands"`
	FileBytes  int64  `json:"file_bytes"`
	Path       string `json:"path"`
}

type Tag struct {
	Tag   string `json:"tag"`
	Count int    `json:"count"`
}

type Store struct {
	path string
	mu   sync.Mutex
	ro   *sql.DB
	rw   *sql.DB
}

func New(path string) *Store { return &Store{path: path} }

func (s *Store) Path() string { return s.path }

func (s *Store) Exists() bool {
	st, err := os.Stat(s.path)
	return err == nil && st.Size() > 0
}

func (s *Store) dsn(readOnly bool) string {
	u := "file:" + filepath.ToSlash(s.path) + "?_pragma=busy_timeout(5000)"
	if readOnly {
		u += "&mode=ro"
	}
	return u
}

func (s *Store) open(readOnly bool) (*sql.DB, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.Exists() {
		return nil, ErrNoStore
	}
	target := &s.rw
	if readOnly {
		target = &s.ro
	}
	if *target != nil {
		return *target, nil
	}
	db, err := sql.Open("sqlite", s.dsn(readOnly))
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	*target = db
	return db, nil
}

// List returns memories newest first. q is a plain substring filter (the engine's own hybrid
// search needs the embedder; a browse page needs "find the row that says X").
func (s *Store) List(ctx context.Context, q, tag string, includeArchived bool, limit int, layer string) ([]Memory, error) {
	if layer == "" {
		layer = "long"
	}
	db, err := s.open(true)
	if err != nil {
		return nil, err
	}
	if limit <= 0 || limit > 2000 {
		limit = 200
	}
	var (
		where []string
		args  []any
		join  string
	)
	if tag != "" {
		join = " JOIN memory_tags t ON t.memory_id = m.id AND t.tag = ?"
		args = append(args, tag)
	}
	if !includeArchived {
		where = append(where, "m.archived = 0", "json_extract(m.meta, '$.hold') IS NULL") // held = kept but not shown (a hurt on the ledger)
	}
	where = append(where, "m.layer = ?")
	args = append(args, layer)
	if q = strings.TrimSpace(q); q != "" {
		where = append(where, "m.text LIKE ? ESCAPE '\\'")
		args = append(args, "%"+escapeLike(q)+"%")
	}
	sqlq := "SELECT m.id, m.text, m.tags, m.archived, m.archive_reason, m.created_at, m.updated_at, m.layer FROM memories m" + join
	if len(where) > 0 {
		sqlq += " WHERE " + strings.Join(where, " AND ")
	}
	sqlq += " ORDER BY m.id DESC LIMIT ?"
	args = append(args, limit)
	rows, err := db.QueryContext(ctx, sqlq, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Memory{}
	for rows.Next() {
		var m Memory
		var tagsJSON string
		if err := rows.Scan(&m.ID, &m.Text, &tagsJSON, &m.Archived, &m.ArchiveReason, &m.CreatedAt, &m.UpdatedAt, &m.Layer); err != nil {
			return nil, err
		}
		_ = json.Unmarshal([]byte(tagsJSON), &m.Tags)
		if m.Tags == nil {
			m.Tags = []string{}
		}
		m.Superseded = m.Archived == 2
		out = append(out, m)
	}
	return out, rows.Err()
}

func escapeLike(s string) string {
	r := strings.NewReplacer(`\`, `\\`, `%`, `\%`, `_`, `\_`)
	return r.Replace(s)
}

func (s *Store) Tags(ctx context.Context) ([]Tag, error) {
	db, err := s.open(true)
	if err != nil {
		return nil, err
	}
	rows, err := db.QueryContext(ctx, "SELECT t.tag, count(*) FROM memory_tags t JOIN memories m ON m.id = t.memory_id WHERE m.archived = 0 GROUP BY t.tag ORDER BY 2 DESC, 1")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Tag{}
	for rows.Next() {
		var t Tag
		if err := rows.Scan(&t.Tag, &t.Count); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

func (s *Store) Stats(ctx context.Context) (Stats, error) {
	st := Stats{Path: s.path}
	db, err := s.open(true)
	if err != nil {
		return st, err
	}
	one := func(q string) int {
		var n int
		_ = db.QueryRowContext(ctx, q).Scan(&n)
		return n
	}
	st.Memories = one("SELECT count(*) FROM memories WHERE archived = 0 AND layer = 'long'")
	st.Short = one("SELECT count(*) FROM memories WHERE archived = 0 AND layer = 'short'")
	st.Archived = one("SELECT count(*) FROM memories WHERE archived = 1")
	st.Superseded = one("SELECT count(*) FROM memories WHERE archived = 2")
	st.Tags = one("SELECT count(DISTINCT t.tag) FROM memory_tags t JOIN memories m ON m.id = t.memory_id WHERE m.archived = 0")
	st.Pending = one("SELECT count(*) FROM commands WHERE done_at IS NULL")
	st.OwnerAlive = s.ownerAlive(ctx, db)
	if fi, err := os.Stat(s.path); err == nil {
		st.FileBytes = fi.Size()
	}
	return st, nil
}

// ownerAlive mirrors Keepsake.owner_alive(): meta.owner = {"pid", "seen"} refreshed by the owner's
// drain loop; stale after 5 s.
func (s *Store) ownerAlive(ctx context.Context, db *sql.DB) bool {
	var raw string
	if err := db.QueryRowContext(ctx, "SELECT value FROM meta WHERE key = 'owner'").Scan(&raw); err != nil {
		return false
	}
	var info struct {
		Seen float64 `json:"seen"`
	}
	if json.Unmarshal([]byte(raw), &info) != nil {
		return false
	}
	return time.Since(time.Unix(0, int64(info.Seen*1e9))) < 5*time.Second
}

// Delete enqueues a delete command and waits up to `wait` for the owner to execute it.
// status is "done" (count = rows deleted) or "queued" (she is not running; it runs at her next drain).
func (s *Store) Delete(ctx context.Context, ids []int64, reason, by string, wait time.Duration) (status string, count int, cmdID int64, err error) {
	if len(ids) == 0 {
		return "", 0, 0, errors.New("no ids")
	}
	db, err := s.open(false)
	if err != nil {
		return "", 0, 0, err
	}
	payload, _ := json.Marshal(map[string]any{"ids": ids, "reason": reason})
	res, err := db.ExecContext(ctx, "INSERT INTO commands(op, payload, requested_at, requested_by) VALUES ('delete', ?, ?, ?)",
		string(payload), float64(time.Now().UnixNano())/1e9, by)
	if err != nil {
		return "", 0, 0, fmt.Errorf("enqueue: %w", err)
	}
	cmdID, _ = res.LastInsertId()
	deadline := time.Now().Add(wait)
	for time.Now().Before(deadline) {
		var doneAt sql.NullFloat64
		var result sql.NullString
		if err := db.QueryRowContext(ctx, "SELECT done_at, result FROM commands WHERE id = ?", cmdID).Scan(&doneAt, &result); err == nil && doneAt.Valid {
			var r struct {
				Count int    `json:"count"`
				Error string `json:"error"`
			}
			_ = json.Unmarshal([]byte(result.String), &r)
			if r.Error != "" {
				return "error", 0, cmdID, errors.New(r.Error)
			}
			return "done", r.Count, cmdID, nil
		}
		select {
		case <-ctx.Done():
			return "queued", 0, cmdID, nil
		case <-time.After(200 * time.Millisecond):
		}
	}
	return "queued", 0, cmdID, nil
}

func (s *Store) Close() {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, db := range []*sql.DB{s.ro, s.rw} {
		if db != nil {
			_ = db.Close()
		}
	}
	s.ro, s.rw = nil, nil
}
