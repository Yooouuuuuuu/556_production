package shim

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

// Parity tests: golden files were produced by the Python shim (shim/shim.py) via
// scratchpad/gen_golden.py. Any divergence in model-facing text is a real bug.

func load(t *testing.T, name string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("testdata", name))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestToTextProtocolParity(t *testing.T) {
	for _, name := range []string{"req_tools", "req_nosys"} {
		t.Run(name, func(t *testing.T) {
			rawBody := load(t, name+".json")
			var body map[string]any
			if err := json.Unmarshal(rawBody, &body); err != nil {
				t.Fatal(err)
			}
			var raw rawParts
			_ = json.Unmarshal(rawBody, &raw)
			out := toTextProtocol(body, raw)

			var got []map[string]any
			b, _ := json.Marshal(out["messages"])
			_ = json.Unmarshal(b, &got)
			var want []map[string]any
			if err := json.Unmarshal(load(t, "golden_"+name+".json"), &want); err != nil {
				t.Fatal(err)
			}
			if len(got) != len(want) {
				t.Fatalf("message count: got %d want %d", len(got), len(want))
			}
			for i := range want {
				if !reflect.DeepEqual(got[i], want[i]) {
					t.Errorf("message %d differs\n--- got ---\n%s\n--- want ---\n%s", i, got[i]["content"], want[i]["content"])
				}
			}
			for _, k := range []string{"tools", "tool_choice", "parallel_tool_calls"} {
				if _, ok := out[k]; ok {
					t.Errorf("%s should be removed", k)
				}
			}
		})
	}
}

func TestParseToolCallsParity(t *testing.T) {
	text := string(load(t, "reply_calls.txt"))
	calls, cleaned := parseToolCalls(text, func() time.Time { return time.Unix(0, 0) })
	var want struct {
		Cleaned string `json:"cleaned"`
		Calls   []struct {
			Name      string `json:"name"`
			Arguments string `json:"arguments"`
		} `json:"calls"`
	}
	if err := json.Unmarshal(load(t, "golden_reply_calls.json"), &want); err != nil {
		t.Fatal(err)
	}
	if cleaned != want.Cleaned {
		t.Errorf("cleaned text differs\n--- got ---\n%s\n--- want ---\n%s", cleaned, want.Cleaned)
	}
	if len(calls) != len(want.Calls) {
		t.Fatalf("calls: got %d want %d", len(calls), len(want.Calls))
	}
	for i, w := range want.Calls {
		fn := calls[i]["function"].(map[string]any)
		if fn["name"] != w.Name || fn["arguments"] != w.Arguments {
			t.Errorf("call %d: got %s %s want %s %s", i, fn["name"], fn["arguments"], w.Name, w.Arguments)
		}
	}
}
