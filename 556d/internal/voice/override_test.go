package voice

import (
	"os"
	"path/filepath"
	"testing"
)

// A character's override over the global connectors: inherit keeps the global block, none switches
// the side off, a same-kind block fills its empty fields (key, base_url, model) from the global one.
func TestEffective(t *testing.T) {
	dir := t.TempDir()
	global := filepath.Join(dir, "voice.json")
	if err := Save(global, Config{
		TTS: Provider{Kind: "fish-audio", BaseURL: "https://api.fish.audio", APIKey: "k", Model: "s1", Voice: "ref-global"},
		STT: Provider{Kind: "fish-audio", BaseURL: "https://api.fish.audio", Model: "transcribe-1", Language: "zh"},
	}); err != nil {
		t.Fatal(err)
	}
	profile := filepath.Join(dir, "xi")
	_ = os.MkdirAll(profile, 0o755)

	// no override file at all: the global config
	e := Effective(global, profile)
	if e.TTS.Voice != "ref-global" || e.STT.APIKey != "k" {
		t.Fatalf("no override: %+v / %+v", e.TTS, e.STT)
	}

	// only the voice id differs; STT inherits; the key, base_url and model come from the global block
	if err := SaveOverride(filepath.Join(profile, "voice.json"), Override{TTS: Provider{Kind: "fish-audio", Voice: "ref-xi"}, STT: Provider{Kind: Inherit}}); err != nil {
		t.Fatal(err)
	}
	e = Effective(global, profile)
	if e.TTS.Voice != "ref-xi" || e.TTS.APIKey != "k" || e.TTS.BaseURL != "https://api.fish.audio" || e.TTS.Model != "s1" {
		t.Fatalf("partial override: %+v", e.TTS)
	}
	if e.STT.Kind != "fish-audio" || e.STT.Language != "zh" || e.STT.APIKey != "k" {
		t.Fatalf("stt inherit: %+v", e.STT)
	}

	// none switches a side off for this character only
	if err := SaveOverride(filepath.Join(profile, "voice.json"), Override{TTS: Provider{Kind: "none"}, STT: Provider{Kind: Inherit}}); err != nil {
		t.Fatal(err)
	}
	if e = Effective(global, profile); e.TTS.Configured() || !e.STT.Configured() {
		t.Fatalf("none: %+v / %+v", e.TTS, e.STT)
	}
	if g := Load(global); g.TTS.Voice != "ref-global" {
		t.Fatalf("global changed: %+v", g.TTS)
	}

	// a missing kind in the file reads as inherit
	_ = os.WriteFile(filepath.Join(profile, "voice.json"), []byte(`{"tts":{"voice":"x"}}`), 0o600)
	if o := LoadOverride(filepath.Join(profile, "voice.json")); o.TTS.Kind != Inherit || o.STT.Kind != Inherit {
		t.Fatalf("empty kind: %+v", o)
	}
}
