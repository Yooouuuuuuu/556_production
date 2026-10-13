package shim

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

// Ordered JSON: the Python shim serializes with json.dumps(ensure_ascii=False), which keeps
// dict insertion order, uses ", " / ": " separators and emits raw UTF-8. Go maps sort keys,
// so anything whose exact text reaches the model (tool signatures, <tool_call> blocks,
// <tool_response> payloads) goes through this order-preserving representation instead.

type KV struct {
	Key string
	Val any
}

type OMap []KV

func (m OMap) Get(k string) (any, bool) {
	for _, kv := range m {
		if kv.Key == k {
			return kv.Val, true
		}
	}
	return nil, false
}

// decodeOrdered parses JSON into OMap / []any / json.Number / string / bool / nil.
func decodeOrdered(raw []byte) (any, error) {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	v, err := readValue(dec)
	if err != nil {
		return nil, err
	}
	return v, nil
}

func readValue(dec *json.Decoder) (any, error) {
	tok, err := dec.Token()
	if err != nil {
		return nil, err
	}
	switch t := tok.(type) {
	case json.Delim:
		switch t {
		case '{':
			om := OMap{}
			for dec.More() {
				kt, err := dec.Token()
				if err != nil {
					return nil, err
				}
				key, _ := kt.(string)
				val, err := readValue(dec)
				if err != nil {
					return nil, err
				}
				om = append(om, KV{key, val})
			}
			if _, err := dec.Token(); err != nil { // '}'
				return nil, err
			}
			return om, nil
		case '[':
			arr := []any{}
			for dec.More() {
				val, err := readValue(dec)
				if err != nil {
					return nil, err
				}
				arr = append(arr, val)
			}
			if _, err := dec.Token(); err != nil { // ']'
				return nil, err
			}
			return arr, nil
		}
		return nil, fmt.Errorf("unexpected delim %v", t)
	default:
		return tok, nil
	}
}

// marshalOrdered renders like Python's json.dumps(..., ensure_ascii=False).
func marshalOrdered(v any) string {
	var sb strings.Builder
	writeOrdered(&sb, v)
	return sb.String()
}

func writeOrdered(sb *strings.Builder, v any) {
	switch t := v.(type) {
	case nil:
		sb.WriteString("null")
	case bool:
		if t {
			sb.WriteString("true")
		} else {
			sb.WriteString("false")
		}
	case json.Number:
		sb.WriteString(t.String())
	case float64:
		sb.WriteString(strconv.FormatFloat(t, 'g', -1, 64))
	case int:
		sb.WriteString(strconv.Itoa(t))
	case string:
		sb.WriteString(pyQuote(t))
	case OMap:
		sb.WriteByte('{')
		for i, kv := range t {
			if i > 0 {
				sb.WriteString(", ")
			}
			sb.WriteString(pyQuote(kv.Key))
			sb.WriteString(": ")
			writeOrdered(sb, kv.Val)
		}
		sb.WriteByte('}')
	case []any:
		sb.WriteByte('[')
		for i, x := range t {
			if i > 0 {
				sb.WriteString(", ")
			}
			writeOrdered(sb, x)
		}
		sb.WriteByte(']')
	case map[string]any: // unordered fallback: Go's sorted keys
		var buf bytes.Buffer
		enc := json.NewEncoder(&buf)
		enc.SetEscapeHTML(false)
		_ = enc.Encode(t)
		sb.WriteString(pythonSeparators(strings.TrimRight(buf.String(), "\n")))
	default:
		var buf bytes.Buffer
		enc := json.NewEncoder(&buf)
		enc.SetEscapeHTML(false)
		_ = enc.Encode(t)
		sb.WriteString(strings.TrimRight(buf.String(), "\n"))
	}
}

// pyQuote escapes a string the way Python's json.dumps(ensure_ascii=False) does:
// \" \\ \n \r \t \b \f, other control chars as \u00XX, everything else raw.
func pyQuote(s string) string {
	var sb strings.Builder
	sb.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			sb.WriteString(`\"`)
		case '\\':
			sb.WriteString(`\\`)
		case '\n':
			sb.WriteString(`\n`)
		case '\r':
			sb.WriteString(`\r`)
		case '\t':
			sb.WriteString(`\t`)
		case '\b':
			sb.WriteString(`\b`)
		case '\f':
			sb.WriteString(`\f`)
		default:
			if r < 0x20 {
				fmt.Fprintf(&sb, `\u%04x`, r)
			} else {
				sb.WriteRune(r)
			}
		}
	}
	sb.WriteByte('"')
	return sb.String()
}
