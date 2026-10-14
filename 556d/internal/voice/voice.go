// Package voice holds the cloud STT / TTS connectors: configuration (home/voice.json, agency-level
// keys) and the two calls everything else will build on — Speak(text) -> audio bytes and
// Transcribe(audio) -> text. Only the OpenAI-compatible shape is implemented ("/audio/speech",
// "/audio/transcriptions"), which covers OpenAI, Groq (STT), Fish Audio, Azure OpenAI and most
// proxies; vendor-specific APIs (ElevenLabs, MiniMax, Azure Speech) are later adapters behind the
// same two methods. The voice feature itself (lipsync, push-to-talk) is future work; this makes
// the APIs connectable and testable from Settings.
package voice

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

type Provider struct {
	Kind     string `json:"kind"`               // none | openai-compatible | fish-audio
	BaseURL  string `json:"base_url"`           // e.g. https://api.openai.com/v1 or http://127.0.0.1:18765/v1
	APIKey   string `json:"api_key,omitempty"`  // stored here (local app); masked on the API
	Model    string `json:"model"`              // tts: gpt-4o-mini-tts / tts-1 … ; stt: whisper-large-v3-turbo / gpt-4o-mini-transcribe …
	Voice    string `json:"voice,omitempty"`    // tts only (fish-audio: the reference_id of her voice)
	Format   string `json:"format,omitempty"`   // tts only: mp3 | wav | opus (default mp3)
	Language string `json:"language,omitempty"` // stt only: ISO code hint, e.g. zh, ja, en
}

// HandsFree holds the conversation-mode loop parameters (the numbers tuned in the earlier
// voice_agent_vad.py) and the spoken-style hint added to voice turns.
type HandsFree struct {
	Threshold    float64 `json:"threshold"`      // VAD speech probability threshold
	MinSilenceMs int     `json:"min_silence_ms"` // silence that closes a cut
	PreRollS     float64 `json:"pre_roll_s"`     // audio kept before the detected start
	GraceS       float64 `json:"grace_s"`        // after a cut: wait this long for the voice to resume (same turn)
	MinTurnS     float64 `json:"min_turn_s"`     // shorter turns are blips
	MaxTurnS     float64 `json:"max_turn_s"`     // hard cap per turn
	EchoGuard    bool    `json:"echo_guard"`     // mute the mic while she speaks (speakers)
	SpokenStyle  string  `json:"spoken_style"`   // ephemeral system hint for voice turns
}

const DefaultSpokenStyle = "這一輪是語音對話：用口語回答，一到三句就好；不要條列、表情符號、網址或 Markdown 符號，數字和專有名詞用說得出口的寫法。"

func DefaultHandsFree() HandsFree {
	return HandsFree{Threshold: 0.5, MinSilenceMs: 500, PreRollS: 0.4, GraceS: 0.9, MinTurnS: 0.35, MaxTurnS: 30, EchoGuard: true, SpokenStyle: DefaultSpokenStyle}
}

type Config struct {
	TTS       Provider  `json:"tts"`
	STT       Provider  `json:"stt"`
	HandsFree HandsFree `json:"handsfree"`
}

func Default() Config {
	return Config{TTS: Provider{Kind: "none", Format: "mp3"}, STT: Provider{Kind: "none"}, HandsFree: DefaultHandsFree()}
}

func Load(path string) Config {
	c := Default()
	if b, err := os.ReadFile(path); err == nil {
		_ = json.Unmarshal(b, &c)
	}
	if c.TTS.Kind == "" {
		c.TTS.Kind = "none"
	}
	if c.STT.Kind == "" {
		c.STT.Kind = "none"
	}
	if c.STT.APIKey == "" && c.STT.Kind == c.TTS.Kind && c.STT.Kind != "none" {
		c.STT.APIKey = c.TTS.APIKey // same provider, same key (entered once)
	}
	d := DefaultHandsFree()
	if c.HandsFree.Threshold <= 0 {
		c.HandsFree.Threshold = d.Threshold
	}
	if c.HandsFree.MinSilenceMs <= 0 {
		c.HandsFree.MinSilenceMs = d.MinSilenceMs
	}
	if c.HandsFree.GraceS < 0 {
		c.HandsFree.GraceS = 0
	}
	if c.HandsFree.MaxTurnS <= 0 {
		c.HandsFree.MaxTurnS = d.MaxTurnS
	}
	return c
}

func Save(path string, c Config) error {
	b, _ := json.MarshalIndent(c, "", "  ")
	return os.WriteFile(path, b, 0o600)
}

// Masked returns a copy safe to send to the UI: keys replaced by a flag.
func (c Config) Masked() map[string]any {
	m := func(p Provider) map[string]any {
		return map[string]any{"kind": p.Kind, "base_url": p.BaseURL, "api_key_set": p.APIKey != "", "model": p.Model,
			"voice": p.Voice, "format": p.Format, "language": p.Language}
	}
	return map[string]any{"tts": m(c.TTS), "stt": m(c.STT), "handsfree": c.HandsFree}
}

// Override is one character's voice (home/profiles/<id>/voice.json). A provider block whose kind is
// "inherit" (or empty) uses the global connector; "none" switches that side off for this character;
// a configured block replaces it, and fields left empty (base_url, api_key, model, format, language)
// are filled from the global block of the same kind, so changing only the voice id is enough.
// Hands-free parameters are global (they are about your microphone, not the character).
type Override struct {
	TTS Provider `json:"tts"`
	STT Provider `json:"stt"`
}

const Inherit = "inherit"

func LoadOverride(path string) Override {
	o := Override{TTS: Provider{Kind: Inherit}, STT: Provider{Kind: Inherit}}
	if b, err := os.ReadFile(path); err == nil {
		_ = json.Unmarshal(b, &o)
	}
	if o.TTS.Kind == "" {
		o.TTS.Kind = Inherit
	}
	if o.STT.Kind == "" {
		o.STT.Kind = Inherit
	}
	return o
}

func SaveOverride(path string, o Override) error {
	b, _ := json.MarshalIndent(o, "", "  ")
	return os.WriteFile(path, b, 0o600)
}

// Masked returns the override safe for the UI: keys replaced by a flag.
func (o Override) Masked() map[string]any {
	m := func(p Provider) map[string]any {
		return map[string]any{"kind": p.Kind, "base_url": p.BaseURL, "api_key_set": p.APIKey != "", "model": p.Model,
			"voice": p.Voice, "format": p.Format, "language": p.Language}
	}
	return map[string]any{"tts": m(o.TTS), "stt": m(o.STT)}
}

// Effective is the config a character speaks and listens with: the global config with that
// character's override applied (profileDir "" = the global config alone).
func Effective(globalPath, profileDir string) Config {
	c := Load(globalPath)
	if profileDir == "" {
		return c
	}
	o := LoadOverride(filepath.Join(profileDir, "voice.json"))
	apply := func(dst *Provider, ov Provider) {
		switch ov.Kind {
		case Inherit, "":
			return
		case "none":
			*dst = Provider{Kind: "none"}
			return
		}
		if ov.Kind == dst.Kind {
			ov.BaseURL = firstNonEmpty(ov.BaseURL, dst.BaseURL)
			ov.APIKey = firstNonEmpty(ov.APIKey, dst.APIKey)
			ov.Model = firstNonEmpty(ov.Model, dst.Model)
			ov.Format = firstNonEmpty(ov.Format, dst.Format)
			ov.Language = firstNonEmpty(ov.Language, dst.Language)
		}
		*dst = ov
	}
	apply(&c.TTS, o.TTS)
	apply(&c.STT, o.STT)
	if c.STT.APIKey == "" && c.STT.Kind == c.TTS.Kind && c.STT.Kind != "none" {
		c.STT.APIKey = c.TTS.APIKey
	}
	return c
}

func (p Provider) Configured() bool { return p.Kind != "" && p.Kind != "none" }

func (p Provider) url(path string) string { return strings.TrimRight(p.BaseURL, "/") + path }

var client = &http.Client{Timeout: 90 * time.Second}

// Speak synthesizes text; returns audio bytes and their content type.
func (p Provider) Speak(ctx context.Context, text string) ([]byte, string, error) {
	if !p.Configured() {
		return nil, "", errors.New("tts: not configured")
	}
	format := p.Format
	if format == "" {
		format = "mp3"
	}
	var req *http.Request
	switch p.Kind {
	case "openai-compatible":
		body, _ := json.Marshal(map[string]any{"model": p.Model, "input": text, "voice": p.Voice, "response_format": format})
		req, _ = http.NewRequestWithContext(ctx, http.MethodPost, p.url("/audio/speech"), bytes.NewReader(body))
	case "fish-audio":
		// docs.fish.audio: POST /v1/tts, JSON body, the voice is reference_id, the model is a header
		body, _ := json.Marshal(map[string]any{"text": text, "reference_id": p.Voice, "format": format, "latency": "balanced", "normalize": true})
		req, _ = http.NewRequestWithContext(ctx, http.MethodPost, fishBase(p.BaseURL)+"/v1/tts", bytes.NewReader(body))
		req.Header.Set("model", firstNonEmpty(p.Model, "s1"))
	default:
		return nil, "", fmt.Errorf("tts: provider kind %q not implemented", p.Kind)
	}
	req.Header.Set("Content-Type", "application/json")
	if p.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+p.APIKey)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, "", fmt.Errorf("tts: %w", err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	if resp.StatusCode >= 300 {
		return nil, "", fmt.Errorf("tts: HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(data[:min(len(data), 300)])))
	}
	ct := resp.Header.Get("Content-Type")
	if ct == "" {
		ct = map[string]string{"mp3": "audio/mpeg", "wav": "audio/wav", "opus": "audio/ogg"}[format]
	}
	return data, ct, nil
}

// Transcribe sends audio (multipart) and returns the text.
func (p Provider) Transcribe(ctx context.Context, audio []byte, filename string) (string, error) {
	if !p.Configured() {
		return "", errors.New("stt: not configured")
	}
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	var req *http.Request
	switch p.Kind {
	case "openai-compatible":
		_ = mw.WriteField("model", p.Model)
		if p.Language != "" {
			_ = mw.WriteField("language", p.Language)
		}
		fw, _ := mw.CreateFormFile("file", filename)
		_, _ = fw.Write(audio)
		_ = mw.Close()
		req, _ = http.NewRequestWithContext(ctx, http.MethodPost, p.url("/audio/transcriptions"), &buf)
	case "fish-audio":
		// docs.fish.audio: POST /v1/asr multipart (audio, language); the model is a header
		if p.Language != "" {
			_ = mw.WriteField("language", p.Language)
		}
		_ = mw.WriteField("ignore_timestamps", "true")
		_ = mw.WriteField("tag_audio_events", "false")
		fw, _ := mw.CreateFormFile("audio", filename)
		_, _ = fw.Write(audio)
		_ = mw.Close()
		req, _ = http.NewRequestWithContext(ctx, http.MethodPost, fishBase(p.BaseURL)+"/v1/asr", &buf)
		req.Header.Set("model", firstNonEmpty(p.Model, "transcribe-1"))
	default:
		return "", fmt.Errorf("stt: provider kind %q not implemented", p.Kind)
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())
	if p.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+p.APIKey)
	}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("stt: %w", err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if resp.StatusCode >= 300 {
		return "", fmt.Errorf("stt: HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(data[:min(len(data), 300)])))
	}
	var out struct {
		Text string `json:"text"`
	}
	if err := json.Unmarshal(data, &out); err != nil {
		return strings.TrimSpace(string(data)), nil // some servers return plain text
	}
	return cleanTranscript(out.Text), nil
}

func fishBase(u string) string {
	u = strings.TrimRight(strings.TrimSpace(u), "/")
	if u == "" {
		return "https://api.fish.audio"
	}
	return strings.TrimSuffix(u, "/v1")
}

func firstNonEmpty(a, b string) string {
	if strings.TrimSpace(a) != "" {
		return a
	}
	return b
}

var speakerTag = regexp.MustCompile(`<\|speaker:\d+\|>`)

// cleanTranscript drops Fish's inline speaker markers.
func cleanTranscript(s string) string { return strings.TrimSpace(speakerTag.ReplaceAllString(s, " ")) }

var (
	ruleLine   = regexp.MustCompile(`^[━─\-=*#>│|┃\s]+$`)
	htmlTag    = regexp.MustCompile(`<[^>]{1,40}>`)
	mdLink     = regexp.MustCompile(`\[([^\]]+)\]\([^)]+\)`)
	repeatPunc = regexp.MustCompile(`[-_=~・.]{3,}`)
	symbols    = regexp.MustCompile("[*#`_~━─│┃■□▶«»]+")
	emoji      = regexp.MustCompile(`[\x{1F000}-\x{1FAFF}\x{2600}-\x{27BF}\x{FE0F}\x{200D}]`)
	spaces     = regexp.MustCompile(`\s+`)
)

// Sanitize makes a chat reply speakable: no markdown, rules, tags, emoji or symbol noise.
func Sanitize(text string) string {
	var keep []string
	for _, l := range strings.Split(text, "\n") {
		if strings.TrimSpace(l) == "" || ruleLine.MatchString(strings.TrimSpace(l)) {
			continue
		}
		keep = append(keep, strings.TrimSpace(l))
	}
	out := strings.Join(keep, " ")
	out = mdLink.ReplaceAllString(out, "$1")
	out = htmlTag.ReplaceAllString(out, "")
	out = repeatPunc.ReplaceAllString(out, "")
	out = symbols.ReplaceAllString(out, "")
	out = emoji.ReplaceAllString(out, "")
	return strings.TrimSpace(spaces.ReplaceAllString(out, " "))
}
