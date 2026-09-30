# hermes-shim — OpenAI-compatible router + tool-call translator for local Hermes agents.
#
# Lanes: Hermes sends model="auto/<lane>"; routing.json maps each lane to a backend.
#   qwen   backend → native tool-calls: request passed through unchanged (model swapped).
#   gemini backend → NO native tools: tools are injected into the prompt in Nous's
#                    <tool_call> text format, and <tool_call>{...}</tool_call> blocks in the
#                    reply are parsed back into structured OpenAI tool_calls.
# routing.json is re-read when its mtime changes → flip a lane without restarting.
# Stdlib only. Logs to shim.log next to this file.
import json, re, time, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTING_FILE = HERE / "routing.json"
LOG_FILE = HERE / "shim.log"
PORT = 18767  # 556 project shim — production shim owns 18766
TIMEOUT = 600

BACKENDS = {
    "qwen": {
        "base_url": "http://127.0.0.1:18002/v1",
        "model": "/mnt/c/localai/models/hub/Qwen3.6-27B-Balanced/Qwen3.6-27B-Uncensored-HauhauCS-Balanced-IQ3_XS.gguf",
        "native_tools": True,
    },
    "gemini": {
        "base_url": "http://localhost:18765/v1",
        "model": "agyapi/gemini-3.1-pro",
        "native_tools": False,
    },
    "claude": {   # best agentic coder available on the proxy; tools via text-format translation
        "base_url": "http://localhost:18765/v1",
        "model": "agyapi/claude-sonnet-4-6",
        "native_tools": False,
    },
    "claude-opus": {   # for the hardest tasks
        "base_url": "http://localhost:18765/v1",
        "model": "agyapi/claude-opus-4-6",
        "native_tools": False,
    },
    "gemini-flash": {   # fast/cheap gemini — the 556 chat default
        "base_url": "http://localhost:18765/v1",
        "model": "agyapi/gemini-3.7-flash",
        "native_tools": False,
    },
}

_lock = threading.Lock()
_routing_cache = {"mtime": 0.0, "data": {"default": "qwen", "lanes": {}}}

def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    with _lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)

DEBUG_FILE = HERE / "shim_debug.log"
def _dbg(tag, req):
    try:
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%H:%M:%S')} {tag} msgs={len(req.get('messages',[]))} =====\n")
            for m in req.get("messages", []):
                c = m.get("content") or ""
                f.write(f"[{m.get('role')}] ({len(c)}c) {c[:600]}\n")
    except Exception: pass
def _dbg_resp(resp):
    try:
        ch = (resp.get("choices") or [{}])[0]
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(f"<<< finish={ch.get('finish_reason')} content={repr((ch.get('message') or {}).get('content'))[:500]}\n")
    except Exception: pass

def routing():
    try:
        m = ROUTING_FILE.stat().st_mtime
        if m != _routing_cache["mtime"]:
            _routing_cache["data"] = json.loads(ROUTING_FILE.read_text(encoding="utf-8"))
            _routing_cache["mtime"] = m
    except FileNotFoundError:
        pass
    return _routing_cache["data"]

def pick_backends(model_name):
    """Resolve a lane to an ordered fallback chain of (name, backend). A lane may map to a single
    backend (string) or a list — the shim tries them in order until one succeeds. Used for the
    scarce-Claude 'code' lane: ["claude", "gemini"] = try Claude, fall back to Gemini on any error."""
    r = routing()
    lane = model_name.split("/", 1)[1] if model_name.startswith("auto/") else model_name
    spec = r.get("lanes", {}).get(lane, r.get("default", "qwen"))
    names = spec if isinstance(spec, list) else [spec]
    chain = [(n, BACKENDS[n]) for n in names if n in BACKENDS]
    return lane, (chain or [("qwen", BACKENDS["qwen"])])

# ---------- Nous <tool_call> text format ----------
TOOLS_PROMPT = (
    "You are a function calling AI model. You are provided with function signatures within "
    "<tools> </tools> XML tags. You may call one or more functions to assist with the user query. "
    "If available tools are not relevant, just respond in natural language. Don't make assumptions "
    "about values to plug into functions. After calling functions you will receive results within "
    "<tool_response> </tool_response> XML tags.\nHere are the available tools:\n<tools>\n{tools}\n</tools>\n"
    "When you decide to call a function, output EXACTLY one or more blocks of the form:\n"
    "<tool_call>\n{{\"name\": \"<function-name>\", \"arguments\": {{...}}}}\n</tool_call>\n"
    "Rules: the JSON inside <tool_call> MUST use double quotes and be valid JSON. Output NOTHING else "
    "on the lines of a <tool_call> block. If you are not calling a function, never emit <tool_call>.\n"
    "IMPORTANT: you have NO native/internal function-calling channel in this session. Never attempt to "
    "invoke a function through any built-in tool mechanism — ALWAYS write the <tool_call> block as plain "
    "text inside your normal reply. A native function call here will fail and produce an empty response."
)
TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

def to_text_protocol(body):
    """Rewrite an OpenAI tools request into a plain-chat request (Nous text format)."""
    tools = body.pop("tools", None) or []
    body.pop("tool_choice", None)
    body.pop("parallel_tool_calls", None)
    sigs = "\n".join(json.dumps(t.get("function", t), ensure_ascii=False) for t in tools)
    tools_block = TOOLS_PROMPT.format(tools=sigs) if tools else ""
    out, pending_tool = [], []

    def flush_tools():
        if pending_tool:
            joined = "\n".join(pending_tool)
            out.append({"role": "user", "content": joined})
            pending_tool.clear()

    for m in body.get("messages", []):
        role = m.get("role")
        if role == "system" and tools_block:
            out.append({"role": "system", "content": (m.get("content") or "") + "\n\n" + tools_block})
            tools_block = ""  # only once
        elif role == "assistant" and m.get("tool_calls"):
            flush_tools()
            content = m.get("content") or ""
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments")
                if isinstance(args, str):
                    try: args = json.loads(args)
                    except Exception: pass
                content += "\n<tool_call>\n" + json.dumps(
                    {"name": fn.get("name"), "arguments": args}, ensure_ascii=False) + "\n</tool_call>"
            out.append({"role": "assistant", "content": content.strip()})
        elif role == "tool":
            payload = {"name": m.get("name", ""), "content": m.get("content", "")}
            pending_tool.append("<tool_response>\n" + json.dumps(payload, ensure_ascii=False) + "\n</tool_response>")
        else:
            flush_tools()
            out.append({"role": role, "content": m.get("content") or ""})
    flush_tools()
    if tools_block:  # no system message existed
        out.insert(0, {"role": "system", "content": tools_block})
    body["messages"] = out
    return body

def parse_tool_calls(text):
    """Extract <tool_call> blocks -> (tool_calls list, cleaned text)."""
    calls = []
    def repl(match):
        raw = match.group(1)
        try:
            obj = json.loads(raw)
        except Exception:
            try:
                obj = json.loads(raw.replace("'", '"'))
            except Exception:
                log(f"unparseable tool_call block: {raw[:200]}")
                return match.group(0)  # leave in content
        calls.append({
            "id": f"shimcall_{len(calls)+1}_{int(time.time()*1000)%100000}",
            "type": "function",
            "function": {"name": obj.get("name", ""),
                         "arguments": json.dumps(obj.get("arguments", {}), ensure_ascii=False)},
        })
        return ""
    cleaned = TOOL_CALL_RE.sub(repl, text or "").strip()
    return calls, cleaned

# ---------- upstream ----------
def upstream(base_url, path, body):
    req = urllib.request.Request(base_url + path, method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(body).encode("utf-8"))
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())

# ---------- server ----------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_sse(self, payloads):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        def chunk(s):
            b = s.encode("utf-8")
            self.wfile.write(f"{len(b):X}\r\n".encode() + b + b"\r\n")
        for p in payloads:
            chunk("data: " + json.dumps(p, ensure_ascii=False) + "\n\n")
        chunk("data: [DONE]\n\n")
        self.wfile.write(b"0\r\n\r\n")

    def log_message(self, fmt, *args):  # silence default stderr logging
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            lanes = sorted(set(list(routing().get("lanes", {}).keys()) + ["tasks", "probe"]))
            data = [{"id": f"auto/{l}", "object": "model", "owned_by": "hermes-shim"} for l in lanes]
            self._send(200, {"object": "list", "data": data})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if "/chat/completions" not in self.path:
            self._send(404, {"error": "not found"}); return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except Exception as e:
            self._send(400, {"error": f"bad request: {e}"}); return
        want_stream = bool(body.get("stream"))
        original = body
        lane, chain = pick_backends(str(original.get("model", "")))
        last_err = None
        for idx, (bname, backend) in enumerate(chain):
            attempts = 1 if backend["native_tools"] else 4   # emulated backends fail intermittently (~50%): retry
            for att in range(1, attempts + 1):
                t0 = time.time()
                req = json.loads(json.dumps(original))   # fresh copy per attempt (text-protocol mutates)
                req["model"] = backend["model"]
                req["stream"] = False
                try:
                    if backend["native_tools"]:
                        resp = upstream(backend["base_url"], "/chat/completions", req)
                        log(f"lane={lane} -> {bname} passthrough {time.time()-t0:.1f}s")
                    else:
                        n_tools = len(req.get("tools") or [])
                        req = to_text_protocol(req)
                        resp = upstream(backend["base_url"], "/chat/completions", req)
                        msg = (resp.get("choices") or [{}])[0].get("message", {})
                        calls, cleaned = parse_tool_calls(msg.get("content", ""))
                        # relay glitch: empty text or its synthetic "[openmini/...] returned no text" marker
                        broken = (not calls) and (
                            not (cleaned or "").strip()
                            or (cleaned or "").strip().startswith("[openmini/")
                            or "returned no text" in (cleaned or ""))
                        if broken:
                            last_err = (502, f"{bname} empty/glitch response")
                            log(f"lane={lane} -> {bname} EMPTY (attempt {att}/{attempts}) {time.time()-t0:.1f}s"
                                + (" -> retrying" if att < attempts else ""))
                            continue
                        if calls:
                            msg["tool_calls"] = calls
                            msg["content"] = cleaned or None
                            resp["choices"][0]["finish_reason"] = "tool_calls"
                        resp["choices"][0]["message"] = msg
                        log(f"lane={lane} -> {bname} tools_in={n_tools} tool_calls_out={len(calls)} "
                            f"attempt={att} {time.time()-t0:.1f}s")
                    self._deliver(resp, want_stream)
                    return
                except urllib.error.HTTPError as e:
                    detail = ""
                    try: detail = e.read().decode("utf-8", "replace")[:300]
                    except Exception: pass
                    last_err = (e.code, detail)
                    log(f"lane={lane} -> {bname} HTTP {e.code}: {detail} (attempt {att}/{attempts})")
                except Exception as e:
                    last_err = (502, str(e))
                    log(f"lane={lane} -> {bname} ERROR {e} (attempt {att}/{attempts})")
            if idx + 1 < len(chain):
                log(f"lane={lane}: {bname} exhausted -> falling back")
        code, detail = last_err or (502, "no backend available")
        self._send(code if isinstance(code, int) else 502,
                   {"error": {"message": f"all backends failed for lane '{lane}': {detail}"}})

    def _deliver(self, resp, want_stream):
        if not want_stream:
            self._send(200, resp); return
        # fake-SSE: role chunk, full-delta chunk, finish chunk
        base = {"id": resp.get("id", "shim"), "object": "chat.completion.chunk",
                "created": resp.get("created", int(time.time())), "model": resp.get("model", "")}
        msg = resp["choices"][0]["message"]
        fin = resp["choices"][0].get("finish_reason", "stop")
        first = dict(base); first["choices"] = [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]
        delta = {}
        if msg.get("content"): delta["content"] = msg["content"]
        if msg.get("tool_calls"):
            delta["tool_calls"] = [
                {"index": i, "id": tc["id"], "type": "function",
                 "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}
                for i, tc in enumerate(msg["tool_calls"])]
        mid = dict(base); mid["choices"] = [{"index": 0, "delta": delta, "finish_reason": None}]
        lastc = dict(base); lastc["choices"] = [{"index": 0, "delta": {}, "finish_reason": fin}]
        if resp.get("usage"): lastc["usage"] = resp["usage"]
        self._send_sse([first, mid, lastc])

if __name__ == "__main__":
    if not ROUTING_FILE.exists():
        ROUTING_FILE.write_text(json.dumps(
            {"default": "qwen", "lanes": {"tasks": "qwen", "chat": "qwen", "digest": "gemini",
                                          "news": "gemini", "probe": "gemini", "teacher": "gemini"}}, indent=2),
            encoding="utf-8")
    log(f"shim starting on :{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
