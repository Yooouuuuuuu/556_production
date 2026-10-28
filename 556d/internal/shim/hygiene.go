package shim

import (
	"encoding/json"
	"log"
	"os"
	"strings"
	"sync"
)

// Prompt hygiene (docs/prompt/around-the-soul.md, prompt.md §2.8). Hermes composes her system prompt from the
// SOUL plus its own English guidance: who runs her (a Nous Research product with a docs URL), how to finish a
// job, how to batch tool calls, the mid-turn steering marker, the Windows host and the user's home path, the
// Python toolchain probe, which profile folder she lives in, and a trailer naming the model, provider and
// platform. None of it is hers, four blocks have no config switch, and vendor is never edited — so the shim,
// which sees every request on every platform, drops those paragraphs by their known shape before the request
// leaves. The filter is deterministic, so the prefix the provider caches stays byte-stable per session.
//
// A second hygiene rule lives here too: the proxy openmini answers through its own reply function
// (`openmini_reply(content)`, its anti-truncation device). A model told about our text tool protocol sometimes
// writes its reply as a text <tool_call> to that function; Hermes has no such tool and the turn is wasted. Such
// a call is unwrapped into plain reply text, never forwarded as a call.

// Paragraphs (blank-line separated blocks of the system message) that start with one of these are vendor text.
var vendorParagraphPrefixes = []string{
	"You run on Hermes Agent (by Nous Research).", // help guidance: no switch
	"# Finishing the job",                        // agent.task_completion_guidance (also switched off in config)
	"# Parallel tool calls",                      // agent.parallel_tool_call_guidance (also switched off)
	"## Mid-turn user steering",                  // steering note: no switch while tools are loaded
	"Host: ",                                     // environment hints: host OS, user home, cwd — no switch
	"Shell: on this Windows host",                // the Windows shell paragraph of the same block
	"You are running inside WSL",                 // the WSL variant
	"Python toolchain:",                          // environment probe (also switched off)
	"Active Hermes profile: ",                    // profile paths: no switch
}

// The timestamp paragraph ("Conversation started: …", "Today's date …", the Model / Provider / Platform trailer) is
// dropped whole: its weekday came out wrong in the first live check (Hermes said Monday for a Tuesday) and the
// clock line at the top of the state block carries date, weekday and time on every turn (prompt.md §2.7).
var vendorDateParagraphPrefixes = []string{"Conversation started:", "Today's date", "Timezone: ", "Session ID: ", "Model: "}

var (
	hygieneMu       sync.Mutex
	hygieneLastSig  string
	hygieneWarnOnce sync.Once
)

// pluginWrapperLine is a line Hermes wraps a plugin prompt section in: an English heading that names the plugin
// ("## Plugin Context: kokoro.memory") and HTML comments for its own reconstruction. The model needs none of them.
func pluginWrapperLine(line string) bool {
	t := strings.TrimSpace(line)
	return strings.HasPrefix(t, "<!-- hermes-plugin-section") || strings.HasPrefix(t, "## Plugin Context: ")
}

// stripPluginWrapper removes those lines from a paragraph; "" when nothing else was in it.
func stripPluginWrapper(p string) (string, bool) {
	if !strings.Contains(p, "hermes-plugin-section") && !strings.Contains(p, "## Plugin Context: ") {
		return p, false
	}
	var out []string
	for _, ln := range strings.Split(p, "\n") {
		if !pluginWrapperLine(ln) {
			out = append(out, ln)
		}
	}
	return strings.TrimSpace(strings.Join(out, "\n")), true
}

// filterSystem removes the vendor paragraphs, the trailer lines and the plugin-section wrapper from one system message.
func filterSystem(content string) string {
	if content == "" || !strings.Contains(content, "\n") {
		return content
	}
	if dump := os.Getenv("X556_SHIM_DUMP"); dump != "" && len(content) > 2000 { // debugging aid: her prompt as received, before the filter
		_ = os.WriteFile(dump, []byte(content), 0o644)
	}
	paras := strings.Split(content, "\n\n")
	kept := make([]string, 0, len(paras))
	var dropped []string
	sawHermes := false
	for _, p := range paras {
		t := strings.TrimSpace(p)
		isDate := false
		for _, pre := range vendorDateParagraphPrefixes {
			if strings.HasPrefix(t, pre) {
				isDate = true
				break
			}
		}
		if isDate {
			sawHermes = true
			dropped = append(dropped, "date")
			continue
		}
		isVendor := ""
		for _, pre := range vendorParagraphPrefixes {
			if strings.HasPrefix(t, pre) {
				isVendor = pre
				break
			}
		}
		if isVendor != "" {
			if strings.HasPrefix(isVendor, "You run on Hermes") {
				sawHermes = true
			}
			dropped = append(dropped, shortName(isVendor))
			continue
		}
		if q, touched := stripPluginWrapper(p); touched {
			if !containsPrefix(dropped, "plugin-wrapper") {
				dropped = append(dropped, "plugin-wrapper")
			}
			if q == "" {
				continue
			}
			p = q
		}
		kept = append(kept, p)
	}
	sig := strings.Join(dropped, ",")
	hygieneMu.Lock()
	changed := sig != hygieneLastSig
	hygieneLastSig = sig
	hygieneMu.Unlock()
	if changed {
		if len(dropped) > 0 {
			log.Printf("[shim] system prompt: dropped %d vendor paragraph(s): %s", len(dropped), sig)
		} else {
			log.Printf("[shim] system prompt: nothing to drop")
		}
	}
	if sawHermes && !containsPrefix(dropped, "help") {
		// a Hermes prompt without the help paragraph: the vendor text changed shape (a Hermes bump) — say so once
		hygieneWarnOnce.Do(func() {
			log.Printf("[shim] system prompt: Hermes prompt seen but the help-guidance paragraph was not found — vendor text changed? check docs/prompt/around-the-soul.md")
		})
	}
	return strings.Join(kept, "\n\n")
}

func shortName(prefix string) string {
	switch {
	case strings.HasPrefix(prefix, "You run on Hermes"):
		return "help"
	case strings.HasPrefix(prefix, "# Finishing"):
		return "finish"
	case strings.HasPrefix(prefix, "# Parallel"):
		return "parallel"
	case strings.HasPrefix(prefix, "## Mid-turn"):
		return "steer"
	case strings.HasPrefix(prefix, "Host:"):
		return "host"
	case strings.HasPrefix(prefix, "Shell:"):
		return "shell"
	case strings.HasPrefix(prefix, "You are running inside WSL"):
		return "wsl"
	case strings.HasPrefix(prefix, "Python toolchain"):
		return "probe"
	case strings.HasPrefix(prefix, "Active Hermes profile"):
		return "profile"
	}
	return prefix
}

func containsPrefix(list []string, s string) bool {
	for _, x := range list {
		if x == s {
			return true
		}
	}
	return false
}

// filterSystemMessages applies filterSystem to every system message of a parsed request body (the native-tools
// path; the text-protocol path filters inside toTextProtocol).
func filterSystemMessages(body map[string]any) {
	msgs, _ := body["messages"].([]any)
	for _, m := range msgs {
		mm, ok := m.(map[string]any)
		if !ok || mm["role"] != "system" {
			continue
		}
		if c, ok := mm["content"].(string); ok {
			mm["content"] = filterSystem(c)
		}
	}
}

// isProxyReplyFunction tells whether a parsed tool call is the proxy's own reply channel, not a Hermes tool.
func isProxyReplyFunction(name string) bool {
	return name == "openmini_reply" || strings.HasSuffix(name, ":openmini_reply")
}

// unwrapReplyFunction turns a text <tool_call> to the proxy's reply function back into reply text: its `content`
// argument joins the cleaned text, and the call is not forwarded. Other calls pass through unchanged.
func unwrapReplyFunction(calls []map[string]any, cleaned string) ([]map[string]any, string) {
	if len(calls) == 0 {
		return calls, cleaned
	}
	kept := calls[:0:0]
	parts := []string{}
	if strings.TrimSpace(cleaned) != "" {
		parts = append(parts, strings.TrimSpace(cleaned))
	}
	n := 0
	for _, c := range calls {
		fn, _ := c["function"].(map[string]any)
		name, _ := fn["name"].(string)
		if !isProxyReplyFunction(name) {
			kept = append(kept, c)
			continue
		}
		n++
		text := ""
		if args, ok := fn["arguments"].(string); ok {
			var m map[string]any
			if json.Unmarshal([]byte(args), &m) == nil {
				if s, ok := m["content"].(string); ok {
					text = s
				} else if s, ok := m["text"].(string); ok {
					text = s
				}
			}
		}
		if strings.TrimSpace(text) != "" {
			parts = append(parts, strings.TrimSpace(text))
		}
	}
	if n > 0 {
		log.Printf("[shim] unwrapped %d reply-function call(s) (openmini_reply) into plain text", n)
	}
	return kept, strings.Join(parts, "\n")
}


var toolNamesLast string

// logToolNames prints the tool names of a request once per distinct set — what the model is actually offered.
func logToolNames(raw rawParts) {
	names := make([]string, 0, len(raw.Tools))
	for _, t := range raw.Tools {
		var v struct {
			Function struct {
				Name string `json:"name"`
			} `json:"function"`
			Name string `json:"name"`
		}
		if json.Unmarshal(t, &v) == nil {
			if v.Function.Name != "" {
				names = append(names, v.Function.Name)
			} else if v.Name != "" {
				names = append(names, v.Name)
			}
		}
	}
	sig := strings.Join(names, ",")
	hygieneMu.Lock()
	changed := sig != toolNamesLast
	toolNamesLast = sig
	hygieneMu.Unlock()
	if changed {
		log.Printf("[shim] tools offered (%d): %s", len(names), sig)
	}
}
