package api

import (
	"encoding/json"
	"strings"
	"testing"
)

// The 主動 sliders write psyche.json to the profile and to the package; the package copy must not carry this
// machine's zone (time.timezone_offset_h), which 556d writes into the profile before every start.
func TestPackageCopyDropsTheZone(t *testing.T) {
	var cur map[string]any
	if err := json.Unmarshal([]byte(`{"character":{"pronoun":"她"},"time":{"tick_s":60,"timezone_offset_h":8},"proactive":{"daily_cap":3}}`), &cur); err != nil {
		t.Fatal(err)
	}
	out := packageCopy(cur)
	if strings.Contains(string(out), "timezone_offset_h") {
		t.Fatalf("package copy carries the zone: %s", out)
	}
	var got map[string]any
	if err := json.Unmarshal(out, &got); err != nil {
		t.Fatal(err)
	}
	if got["time"].(map[string]any)["tick_s"] != 60.0 || got["proactive"].(map[string]any)["daily_cap"] != 3.0 || got["character"].(map[string]any)["pronoun"] != "她" {
		t.Fatalf("package copy lost a setting: %s", out)
	}
	if _, ok := cur["time"].(map[string]any)["timezone_offset_h"]; !ok {
		t.Fatal("the profile's own map must keep the zone")
	}
}
