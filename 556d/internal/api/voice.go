package api

import (
	"io"
	"context"
	"encoding/base64"
	"net/http"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/Yooouuuuuuu/556_production/556d/internal/voice"
)

// Voice connectors (global: home/voice.json; per character: home/profiles/<id>/voice.json, an
// override whose provider blocks may say "inherit"):
//   GET  /api/voice                  global config with keys masked
//   PUT  /api/voice                  merge; an empty api_key keeps the stored one
//   GET  /api/voice?companion=<id>   that character's override + the effective config
//   PUT  /api/voice?companion=<id>   merge into the override
//   POST /api/voice/test   {text?}: TTS the text, then STT the result when both are configured —
//                          a round trip that proves the connection; returns timings + the audio.
//                          ?companion= tests what that character would use.
// /api/voice/speak and /api/voice/transcribe use the effective config of ?companion= or, without
// it, of the character on stage — so each character can have a voice of its own.

var voiceMu sync.Mutex

func (a *API) voicePath() string { return filepath.Join(a.settings.home, "voice.json") }

// voiceCompanion is the character a request names (?companion= / X-556-Companion), "" for the global config.
func (a *API) voiceCompanion(r *http.Request) string {
	name := r.URL.Query().Get("companion")
	if name == "" {
		name = r.Header.Get("X-556-Companion")
	}
	return name
}

// voiceFor is the effective config for the named character, else the one on stage, else global.
func (a *API) voiceFor(r *http.Request) voice.Config {
	name := a.voiceCompanion(r)
	if name == "" {
		name = a.selectedName()
	}
	if name != "" && a.mgr.Exists(name) {
		return voice.Effective(a.voicePath(), a.mgr.Dir(name))
	}
	return voice.Load(a.voicePath())
}

// voiceOverrideHandler: GET / PUT one character's voice override (profile voice.json).
func (a *API) voiceOverrideHandler(w http.ResponseWriter, r *http.Request, name string) {
	if !a.mgr.Exists(name) {
		writeJSON(w, 404, map[string]any{"error": errNoCompanion.Error()})
		return
	}
	path := filepath.Join(a.mgr.Dir(name), "voice.json")
	cur := voice.LoadOverride(path)
	kinds := []string{voice.Inherit, "none", "openai-compatible", "fish-audio"}
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, 200, map[string]any{"companion": name, "voice": cur.Masked(), "effective": voice.Effective(a.voicePath(), a.mgr.Dir(name)).Masked(), "kinds": kinds})
	case http.MethodPut:
		var patch struct {
			TTS *voice.Provider `json:"tts"`
			STT *voice.Provider `json:"stt"`
		}
		if err := decodeJSON(r, &patch); err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		merge := func(dst *voice.Provider, src *voice.Provider) {
			if src == nil {
				return
			}
			key := dst.APIKey
			*dst = *src
			if strings.TrimSpace(src.APIKey) == "" {
				dst.APIKey = key
			}
			if dst.Kind == "" {
				dst.Kind = voice.Inherit
			}
		}
		merge(&cur.TTS, patch.TTS)
		merge(&cur.STT, patch.STT)
		if err := voice.SaveOverride(path, cur); err != nil {
			writeJSON(w, 500, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]any{"companion": name, "voice": cur.Masked(), "effective": voice.Effective(a.voicePath(), a.mgr.Dir(name)).Masked(), "kinds": kinds})
	default:
		writeJSON(w, 405, map[string]any{"error": "method not allowed"})
	}
}

func (a *API) voiceHandler(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "GET, PUT, OPTIONS") {
		return
	}
	voiceMu.Lock()
	defer voiceMu.Unlock()
	if name := a.voiceCompanion(r); name != "" {
		a.voiceOverrideHandler(w, r, name)
		return
	}
	cur := voice.Load(a.voicePath())
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, 200, map[string]any{"voice": cur.Masked(), "kinds": []string{"none", "openai-compatible", "fish-audio"}})
	case http.MethodPut:
		var patch struct {
			TTS       *voice.Provider  `json:"tts"`
			STT       *voice.Provider  `json:"stt"`
			HandsFree *voice.HandsFree `json:"handsfree"`
		}
		if err := decodeJSON(r, &patch); err != nil {
			writeJSON(w, 400, map[string]any{"error": err.Error()})
			return
		}
		merge := func(dst *voice.Provider, src *voice.Provider) {
			if src == nil {
				return
			}
			key := dst.APIKey
			*dst = *src
			if strings.TrimSpace(src.APIKey) == "" {
				dst.APIKey = key // keep the stored secret unless a new one is given
			}
			if dst.Kind == "" {
				dst.Kind = "none"
			}
		}
		merge(&cur.TTS, patch.TTS)
		merge(&cur.STT, patch.STT)
		if patch.HandsFree != nil {
			cur.HandsFree = *patch.HandsFree
		}
		if err := voice.Save(a.voicePath(), cur); err != nil {
			writeJSON(w, 500, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]any{"voice": cur.Masked()})
	default:
		writeJSON(w, 405, map[string]any{"error": "method not allowed"})
	}
}

func (a *API) voiceTest(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, 405, map[string]any{"error": "POST only"})
		return
	}
	var body struct {
		Text string `json:"text"`
	}
	_ = decodeJSON(r, &body)
	if strings.TrimSpace(body.Text) == "" {
		body.Text = "測試一下，我是五五六。"
	}
	cfg := a.voiceFor(r)
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Minute)
	defer cancel()
	out := map[string]any{}
	var audio []byte
	var ct string
	if cfg.TTS.Configured() {
		t0 := time.Now()
		data, c, err := cfg.TTS.Speak(ctx, body.Text)
		res := map[string]any{"ok": err == nil, "ms": time.Since(t0).Milliseconds()}
		if err != nil {
			res["error"] = err.Error()
		} else {
			audio, ct = data, c
			res["bytes"], res["content_type"] = len(data), c
			if len(data) <= 1<<20 {
				res["audio_data_url"] = "data:" + c + ";base64," + base64.StdEncoding.EncodeToString(data)
			}
		}
		out["tts"] = res
	} else {
		out["tts"] = map[string]any{"ok": false, "error": "not configured"}
	}
	if cfg.STT.Configured() {
		if audio == nil {
			out["stt"] = map[string]any{"ok": false, "error": "no audio to transcribe (TTS not configured or failed)"}
		} else {
			t0 := time.Now()
			ext := "mp3"
			if strings.Contains(ct, "wav") {
				ext = "wav"
			} else if strings.Contains(ct, "ogg") {
				ext = "ogg"
			}
			text, err := cfg.STT.Transcribe(ctx, audio, "test."+ext)
			res := map[string]any{"ok": err == nil, "ms": time.Since(t0).Milliseconds()}
			if err != nil {
				res["error"] = err.Error()
			} else {
				res["text"] = text
			}
			out["stt"] = res
		}
	} else {
		out["stt"] = map[string]any{"ok": false, "error": "not configured"}
	}
	writeJSON(w, 200, out)
}

// voiceTranscribe turns one recorded turn (raw audio body; Content-Type says the container) into
// text. ?lang= overrides the configured language hint.
func (a *API) voiceTranscribe(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, 405, map[string]any{"error": "POST only"})
		return
	}
	cfg := a.voiceFor(r)
	if !cfg.STT.Configured() {
		writeJSON(w, 409, map[string]any{"error": "STT is not configured (設定 → 語音連線)"})
		return
	}
	data, _ := io.ReadAll(io.LimitReader(r.Body, 25<<20))
	if len(data) < 100 {
		writeJSON(w, 400, map[string]any{"error": "no audio"})
		return
	}
	ext := "webm"
	ct := strings.ToLower(r.Header.Get("Content-Type"))
	for k, v := range map[string]string{"wav": "wav", "ogg": "ogg", "mpeg": "mp3", "mp3": "mp3", "mp4": "m4a", "m4a": "m4a", "webm": "webm"} {
		if strings.Contains(ct, k) {
			ext = v
		}
	}
	p := cfg.STT
	if l := r.URL.Query().Get("lang"); l != "" {
		p.Language = l
	}
	ctx, cancel := context.WithTimeout(r.Context(), 60*time.Second)
	defer cancel()
	t0 := time.Now()
	text, err := p.Transcribe(ctx, data, "turn."+ext)
	if err != nil {
		writeJSON(w, 502, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, 200, map[string]any{"text": text, "ms": time.Since(t0).Milliseconds(), "bytes": len(data)})
}

// voiceSpeak synthesizes a reply (sanitized for speech unless raw), caches the audio for the
// windows and tells the avatar to lip-sync it. {"action":"end"} just ends the lip-sync.
func (a *API) voiceSpeak(w http.ResponseWriter, r *http.Request) {
	if cors(w, r, "POST, OPTIONS") {
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, 405, map[string]any{"error": "POST only"})
		return
	}
	var body struct {
		Text   string `json:"text"`
		Raw    bool   `json:"raw"`
		Action string `json:"action"`
	}
	_ = decodeJSON(r, &body)
	switch body.Action {
	case "end":
		if a.bridge != nil {
			a.bridge.SpeakEnd()
		}
		writeJSON(w, 200, map[string]any{"ok": true})
		return
	case "playing":
		if a.bridge != nil {
			a.bridge.SpeakPlaying()
		}
		writeJSON(w, 200, map[string]any{"ok": true})
		return
	}
	text := strings.TrimSpace(body.Text)
	if !body.Raw {
		text = voice.Sanitize(text)
	}
	if text == "" {
		writeJSON(w, 400, map[string]any{"error": "nothing to say"})
		return
	}
	cfg := a.voiceFor(r)
	if !cfg.TTS.Configured() {
		writeJSON(w, 409, map[string]any{"error": "TTS is not configured (設定 → 語音連線)"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 90*time.Second)
	defer cancel()
	t0 := time.Now()
	data, ct, err := cfg.TTS.Speak(ctx, text)
	if err != nil {
		writeJSON(w, 502, map[string]any{"error": err.Error()})
		return
	}
	ext := "mp3"
	switch {
	case strings.Contains(ct, "wav"):
		ext = "wav"
	case strings.Contains(ct, "ogg") || strings.Contains(ct, "opus"):
		ext = "ogg"
	case strings.Contains(ct, "webm"):
		ext = "webm"
	}
	if a.bridge == nil {
		writeJSON(w, 500, map[string]any{"error": "no bridge"})
		return
	}
	name, err := a.bridge.CacheAudio(data, ext)
	if err != nil {
		writeJSON(w, 500, map[string]any{"error": err.Error()})
		return
	}
	url := "http://" + r.Host + "/cache/audio/" + name
	a.bridge.SpeakAudio(url, text)
	writeJSON(w, 200, map[string]any{"audio_url": url, "text": text, "ms": time.Since(t0).Milliseconds(), "bytes": len(data)})
}
