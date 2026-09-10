#!/usr/bin/env python3
"""Tiny OpenAI chat-completions mock (SSE streaming) for testing the pi runner without an API key.
Turn 1: returns a `bash` tool call writing out.txt. Turn 2 (after the tool result): returns text "DONE mock".
Usage: mock_openai.py <port>
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


def sse(handler, obj):
    handler.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
    handler.wfile.flush()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        if self.path.endswith("/models"):
            body = json.dumps({"object": "list", "data": [{"id": "mock-1", "object": "model"}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        msgs = req.get("messages", [])
        has_tool_result = any(m.get("role") == "tool" for m in msgs)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        cid = f"chatcmpl-{int(time.time()*1000)}"
        base = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": "mock-1"}
        if not has_tool_result and any(t.get("function", {}).get("name") == "bash" for t in req.get("tools", [])):
            sse(self, {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]})
            sse(self, {**base, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                       "function": {"name": "bash", "arguments": json.dumps({"command": "echo hello-from-mock > out.txt"})}}]}, "finish_reason": None}]})
            sse(self, {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                       "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}})
        else:
            sse(self, {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "DONE mock"}, "finish_reason": None}]})
            sse(self, {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 80, "completion_tokens": 3, "total_tokens": 83}})
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
