// Package api is the UI-facing surface of 556d — the hub every window talks to:
//   - the app's chat goes INTO the selected companion's Hermes gateway through its OpenAI-
//     compatible API server (one Hermes process per character; the app is a client of her,
//     same level as Telegram);
//   - hub events on the bridge WebSocket so every window sees the same conversation
//     (chat.user / chat.delta / chat.complete / chat.error / companion.state, tagged with the
//     companion), plus companion.selected / companion.lifecycle;
//   - /api/history, /api/settings, /api/companion(s), /api/selected, /api/memory, /api/voice,
//     /api/config, /api/restart-hermes;
//   - one conversation per character: the app continues her Telegram DM session (conversation()),
//     channel turns are shown in the windows (followLoop), app turns are mirrored into Telegram as
//     plain text ("你問我 / 我說", no LLM).
//
// Turns are serialized per companion: several clients may send at once, they queue.
package api

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/Yooouuuuuuu/556_production/556d/internal/bridge"
	"github.com/Yooouuuuuuu/556_production/556d/internal/companions"
	"github.com/Yooouuuuuuu/556_production/556d/internal/hermesapi"
	"github.com/Yooouuuuuuu/556_production/556d/internal/supervisor"
	"github.com/Yooouuuuuuu/556_production/556d/internal/voice"
)

// appSessionKey names the app-only conversation of a companion WITHOUT a channel (X-Hermes-Session-Key);
// its session id is kept in her companion.json. A Telegram-bound companion has one conversation
// for every surface instead — see conversation().
const appSessionKey = "556:app"

// follower is the live tail of a companion's conversation: turns that arrive through her channels
// are broadcast to the windows (the app's own turns were broadcast as they happened).
type follower struct {
	event bool // between her event-turn prompt (hidden) and her answer (shown as 主動)
	sessionID string
	cursor    int64
	lastUser  string // attribution state: her reply belongs to the question before it
}

type session struct {
	id   string
	turn sync.Mutex // one turn at a time per companion
}

type API struct {
	Shutdown func() // set by main: asks the daemon to finish up and exit (the app calls POST /api/shutdown on quit)
	mgr      *companions.Manager
	bridge   *bridge.Bridge
	sup      *supervisor.Supervisor
	settings *SettingsStore
	mu        sync.Mutex
	openMu    sync.Mutex           // one conversation is opened at a time (start vs. a racing first turn)
	sessions  map[string]*session  // per companion (app-only conversations)
	followers map[string]*follower // per companion: the shared conversation's live tail
}

// New wires the hub API. defaultSelected (556d.toml daemon.profile) is the companion the
// windows open on when settings.json has no selection yet; nothing is started by it.
func New(mgr *companions.Manager, b *bridge.Bridge, sup *supervisor.Supervisor, hermesHome, defaultSelected string) *API {
	a := &API{mgr: mgr, bridge: b, sup: sup, settings: NewSettingsStore(hermesHome), sessions: map[string]*session{}, followers: map[string]*follower{}}
	go a.followLoop()
	sel := a.settings.Get().SelectedCompanion
	if sel == "" || !mgr.Exists(sel) {
		sel = defaultSelected
	}
	if sel != "" && mgr.Exists(sel) {
		a.settings.SetSelected(sel, mgr.Dir(sel))
	} else {
		a.settings.SetSelected("", "")
	}
	return a
}

// Register mounts the API. The app is the only UI.
func (a *API) Register(mux *http.ServeMux) {
	mux.HandleFunc("/v1/chat/completions", a.chat)
	mux.HandleFunc("/v1/models", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]any{"object": "list", "data": []any{map[string]any{"id": "556", "object": "model", "owned_by": "556-production"}}})
	})
	mux.HandleFunc("/api/history", a.history)
	mux.HandleFunc("/api/settings", a.settingsHandler)
	mux.HandleFunc("/api/companion", a.companion)
	mux.HandleFunc("/api/companions", a.companionsHandler)
	mux.HandleFunc("/api/companions/", a.companionsHandler)
	mux.HandleFunc("/api/selected", a.selectedHandler)
	mux.HandleFunc("/api/restart-hermes", a.restartHermes)
	mux.HandleFunc("/api/memory", a.memoryList)          // her memory: view (delete-only page)
	mux.HandleFunc("/api/memory/delete", a.memoryDelete) // through the KeepsakeDB command queue
	mux.HandleFunc("/api/chat", a.chat)                  // same handler; the app and probes use this path
	mux.HandleFunc("/api/voice", a.voiceHandler)         // cloud STT/TTS connectors (home/voice.json)
	mux.HandleFunc("/api/voice/test", a.voiceTest)       // TTS -> STT round trip
	mux.HandleFunc("/api/voice/transcribe", a.voiceTranscribe) // raw audio -> text (push-to-talk / conversation mode)
	mux.HandleFunc("/api/voice/speak", a.voiceSpeak)      // text -> cached audio + speak_audio event (lipsync)
	mux.HandleFunc("/api/config", a.configHandler)       // the config registry: every knob, dev panel
	mux.HandleFunc("/api/shutdown", a.shutdownHandler)   // graceful daemon shutdown (companions finish up first)
	mux.HandleFunc("/api/relay", a.relayHandler)                  // a character's message for another character: 556d carries the exchange
	mux.HandleFunc("/api/relay/session", a.relaySessionHandler)   // her session with another character (opened + stamped like yours)
	mux.HandleFunc("/api/relay/log", a.relayLogHandler)           // their conversations, read-only (狀態 page)
	mux.HandleFunc("/api/psyche/settings", a.psycheSettingsHandler) // psyche.json: 主動 gates apply at the next tick, the rest at her next start
	mux.HandleFunc("/api/psyche/command", a.psycheCommandHandler)   // close a loop / add a reminder / add a life event — queued for the engine
	mux.HandleFunc("/api/psyche", a.psycheHandler)       // 狀態: read-only view of her psyche.db (the engine in her process writes it)
	mux.HandleFunc("/api/tools", a.toolsHandler)         // what she can do: baseline memory + extensions (restart applies)
}

func (a *API) shutdownHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, 405, map[string]any{"error": "POST only"})
		return
	}
	if a.Shutdown == nil {
		writeJSON(w, 501, map[string]any{"error": "shutdown not wired"})
		return
	}
	writeJSON(w, 202, map[string]any{"ok": true, "note": "finishing up: active companions get their grace period, then 556d exits"})
	go a.Shutdown()
}

func (a *API) sessionSlot(name string) *session {
	a.mu.Lock()
	defer a.mu.Unlock()
	s := a.sessions[name]
	if s == nil {
		s = &session{}
		if sid, _ := companions.ReadCompanionJSON(a.mgr.Dir(name))["app_session_id"].(string); sid != "" {
			s.id = sid
		}
		a.sessions[name] = s
	}
	return s
}

func (a *API) forgetSession(name string) {
	a.mu.Lock()
	delete(a.sessions, name)
	delete(a.followers, name)
	a.mu.Unlock()
}

func (a *API) emit(ev map[string]any) {
	if a.bridge != nil {
		a.bridge.Broadcast(ev)
	}
}

type chatRequest struct {
	Model    string `json:"model"`
	Stream   bool   `json:"stream"`
	Messages []struct {
		Role    string `json:"role"`
		Content any    `json:"content"`
	} `json:"messages"`
}

func cors(w http.ResponseWriter, r *http.Request, methods string) bool {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-556-Client, X-556-Companion, X-556-Voice")
	w.Header().Set("Access-Control-Allow-Methods", methods)
	if r.Method == http.MethodOptions {
		w.WriteHeader(204)
		return true
	}
	return false
}

func decodeJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}

func (a *API) chat(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	body, _ := io.ReadAll(r.Body)
	var req chatRequest
	if err := json.Unmarshal(body, &req); err != nil {
		writeJSON(w, 400, map[string]any{"error": "bad request: " + err.Error()})
		return
	}
	// Hermes owns the conversation history; only the newest user message is forwarded.
	text := ""
	for i := len(req.Messages) - 1; i >= 0; i-- {
		if req.Messages[i].Role == "user" {
			text = contentText(req.Messages[i].Content)
			break
		}
	}
	if strings.TrimSpace(text) == "" {
		writeJSON(w, 400, map[string]any{"error": "no user message"})
		return
	}
	source := r.Header.Get("X-556-Client")
	if source == "" {
		source = "http"
	}
	name, cl, err := a.target(r)
	if err != nil {
		writeJSON(w, 409, map[string]any{"error": err.Error()})
		return
	}
	slot := a.sessionSlot(name)
	slot.turn.Lock()
	defer slot.turn.Unlock()
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()
	key, sid, bound, err := a.conversation(ctx, name, cl)
	if err != nil {
		log.Printf("[api] %s: conversation: %v", name, err)
		writeJSON(w, 502, map[string]any{"error": "conversation: " + err.Error()})
		return
	}

	a.emit(map[string]any{"type": "chat.user", "companion": name, "text": text, "source": source})
	a.emit(map[string]any{"type": "companion.state", "companion": name, "talking": true})

	id := fmt.Sprintf("chatcmpl-556-%d", time.Now().UnixNano())
	created := time.Now().Unix()
	var sse func(delta map[string]any, finish any, usage any)
	if req.Stream {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.WriteHeader(200)
		fl, _ := w.(http.Flusher)
		sse = func(delta map[string]any, finish any, usage any) {
			c := map[string]any{"id": id, "object": "chat.completion.chunk", "created": created, "model": "556",
				"choices": []any{map[string]any{"index": 0, "delta": delta, "finish_reason": finish}}}
			if usage != nil {
				c["usage"] = usage
			}
			b, _ := json.Marshal(c)
			_, _ = io.WriteString(w, "data: "+string(b)+"\n\n")
			if fl != nil {
				fl.Flush()
			}
		}
		sse(map[string]any{"role": "assistant"}, nil, nil)
	}

	system := ""
	if r.Header.Get("X-556-Voice") == "1" { // a spoken turn: short, speakable reply
		system = voice.Load(a.voicePath()).HandsFree.SpokenStyle
	}
	res, err := cl.Chat(ctx, text, key, sid, system)
	if res.Reply != "" { // her reply arrives whole (see hermesapi.Chat); the windows render it as one delta
		a.emit(map[string]any{"type": "chat.delta", "companion": name, "text": res.Reply})
		if sse != nil {
			sse(map[string]any{"content": res.Reply}, nil, nil)
		}
	}
	if bound {
		a.markOwn(name, sid) // the follower must not replay the app's own turn
	} else if res.SessionID != "" && res.SessionID != slot.id {
		slot.id = res.SessionID
		_ = companions.SetCompanionField(a.mgr.Dir(name), "app_session_id", slot.id)
	}
	status := res.Status
	reply := res.Reply
	if err != nil {
		log.Printf("[api] %s: hermes api error: %v", name, err)
		a.emit(map[string]any{"type": "chat.error", "companion": name, "message": err.Error()})
		if reply == "" {
			reply = "（她好像遇到了問題：" + err.Error() + "）"
		}
		status = "error"
	} else if res.Err != "" {
		a.emit(map[string]any{"type": "chat.error", "companion": name, "message": res.Err})
		if reply == "" {
			reply = "（她好像遇到了問題：" + res.Err + "）"
			status = "error"
		}
	}
	if ctx.Err() != nil {
		status = "timeout"
	}

	a.emit(map[string]any{"type": "chat.complete", "companion": name, "text": reply, "status": status, "usage": res.Usage})
	a.emit(map[string]any{"type": "companion.state", "companion": name, "talking": false})
	a.bubble(name, reply)
	if status == "stop" && reply != "" && a.settings.Get().MirrorToTelegram {
		go a.mirrorToTelegram(name, text, reply)
	}
	if sse != nil {
		sse(map[string]any{}, status, res.Usage)
		_, _ = io.WriteString(w, "data: [DONE]\n\n")
		if fl, ok := w.(http.Flusher); ok {
			fl.Flush()
		}
		return
	}
	writeJSON(w, 200, map[string]any{
		"id": id, "object": "chat.completion", "created": created, "model": "556",
		"choices": []any{map[string]any{"index": 0, "finish_reason": status,
			"message": map[string]any{"role": "assistant", "content": reply}}},
		"usage": res.Usage,
	})
}

// mirrorToTelegram (c): echo an app exchange into your Telegram DM as plain text,
// through her own bot token. No LLM; her gateway never sees its own bot's messages, so no loop.
func (a *API) mirrorToTelegram(name, question, answer string) {
	a.sendTelegram(name, "你問我："+strings.TrimSpace(question)+"\n\n我說："+strings.TrimSpace(answer))
}

// sendTelegram sends plain text to her home channel through her own bot (no LLM): the app mirror,
// and her event-turn answers when she speaks first (same path, by design).
func (a *API) sendTelegram(name, text string) {
	env := a.mgr.Env(name)
	token := env["TELEGRAM_BOT_TOKEN"]
	chat := companions.TelegramChat(env)
	if token == "" || chat == "" {
		return
	}
	if rs := []rune(text); len(rs) > 3900 {
		text = string(rs[:3900]) + "…"
	}
	body, _ := json.Marshal(map[string]any{"chat_id": chat, "text": text, "disable_notification": true})
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, "https://api.telegram.org/bot"+token+"/sendMessage", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		log.Printf("[api] %s: telegram mirror failed: %v", name, err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		data, _ := io.ReadAll(io.LimitReader(resp.Body, 300))
		log.Printf("[api] %s: telegram mirror HTTP %d: %s", name, resp.StatusCode, strings.TrimSpace(string(data)))
	}
}

// history returns the last N turns (2N messages) of her conversation — every surface, each message
// tagged with where it came from.
func (a *API) history(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, OPTIONS") {
		return
	}
	turns := a.settings.Get().ContextTurns
	if v, err := strconv.Atoi(r.URL.Query().Get("limit")); err == nil && v > 0 {
		turns = v
	}
	name, _, err := a.target(r)
	if err != nil {
		writeJSON(w, 200, map[string]any{"session_id": "", "turns": turns, "messages": []any{}, "note": err.Error()})
		return
	}
	sid := a.currentConversation(name)
	if sid == "" {
		writeJSON(w, 200, map[string]any{"session_id": "", "companion": name, "turns": turns, "messages": []any{}})
		return
	}
	msgs, err := a.mgr.Transcript(name).Messages(sid, turns*2, a.channelName(name))
	if err != nil {
		writeJSON(w, 502, map[string]any{"error": err.Error()})
		return
	}
	if msgs == nil {
		msgs = []companions.Message{}
	}
	writeJSON(w, 200, map[string]any{"session_id": sid, "companion": name, "turns": turns, "messages": msgs})
}

func (a *API) settingsHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, PUT, OPTIONS") {
		return
	}
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, 200, map[string]any{"settings": a.settings.Get(),
			"notes": map[string]any{"companion": "companion_name / avatar_model apply to the selected companion (companion.json)"}})
	case http.MethodPut:
		body, _ := io.ReadAll(r.Body)
		next, ap, err := a.settings.Update(body)
		if err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		if sel := next.SelectedCompanion; sel != "" {
			info := a.mgr.Info(sel)
			a.emit(map[string]any{"type": "companion.selected", "companion": sel, "display_name": info.DisplayName,
				"avatar_model_url": "/" + strings.TrimPrefix(info.AvatarModel, "/")})
		}
		writeJSON(w, 200, map[string]any{"settings": next, "restart_required": ap.RestartRequired, "reembed_required": ap.ReembedRequired})
	default:
		writeJSON(w, 405, map[string]any{"error": "method not allowed"})
	}
}

// companion describes the SELECTED companion (what the chat window and the avatar show).
func (a *API) companion(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, OPTIONS") {
		return
	}
	sel := a.selectedName()
	if sel == "" {
		writeJSON(w, 200, map[string]any{"name": "", "profile": "", "active": false, "hermes_connected": false,
			"avatar_model_url": "/" + strings.TrimPrefix(a.settings.Get().AvatarModel, "/")})
		return
	}
	info := a.mgr.Info(sel)
	writeJSON(w, 200, map[string]any{
		"name": info.DisplayName, "profile": sel, "active": info.Active,
		"avatar_model_url": "/" + strings.TrimPrefix(info.AvatarModel, "/"),
		"hermes_connected":  info.HermesConnected,
		"channels":          info.Channels,
	})
}

// restartHermes restarts her one process (gateway = API server + channels); the app's
// conversation continues by session id afterwards.
func (a *API) restartHermes(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, 405, map[string]any{"error": "POST only"})
		return
	}
	name, _, err := a.target(r)
	if err != nil {
		writeJSON(w, 409, map[string]any{"error": err.Error()})
		return
	}
	if err := a.sup.Restart("gateway:" + name); err != nil {
		writeJSON(w, 500, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, 202, map[string]any{"ok": true, "note": name + ": restarting; the conversation continues by session id"})
}

// bubble mirrors a reply onto the avatar (which follows the selected companion).
func (a *API) bubble(name, text string) {
	if a.bridge == nil || strings.TrimSpace(text) == "" {
		return
	}
	runes := []rune(text)
	if len(runes) > 120 {
		text = string(runes[:120])
	}
	ms := max(4000, min(12000, len([]rune(text))*120))
	a.bridge.Broadcast(map[string]any{"type": "message", "companion": name, "text": text, "duration": ms})
}

func contentText(c any) string {
	switch v := c.(type) {
	case string:
		return v
	case []any: // OpenAI content parts
		var sb strings.Builder
		for _, p := range v {
			if pm, ok := p.(map[string]any); ok {
				if t, _ := pm["text"].(string); t != "" {
					sb.WriteString(t)
				}
			}
		}
		return sb.String()
	}
	return ""
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

// openConversation runs right after a start: once her API answers, her one conversation is
// made to exist (create + Telegram routing stamp when none is live). A message never opens one;
// conversation() only falls back to the same code if a turn lands before this finished.
func (a *API) openConversation(name string) {
	deadline := time.Now().Add(90 * time.Second)
	for time.Now().Before(deadline) {
		info := a.mgr.Info(name)
		if !info.Active || info.Stopping {
			return
		}
		if info.HermesConnected {
			break
		}
		time.Sleep(time.Second)
	}
	cl := a.mgr.Client(name)
	if cl == nil {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if _, _, _, err := a.conversation(ctx, name, cl); err != nil {
		log.Printf("[api] %s: could not open her conversation at start: %v", name, err)
	}
}

// conversation resolves which Hermes session an app turn continues.
//
// A Telegram-bound companion has ONE conversation: her DM with you, keyed by the gateway as
// agent:main:telegram:dm:<chat>. The app joins it by id (X-Hermes-Session-Id; the gateway rebuilds
// context from state.db every turn, so both surfaces see one history). When it does not exist yet —
// the app spoke first — 556d creates it through her API and stamps the Telegram routing identity on
// the row, so her first Telegram message lands in the same session. Companions without a channel
// keep an app-only conversation (key 556:app, id persisted in companion.json).
func (a *API) conversation(ctx context.Context, name string, cl *hermesapi.Client) (key, id string, bound bool, err error) {
	chat := companions.TelegramChat(a.mgr.Env(name))
	if chat == "" {
		return appSessionKey, a.sessionSlot(name).id, false, nil
	}
	tr := a.mgr.Transcript(name)
	tkey := companions.TelegramKey(chat)
	a.openMu.Lock()
	defer a.openMu.Unlock()
	if id, err = tr.LiveSession("telegram", tkey); err != nil {
		return "", "", true, err
	}
	if id != "" {
		return "", id, true, nil
	}
	b := make([]byte, 3)
	_, _ = rand.Read(b)
	id = fmt.Sprintf("556_%s_%s", time.Now().Format("20060102_150405"), hex.EncodeToString(b))
	if err = cl.CreateSession(ctx, id, "telegram"); err != nil {
		return "", "", true, err
	}
	if serr := tr.StampRouting(id, "telegram", tkey, chat); serr != nil {
		log.Printf("[api] %s: conversation %s opened but not stamped for telegram (%v); Telegram will open its own and the app follows it", name, id, serr)
	} else {
		log.Printf("[api] %s: conversation %s opened (shared with telegram dm %s)", name, id, chat)
	}
	return "", id, true, nil
}

// currentConversation is the session the windows show: the shared one when she has a channel, else
// the app-only one.
func (a *API) currentConversation(name string) string {
	if chat := companions.TelegramChat(a.mgr.Env(name)); chat != "" {
		id, err := a.mgr.Transcript(name).LiveSession("telegram", companions.TelegramKey(chat))
		if err != nil {
			log.Printf("[api] %s: session store: %v", name, err)
		}
		return id
	}
	return a.sessionSlot(name).id
}

func (a *API) channelName(name string) string {
	if ch := companions.DetectChannels(a.mgr.Dir(name)); len(ch) > 0 {
		return ch[0]
	}
	return "channel"
}

// markOwn moves the follower past the app's own turn (its messages were broadcast live).
func (a *API) markOwn(name, sid string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	f := a.followers[name]
	if f == nil || f.sessionID != sid {
		return
	}
	if max, err := a.mgr.Transcript(name).MaxID(sid); err == nil && max > f.cursor {
		f.cursor = max
	}
	f.lastUser = "app"
}

// followLoop watches every active companion's conversation for turns that happened on her channels
// and shows them in the windows — the reverse of the Telegram mirror.
func (a *API) followLoop() {
	t := time.NewTicker(2 * time.Second)
	defer t.Stop()
	for range t.C {
		for _, info := range a.mgr.List() {
			if info.Active && !info.Stopping && info.HermesConnected && len(info.Channels) > 0 {
				a.follow(info.Name, info.Channels[0])
			}
		}
	}
}

func (a *API) follow(name, channel string) {
	chat := companions.TelegramChat(a.mgr.Env(name))
	if chat == "" {
		return
	}
	tr := a.mgr.Transcript(name)
	sid, err := tr.LiveSession("telegram", companions.TelegramKey(chat))
	if err != nil || sid == "" {
		return
	}
	a.mu.Lock()
	f := a.followers[name]
	if f == nil || f.sessionID != sid {
		max, _ := tr.MaxID(sid)
		a.followers[name] = &follower{sessionID: sid, cursor: max, lastUser: "app"} // a new conversation: start from now
		a.mu.Unlock()
		return
	}
	cursor, lastUser := f.cursor, f.lastUser
	a.mu.Unlock()
	msgs, err := tr.After(sid, cursor, channel, lastUser)
	if err != nil || len(msgs) == 0 {
		return
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if f != a.followers[name] {
		return
	}
	for _, m := range msgs {
		if m.ID <= f.cursor {
			continue
		}
		f.cursor = m.ID
		if m.Role == "user" {
			f.lastUser = m.Source
		}
		// her own event turn (the psyche engine speaks first): the user row is her prompt, not you — hidden;
		// her answer shows with source "event" and goes to Telegram like an app turn; silence shows nothing
		if m.Role == "user" && strings.HasPrefix(strings.TrimSpace(m.Text), "【事件】") {
			f.event = true
			continue
		}
		if f.event && m.Role == "assistant" {
			f.event = false
			if isSilence(m.Text) {
				continue
			}
			a.emit(map[string]any{"type": "chat.complete", "companion": name, "text": m.Text, "status": "stop", "source": "event"})
			a.emit(map[string]any{"type": "companion.state", "companion": name, "talking": false})
			a.bubble(name, m.Text)
			log.Printf("[api] %s: she spoke first (%d runes)%s", name, len([]rune(m.Text)), map[bool]string{true: " -> telegram", false: ""}[a.settings.Get().MirrorToTelegram])
			if a.settings.Get().MirrorToTelegram {
				go a.sendTelegram(name, m.Text)
			}
			continue
		}
		if m.Source == "app" {
			continue
		}
		switch m.Role {
		case "user":
			a.emit(map[string]any{"type": "chat.user", "companion": name, "text": m.Text, "source": m.Source})
			a.emit(map[string]any{"type": "companion.state", "companion": name, "talking": true})
		case "assistant":
			a.emit(map[string]any{"type": "chat.complete", "companion": name, "text": m.Text, "status": "stop", "source": m.Source})
			a.emit(map[string]any{"type": "companion.state", "companion": name, "talking": false})
			a.bubble(name, m.Text)
		}
	}
}
