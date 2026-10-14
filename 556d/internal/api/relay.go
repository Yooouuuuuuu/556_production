package api

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/Yooouuuuuuu/556_production/556d/internal/companions"
)

// Inter-agent messaging (inner-life.md §18): characters talk to each other through 556d. Each pair has
// its own session in EACH character's state.db (key 556:agent:<other>, source 556), opened and stamped
// here like her conversation with you. A conversation starts when a character's engine wants to speak
// to another one (its event turn produces the first message and the psyche plugin posts it here) and
// 556d then carries the exchange on, turn by turn, until silence or the turn cap (cost control, not a
// script). Everything either side says is a normal turn in its own session, so memory and appraisal
// run on both sides, with the other character as the counterpart.

const (
	relaySource    = "556"
	relayKeyPrefix = "556:agent:"
	relayDefaultCap = 6
)

type relayPair struct{ a, b string }

func pairKey(a, b string) relayPair {
	if a > b {
		a, b = b, a
	}
	return relayPair{a, b}
}

var (
	relayMu   sync.Mutex
	relayBusy = map[relayPair]bool{}
)

// Mailbox (inner-life.md §18): a message for a character who is not running waits in
// home/mailbox/<to>.json and is delivered when she starts (or at the next sweep), continuing the
// conversation where it stopped — so A can ask while B is down and B can answer while A is down.
// Late delivery carries the time it was left, so the listener does not take it for "now".
type mailItem struct {
	ID   string  `json:"id"`
	From string  `json:"from"`
	To   string  `json:"to"`
	Text string  `json:"text"`
	At   float64 `json:"at"`
	Turn int     `json:"turn"` // turns already taken in this conversation
	Cap  int     `json:"cap"`
}

const (
	mailboxMaxPerPair = 20
	mailboxTTL        = 7 * 24 * time.Hour
)

var mailMu sync.Mutex

func (a *API) mailboxPath(to string) string { return filepath.Join(a.settings.home, "mailbox", to+".json") }

func (a *API) mailboxLoad(to string) []mailItem {
	var items []mailItem
	if raw, err := os.ReadFile(a.mailboxPath(to)); err == nil {
		_ = json.Unmarshal(raw, &items)
	}
	return items
}

func (a *API) mailboxSave(to string, items []mailItem) error {
	if err := os.MkdirAll(filepath.Dir(a.mailboxPath(to)), 0o755); err != nil {
		return err
	}
	if len(items) == 0 {
		return os.Remove(a.mailboxPath(to))
	}
	b, _ := json.MarshalIndent(items, "", "  ")
	return os.WriteFile(a.mailboxPath(to), b, 0o600)
}

func (a *API) mailboxHas(to string) bool {
	st, err := os.Stat(a.mailboxPath(to))
	return err == nil && st.Size() > 2
}

// mailboxPut queues a message for `to`; at most mailboxMaxPerPair from the same sender wait.
func (a *API) mailboxPut(from, to, text string, turn, cap int) {
	mailMu.Lock()
	defer mailMu.Unlock()
	items := a.mailboxLoad(to)
	n := 0
	for _, it := range items {
		if it.From == from {
			n++
		}
	}
	if n >= mailboxMaxPerPair {
		log.Printf("[relay] %s is not running and already holds %d messages from %s; this one is dropped", to, n, from)
		return
	}
	b := make([]byte, 6)
	_, _ = rand.Read(b)
	items = append(items, mailItem{ID: hex.EncodeToString(b), From: from, To: to, Text: text, At: float64(time.Now().Unix()), Turn: turn, Cap: cap})
	if err := a.mailboxSave(to, items); err != nil {
		log.Printf("[relay] mailbox for %s: %v", to, err)
		return
	}
	log.Printf("[relay] %s is not running; message from %s waits in the mailbox (%d waiting): %s", to, from, len(items), head(text, 60))
}

// mailboxDrain delivers what waits for `to`, in order, each continuing its conversation. Items older
// than mailboxTTL are dropped; a pair already talking gets its item back for the next sweep.
func (a *API) mailboxDrain(to string) {
	if a.mgr.Client(to) == nil {
		return
	}
	mailMu.Lock()
	items := a.mailboxLoad(to)
	if len(items) == 0 {
		mailMu.Unlock()
		return
	}
	_ = a.mailboxSave(to, nil)
	mailMu.Unlock()
	now := time.Now()
	for _, it := range items {
		left := time.Unix(int64(it.At), 0)
		if now.Sub(left) > mailboxTTL {
			log.Printf("[relay] mailbox for %s: a message from %s expired unread (%s)", to, it.From, head(it.Text, 40))
			continue
		}
		pk := pairKey(it.From, it.To)
		relayMu.Lock()
		if relayBusy[pk] {
			relayMu.Unlock()
			mailMu.Lock()
			_ = a.mailboxSave(to, append(a.mailboxLoad(to), it))
			mailMu.Unlock()
			continue
		}
		relayBusy[pk] = true
		relayMu.Unlock()
		text := it.Text
		if now.Sub(left) > 10*time.Minute { // not "now": the listener knows when it was left
			text = "（" + left.Format("1/2 15:04") + " 留的話）" + text
		}
		log.Printf("[relay] mailbox for %s: delivering a message from %s left %s ago", to, it.From, now.Sub(left).Round(time.Minute))
		a.relayConversation(it.From, it.To, text, it.Cap-it.Turn, pk)
	}
}

// mailboxOutbox lists what `from` has waiting in other characters' mailboxes (for the 狀態 page).
func (a *API) mailboxOutbox(from string) []mailItem {
	var out []mailItem
	entries, err := os.ReadDir(filepath.Join(a.settings.home, "mailbox"))
	if err != nil {
		return out
	}
	mailMu.Lock()
	defer mailMu.Unlock()
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		for _, it := range a.mailboxLoad(strings.TrimSuffix(e.Name(), ".json")) {
			if it.From == from {
				out = append(out, it)
			}
		}
	}
	return out
}

// relaySession returns the session id of `companion`'s conversation with `counterpart`, opening it when
// it does not exist yet. Only an active companion can open one (her API server must be up).
func (a *API) relaySession(ctx context.Context, companion, counterpart string) (string, error) {
	tr := a.mgr.Transcript(companion)
	key := relayKeyPrefix + counterpart
	a.openMu.Lock()
	defer a.openMu.Unlock()
	id, err := tr.LiveSession(relaySource, key)
	if err != nil {
		return "", err
	}
	if id != "" {
		return id, nil
	}
	cl := a.mgr.Client(companion)
	if cl == nil {
		return "", fmt.Errorf("%s is not running", companion)
	}
	b := make([]byte, 3)
	_, _ = rand.Read(b)
	id = fmt.Sprintf("556a_%s_%s_%s", counterpart, time.Now().Format("20060102_150405"), hex.EncodeToString(b))
	if err = cl.CreateSession(ctx, id, relaySource); err != nil {
		return "", err
	}
	if serr := tr.StampRouting(id, relaySource, key, ""); serr != nil {
		log.Printf("[relay] %s: session %s with %s opened but not stamped (%v)", companion, id, counterpart, serr)
	} else {
		log.Printf("[relay] %s: conversation with %s opened (%s)", companion, counterpart, id)
	}
	return id, nil
}

// POST /api/relay/session {companion, counterpart} -> {session_id}
func (a *API) relaySessionHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		Companion   string `json:"companion"`
		Counterpart string `json:"counterpart"`
	}
	if err := json.NewDecoder(io.LimitReader(r.Body, 1<<16)).Decode(&body); err != nil || body.Companion == "" || body.Counterpart == "" {
		http.Error(w, "bad json", http.StatusBadRequest)
		return
	}
	if !a.mgr.Exists(body.Companion) || !a.mgr.Exists(body.Counterpart) || body.Companion == body.Counterpart {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "unknown companion or counterpart"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	id, err := a.relaySession(ctx, body.Companion, body.Counterpart)
	if err != nil {
		writeJSON(w, http.StatusConflict, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"session_id": id})
}

// POST /api/relay {from, to, text}: `from` just said `text` to `to` (its own event turn). 556d delivers it
// into `to`'s session with `from`, and carries the exchange on in the background.
func (a *API) relayHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		From string `json:"from"`
		To   string `json:"to"`
		Text string `json:"text"`
	}
	if err := json.NewDecoder(io.LimitReader(r.Body, 1<<18)).Decode(&body); err != nil || body.From == "" || body.To == "" || strings.TrimSpace(body.Text) == "" {
		http.Error(w, "bad json", http.StatusBadRequest)
		return
	}
	if !a.mgr.Exists(body.From) || !a.mgr.Exists(body.To) || body.From == body.To {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "unknown companion"})
		return
	}
	cap := relayTurnCap(a.mgr.Dir(body.From))
	if a.mgr.Client(body.To) == nil { // she will get it when she starts
		a.mailboxPut(body.From, body.To, body.Text, 0, cap)
		writeJSON(w, http.StatusOK, map[string]any{"accepted": true, "queued": true, "turn_cap": cap})
		return
	}
	pk := pairKey(body.From, body.To)
	relayMu.Lock()
	if relayBusy[pk] {
		relayMu.Unlock()
		writeJSON(w, http.StatusConflict, map[string]any{"error": "a conversation between them is already running"})
		return
	}
	relayBusy[pk] = true
	relayMu.Unlock()
	go a.relayConversation(body.From, body.To, body.Text, cap, pk)
	writeJSON(w, http.StatusOK, map[string]any{"accepted": true, "turn_cap": cap})
}

// relayTurnCap reads proactive.inter_agent_turn_cap from the initiator's psyche.json.
func relayTurnCap(dir string) int {
	raw, err := os.ReadFile(filepath.Join(dir, "psyche.json"))
	if err != nil {
		return relayDefaultCap
	}
	var m struct {
		Proactive struct {
			Cap int `json:"inter_agent_turn_cap"`
		} `json:"proactive"`
	}
	if json.Unmarshal([]byte(strings.TrimPrefix(string(raw), "\xEF\xBB\xBF")), &m) == nil && m.Proactive.Cap > 0 {
		return m.Proactive.Cap
	}
	return relayDefaultCap
}

// relayConversation carries one exchange: speaker said text to listener; the listener answers in its
// session with the speaker; the answer goes back the other way; … until silence, an error, or the cap.
func (a *API) relayConversation(speaker, listener, text string, cap int, pk relayPair) {
	defer func() {
		relayMu.Lock()
		delete(relayBusy, pk)
		relayMu.Unlock()
	}()
	log.Printf("[relay] %s -> %s: conversation starts (cap %d): %s", speaker, listener, cap, head(text, 60))
	for turn := 0; turn < cap; turn++ {
		cl := a.mgr.Client(listener)
		if cl == nil { // the rest of the conversation waits for her
			a.mailboxPut(speaker, listener, text, turn, cap)
			return
		}
		ctx, cancel := context.WithTimeout(context.Background(), 4*time.Minute)
		sid, err := a.relaySession(ctx, listener, speaker)
		if err != nil {
			cancel()
			log.Printf("[relay] %s: no session with %s: %v", listener, speaker, err)
			return
		}
		// the speaker's name rides in the message itself, so the listener's model cannot mistake it for the producer
		res, err := cl.Chat(ctx, companions.DisplayName(a.mgr.Dir(speaker), speaker)+"："+text, "", sid, "")
		cancel()
		if err != nil || res.Err != "" {
			log.Printf("[relay] %s -> %s: turn failed: %v %s", speaker, listener, err, res.Err)
			return
		}
		reply := strings.TrimSpace(res.Reply)
		if reply == "" || isSilence(reply) {
			log.Printf("[relay] %s stays quiet; conversation ends after %d turn(s)", listener, turn+1)
			return
		}
		a.emit(map[string]any{"type": "relay.turn", "from": listener, "to": speaker, "text": reply, "turn": turn + 1})
		log.Printf("[relay] %s -> %s: %s", listener, speaker, head(reply, 60))
		speaker, listener, text = listener, speaker, reply
	}
	log.Printf("[relay] %s <-> %s: turn cap reached", pk.a, pk.b)
}

func head(s string, n int) string {
	rs := []rune(strings.ReplaceAll(s, "\n", " "))
	if len(rs) > n {
		return string(rs[:n]) + "…"
	}
	return string(rs)
}

// GET /api/relay/log?companion=A — her conversations with other characters (read-only, state.db), newest first.
func (a *API) relayLogHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, OPTIONS") {
		return
	}
	name := r.URL.Query().Get("companion")
	if name == "" {
		name = a.selectedName()
	}
	if name == "" || !a.mgr.Exists(name) {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": errNoCompanion.Error()})
		return
	}
	convs, err := a.mgr.Transcript(name).AgentConversations(relaySource, relayKeyPrefix, 30)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"companion": name, "conversations": []any{}, "error": err.Error()})
		return
	}
	if convs == nil {
		convs = []companions.AgentConversation{}
	}
	sort.SliceStable(convs, func(i, j int) bool { return convs[i].LastTS > convs[j].LastTS })
	names := map[string]string{}
	for _, c := range convs {
		if _, ok := names[c.Counterpart]; !ok {
			names[c.Counterpart] = companions.DisplayName(a.mgr.Dir(c.Counterpart), c.Counterpart)
		}
	}
	pending := a.mailboxLoad(name)
	if pending == nil {
		pending = []mailItem{}
	}
	outbox := a.mailboxOutbox(name)
	if outbox == nil {
		outbox = []mailItem{}
	}
	for _, it := range append(append([]mailItem{}, pending...), outbox...) {
		for _, p := range []string{it.From, it.To} {
			if _, ok := names[p]; !ok && p != name {
				names[p] = companions.DisplayName(a.mgr.Dir(p), p)
			}
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"companion": name, "conversations": convs, "names": names, "pending": pending, "outbox": outbox})
}
