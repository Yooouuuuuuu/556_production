package shim

import (
	"strings"
	"testing"
	"time"
)

// A system prompt shaped like the one Hermes 7166071f builds for a character (docs/prompt/prompt.md §1.2):
// the SOUL first, then the vendor paragraphs, kokoro's block, the timestamp with its trailer.
const sampleSystem = `# 角色甲

你是角色甲，三十歲。白天在一家公司上班。

## 說話的方式
- 用繁體中文，口語，像在傳訊息。

You run on Hermes Agent (by Nous Research). When the user needs help with Hermes itself — configuring, setting up, using, extending, or troubleshooting it — the documentation at https://hermes-agent.nousresearch.com/docs is the authoritative reference.

# Finishing the job
When the user asks you to build, run, or verify something, the deliverable is a working artifact backed by real tool output.

# Parallel tool calls
When you need several pieces of information that don't depend on each other, request them together.

## Mid-turn user steering
Mid-turn, the user can steer you: Hermes appends their message to the end of a tool result.

Host: Windows (11)
User home directory: C:\Users\someone
Current working directory: D:\dev\556_production
Note: on Windows, the machine hostname (e.g. from ` + "`hostname`" + ` or uname) is NOT the username.

Shell: on this Windows host your ` + "`terminal`" + ` tool runs commands through bash (git-bash / MSYS), NOT PowerShell.

Python toolchain: python3=missing, python=3.11.16, pip→python3.14, uv=installed.

Active Hermes profile: a. This session reads and writes C:/x/home/profiles/a/. Do NOT modify another profile's skills/plugins/cron/memories.

你在聊天視窗裡說話：純文字，不用 markdown。

<!-- hermes-plugin-sections:start -->
## Plugin Context: kokoro.memory
<!-- hermes-plugin-section-chars:339 -->

記憶：每一回合會附上一段「Memory」。

關於製作人：
# 你
- 名字：（尚未設定）
<!-- hermes-plugin-sections:end -->

Conversation started: Monday, October 13, 2026 (CST, UTC+08:00)
Today's date (as of the last context rebuild): Thursday, October 16, 2026 — trust this over the start date for what day it is now; query tools for exact time.
Model: auto/556
Provider: custom
Platform: api_server`

func TestFilterSystemDropsVendorTextKeepsHers(t *testing.T) {
	got := filterSystem(sampleSystem)
	for _, gone := range []string{"Nous Research", "Finishing the job", "Parallel tool calls", "Mid-turn user steering",
		"User home directory", "git-bash", "Python toolchain", "Active Hermes profile", "Model: auto/556", "Provider: custom", "Platform: api_server",
		"Conversation started", "Today's date", "Plugin Context", "hermes-plugin-section"} {
		if strings.Contains(got, gone) {
			t.Errorf("still contains %q", gone)
		}
	}
	for _, keep := range []string{"# 角色甲", "你是角色甲，三十歲", "## 說話的方式", "你在聊天視窗裡說話", "記憶：每一回合", "關於製作人", "名字：（尚未設定）"} {
		if !strings.Contains(got, keep) {
			t.Errorf("lost %q", keep)
		}
	}
	if strings.Contains(got, "\n\n\n") {
		t.Errorf("left a triple newline")
	}
	// byte-stable: the same input filters to the same output
	if filterSystem(sampleSystem) != got {
		t.Errorf("not deterministic")
	}
}

func TestFilterSystemLeavesForeignPromptsAlone(t *testing.T) {
	in := "You are a helpful assistant.\n\nAnswer in French."
	if filterSystem(in) != in {
		t.Errorf("a prompt without vendor text must pass unchanged")
	}
	if filterSystem("one line") != "one line" {
		t.Errorf("a one-line prompt must pass unchanged")
	}
}

func TestUnwrapReplyFunction(t *testing.T) {
	calls := []map[string]any{
		{"function": map[string]any{"name": "openmini_reply", "arguments": `{"content": "你怎麼了"}`}},
		{"function": map[string]any{"name": "kokoro_search", "arguments": `{"query": "x"}`}},
		{"function": map[string]any{"name": "default_api:openmini_reply", "arguments": `{"content": "第二句"}`}},
	}
	kept, text := unwrapReplyFunction(calls, "")
	if len(kept) != 1 || kept[0]["function"].(map[string]any)["name"] != "kokoro_search" {
		t.Fatalf("real tool call must survive: %v", kept)
	}
	if text != "你怎麼了\n第二句" {
		t.Errorf("text = %q", text)
	}
	kept, text = unwrapReplyFunction(nil, "plain")
	if len(kept) != 0 || text != "plain" {
		t.Errorf("no calls: %v %q", kept, text)
	}
}

func TestStripThinkRemovesTheScratchBeforeToolParsing(t *testing.T) {
	// a closed block before the reply
	vis, sc := stripThink("<think>\n他聽起來有點累。先別問。\n</think>\n嗯，今天還好嗎？")
	if vis != "嗯，今天還好嗎？" || sc != "<think>\n他聽起來有點累。先別問。\n</think>" {
		t.Fatalf("closed block: visible %q scratch %q", vis, sc)
	}
	// an unterminated block (the model ran out of tokens) leaks nothing
	vis, sc = stripThink("先說一句。\n<think>\n這裡還沒想完")
	if vis != "先說一句。" || sc != "<think>\n這裡還沒想完" {
		t.Fatalf("unterminated: visible %q scratch %q", vis, sc)
	}
	// a tool call written inside the scratch is not a tool call; one after it is
	text := "<think>\n<tool_call>\n{\"name\": \"web_search\", \"arguments\": {}}\n</tool_call>\n</think>\n<tool_call>\n{\"name\": \"kokoro_search\", \"arguments\": {\"query\": \"x\"}}\n</tool_call>"
	vis, sc = stripThink(text)
	calls, cleaned := parseToolCalls(vis, func() time.Time { return time.Unix(0, 0) })
	if len(calls) != 1 || calls[0]["function"].(map[string]any)["name"] != "kokoro_search" || cleaned != "" || !strings.Contains(sc, "web_search") {
		t.Fatalf("tool call inside the scratch was parsed: calls %d cleaned %q", len(calls), cleaned)
	}
	// prose that mentions the tag mid-line is left alone; a reply without a block is unchanged
	if vis, sc := stripThink("我不會寫 <think> 這種東西啦"); vis != "我不會寫 <think> 這種東西啦" || sc != "" {
		t.Fatalf("mid-line mention: %q %q", vis, sc)
	}
	if vis, sc := stripThink("還沒啦，我這兩天都在對採購的單子。"); sc != "" || vis != "還沒啦，我這兩天都在對採購的單子。" {
		t.Fatalf("plain reply changed: %q %q", vis, sc)
	}
}
