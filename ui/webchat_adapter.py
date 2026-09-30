# Thin stand-in for Artemis's shiki_daemon (:19260) — serves just the API surface the
# web-chat SPA needs, and routes chat to the 556 shim (:18767) instead of
# Headroom/llama. Everything Artemis-specific (characters, mem0, worldbook, service
# control) returns benign empties; the SPA has built-in fallbacks for all of them.
import http.server
import json
import socketserver
import threading
import urllib.parse
import urllib.request

PORT = 19260
LIVE2D_BRIDGE = "http://127.0.0.1:19200"


def _push_bubble(raw_response):
    # Fire-and-forget: show the assistant reply as a speech bubble on the avatar.
    # Artemis's webchat drives the Live2D bridge the same way (plus TTS lipsync later).
    def worker():
        try:
            text = json.loads(raw_response)["choices"][0]["message"]["content"][:120]
            ms = max(4000, min(12000, len(text) * 120))
            urllib.request.urlopen(
                f"{LIVE2D_BRIDGE}/api/message?text={urllib.parse.quote(text)}&duration={ms}",
                timeout=5,
            ).read()
        except Exception:
            pass  # bridge offline is fine — chat still works

    threading.Thread(target=worker, daemon=True).start()
SHIM = "http://127.0.0.1:18767/v1/chat/completions"
MODELS = [
    {"id": "auto/556", "name": "Gemini 3.7 Flash (556)"},
    {"id": "auto/pro", "name": "Gemini 3.1 Pro"},
]
UPSTREAM_TIMEOUT = 180


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, payload, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/gateway-config":
            return self._send(200, {"baseUrl": "", "token": "", "models": MODELS})
        if path == "/api/status":
            return self._send(200, {"running": True, "backend": "556-shim"})
        if path == "/api/session-history":
            return self._send(200, {"messages": []})
        if path == "/api/mem0-search":
            return self._send(200, {"results": []})
        return self._send(404, {"error": "not implemented in 556 adapter"})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path != "/api/chat":
            return self._send(404, {"error": "not implemented in 556 adapter"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length))
            messages = req.get("messages", [])
            if req.get("systemPrompt"):
                messages = [{"role": "system", "content": req["systemPrompt"]}] + [
                    m for m in messages if m.get("role") != "system"
                ]
            upstream_body = {
                "model": req.get("model") or MODELS[0]["id"],
                "messages": messages,
                "stream": False,  # shim is non-streaming; SPA handles plain JSON fine
                "temperature": req.get("temperature", 0.7),
                "top_p": req.get("top_p", 0.9),
                "max_tokens": req.get("max_tokens", 4096),
            }
            upstream = urllib.request.Request(
                SHIM,
                data=json.dumps(upstream_body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(upstream, timeout=UPSTREAM_TIMEOUT) as resp:
                raw = resp.read()
            _push_bubble(raw)  # mirror the reply onto the Live2D avatar (Artemis webchat pattern)
            return self._send(200, raw)
        except Exception as exc:  # surface upstream failures to the SPA's error toast
            return self._send(502, {"error": f"shim upstream failed: {exc}"})

    def log_message(self, fmt, *args):
        pass  # keep the console quiet


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("127.0.0.1", PORT), Handler) as server:
        print(f"webchat adapter on :{PORT} -> {SHIM}")
        server.serve_forever()
