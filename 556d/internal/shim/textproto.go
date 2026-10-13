package shim

import (
	"bytes"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"
)

// toolsPrompt is the Nous <tool_call> text-protocol preamble. It must stay byte-identical to
// the Python shim's TOOLS_PROMPT: the parity tests compare rendered output.
const toolsPrompt = "You are a function calling AI model. You are provided with function signatures within " +
	"<tools> </tools> XML tags. You may call one or more functions to assist with the user query. " +
	"If available tools are not relevant, just respond in natural language. Don't make assumptions " +
	"about values to plug into functions. After calling functions you will receive results within " +
	"<tool_response> </tool_response> XML tags.\nHere are the available tools:\n<tools>\n%s\n</tools>\n" +
	"When you decide to call a function, output EXACTLY one or more blocks of the form:\n" +
	"<tool_call>\n{\"name\": \"<function-name>\", \"arguments\": {...}}\n</tool_call>\n" +
	"Rules: the JSON inside <tool_call> MUST use double quotes and be valid JSON. Output NOTHING else " +
	"on the lines of a <tool_call> block. If you are not calling a function, never emit <tool_call>.\n" +
	"IMPORTANT: you have NO native/internal function-calling channel in this session. Never attempt to " +
	"invoke a function through any built-in tool mechanism — ALWAYS write the <tool_call> block as plain " +
	"text inside your normal reply. A native function call here will fail and produce an empty response."

var toolCallRE = regexp.MustCompile(`(?s)<tool_call>\s*(\{.*?\})\s*</tool_call>`)

// marshal renders unordered Go values (response passthrough, SSE chunks) with raw UTF-8 and
// Python-style separators. Text that reaches the model uses marshalOrdered instead.
func marshal(v any) string {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(v)
	return pythonSeparators(strings.TrimRight(buf.String(), "\n"))
}

// pythonSeparators rewrites compact JSON ("a":1,"b":2) into Python's default ("a": 1, "b": 2).
func pythonSeparators(s string) string {
	var out strings.Builder
	inStr, esc := false, false
	for _, r := range s {
		if inStr {
			out.WriteRune(r)
			if esc {
				esc = false
			} else if r == '\\' {
				esc = true
			} else if r == '"' {
				inStr = false
			}
			continue
		}
		switch r {
		case '"':
			inStr = true
			out.WriteRune(r)
		case ',':
			out.WriteString(", ")
		case ':':
			out.WriteString(": ")
		default:
			out.WriteRune(r)
		}
	}
	return out.String()
}

func str(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

// rawParts carries the order-preserving pieces of a request that toTextProtocol renders as
// model-facing text.
type rawParts struct {
	Tools    []json.RawMessage `json:"tools"`
	Messages []json.RawMessage `json:"messages"`
}

// toTextProtocol rewrites an OpenAI tools request into a plain-chat request (Nous text
// format). body is mutated and returned; raw supplies key-ordered originals.
func toTextProtocol(body map[string]any, raw rawParts) map[string]any {
	delete(body, "tools")
	delete(body, "tool_choice")
	delete(body, "parallel_tool_calls")

	sigs := make([]string, 0, len(raw.Tools))
	for _, t := range raw.Tools {
		v, err := decodeOrdered(t)
		if err != nil {
			continue
		}
		if om, ok := v.(OMap); ok {
			if fn, ok := om.Get("function"); ok {
				v = fn
			}
		}
		sigs = append(sigs, marshalOrdered(v))
	}
	toolsBlock := ""
	if len(raw.Tools) > 0 {
		toolsBlock = fmt.Sprintf(toolsPrompt, strings.Join(sigs, "\n"))
	}

	var out []any
	var pendingTool []string
	flush := func() {
		if len(pendingTool) > 0 {
			out = append(out, map[string]any{"role": "user", "content": strings.Join(pendingTool, "\n")})
			pendingTool = nil
		}
	}

	for _, rm := range raw.Messages {
		v, err := decodeOrdered(rm)
		if err != nil {
			continue
		}
		m, _ := v.(OMap)
		roleV, _ := m.Get("role")
		role := str(roleV)
		contentV, _ := m.Get("content")
		content := str(contentV)
		callsV, _ := m.Get("tool_calls")
		calls, _ := callsV.([]any)

		switch {
		case role == "system" && toolsBlock != "":
			out = append(out, map[string]any{"role": "system", "content": content + "\n\n" + toolsBlock})
			toolsBlock = "" // only once
		case role == "assistant" && len(calls) > 0:
			flush()
			for _, c := range calls {
				tc, _ := c.(OMap)
				fnV, _ := tc.Get("function")
				fn, _ := fnV.(OMap)
				nameV, _ := fn.Get("name")
				args, _ := fn.Get("arguments")
				if s, ok := args.(string); ok {
					if parsed, err := decodeOrdered([]byte(s)); err == nil {
						args = parsed
					}
				}
				content += "\n<tool_call>\n" + marshalOrdered(OMap{{"name", nameV}, {"arguments", args}}) + "\n</tool_call>"
			}
			out = append(out, map[string]any{"role": "assistant", "content": strings.TrimSpace(content)})
		case role == "tool":
			nameV, _ := m.Get("name")
			if nameV == nil {
				nameV = ""
			}
			if contentV == nil {
				contentV = ""
			}
			payload := OMap{{"name", nameV}, {"content", contentV}}
			pendingTool = append(pendingTool, "<tool_response>\n"+marshalOrdered(payload)+"\n</tool_response>")
		default:
			flush()
			out = append(out, map[string]any{"role": role, "content": content})
		}
	}
	flush()
	if toolsBlock != "" { // no system message existed
		out = append([]any{map[string]any{"role": "system", "content": toolsBlock}}, out...)
	}
	body["messages"] = out
	return body
}

// parseToolCalls extracts <tool_call> blocks into OpenAI tool_calls and returns the cleaned text.
func parseToolCalls(text string, now func() time.Time) ([]map[string]any, string) {
	var calls []map[string]any
	cleaned := toolCallRE.ReplaceAllStringFunc(text, func(block string) string {
		rawBlock := toolCallRE.FindStringSubmatch(block)[1]
		v, err := decodeOrdered([]byte(rawBlock))
		if err != nil {
			v, err = decodeOrdered([]byte(strings.ReplaceAll(rawBlock, "'", `"`)))
			if err != nil {
				return block // unparseable: leave in content
			}
		}
		obj, _ := v.(OMap)
		nameV, _ := obj.Get("name")
		args, ok := obj.Get("arguments")
		if !ok || args == nil {
			args = OMap{}
		}
		calls = append(calls, map[string]any{
			"id":   fmt.Sprintf("shimcall_%d_%d", len(calls)+1, now().UnixMilli()%100000),
			"type": "function",
			"function": map[string]any{
				"name":      str(nameV),
				"arguments": marshalOrdered(args),
			},
		})
		return ""
	})
	return calls, strings.TrimSpace(cleaned)
}
