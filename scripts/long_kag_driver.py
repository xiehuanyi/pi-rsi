"""Persistent supervisor and localhost-only result viewer for one bounded search."""
from __future__ import annotations

from collections import Counter
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from pi_rsi.util import atomic_write_json, atomic_write_text, read_json, now_iso


def serve(exp):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = self.path.split("?", 1)[0]
            allowed = {"/": "tree.html", "/tree.html": "tree.html", "/status.json": "DRIVER_STATUS.json",
                       "/report.txt": "REPORT.md", "/protocol.txt": "PROTOCOL.md",
                       "/results.txt": "delivery/RESULTS.md"}
            if route not in allowed:
                self.send_error(404)
                return
            p = exp / allowed[route]
            if not p.is_file() and route in ("/", "/tree.html"):
                body = ('<!doctype html><html lang="zh"><meta charset="utf-8">'
                        '<meta http-equiv="refresh" content="10"><title>Kaggriculture 长预算研究</title>'
                        '<body><h1>Kaggriculture 长预算研究</h1><p>正在建立起点评测与实验树。</p>'
                        '<p>24 小时 / 最多 96 个实验 / 2 路并行 / 每实验最长 40 分钟</p>'
                        '<p>此页每 10 秒自动刷新，结果出现后进入实验树。</p></body></html>').encode()
            elif p.is_file():
                body = p.read_bytes()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            kind = "text/html" if route in ("/", "/tree.html") else ("application/json" if route.endswith(".json") else "text/plain")
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/tree.html"
    atomic_write_json(exp / "PREVIEW.json", {"url": url, "pid": os.getpid()})
    return server, url


def terminate_tree(pid):
    pairs = [tuple(map(int, line.split())) for line in subprocess.check_output(
        ["ps", "-eo", "pid=,ppid="], text=True).splitlines()]
    targets = {pid}
    while True:
        more = {p for p, parent in pairs if parent in targets}
        if more <= targets:
            break
        targets |= more
    for p in targets:
        try:
            os.kill(p, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main():
    exp = Path(sys.argv[1]).resolve()
    guard = open(exp / ".driver.lock", "a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (exp / "STARTED.json").exists():
        raise SystemExit("search already started; inspect before resuming; budget must not reset")
    plan = read_json(exp / "PLAN.json")
    for relative, expected in plan["files"].items():
        if hashlib.sha256((exp / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"frozen file changed: {relative}")
    server, url = serve(exp)
    start = time.time()
    state = {"phase": "search", "started_at": now_iso(), "started_ts": start,
             "deadline_ts": start + plan["scheduling_seconds"], "driver_pid": os.getpid(), "url": url}
    atomic_write_json(exp / "STARTED.json", state)
    env = {**os.environ, "PYTHONPATH": str(HARNESS), "PYTHONUNBUFFERED": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    child = None
    requested_stop = threading.Event()

    def stop(signum, frame):
        requested_stop.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def refresh():
        tree = read_json(exp / "tree.json", {})
        counts = Counter(n["status"] for n in tree.get("nodes", []) if n["id"] != "root")
        best = next((n for n in tree.get("nodes", []) if n["id"] == tree.get("best")), {})
        state.update(updated_at=now_iso(), elapsed_s=round(time.time() - start), nodes=dict(counts),
                     best_node=best.get("id"), best_selection_score=best.get("score"))
        atomic_write_json(exp / "DRIVER_STATUS.json", state)
        atomic_write_text(exp / "STATUS.md", "# Kaggriculture 长预算研究\n\n" +
                          f"更新：{state['updated_at']}\n\n阶段：{state['phase']}；已用 {state['elapsed_s']/3600:.2f} 小时。\n\n" +
                          f"已完成 {counts['done']}，运行 {counts['running']}，评测 {counts['evaluating']}，失败 {counts['failed']}。\n\n" +
                          f"当前选择集最优：{best.get('id')} / {best.get('score')}。\n\n" +
                          f"[交互实验树]({url}) · [方案](PROTOCOL.md)\n\n" +
                          "选择分为本地搜索结果；确认在搜索结束且候选锁定后运行。\n")

    try:
        with (exp / "coordinator.log").open("w") as log:
            child = subprocess.Popen([sys.executable, "-m", "pi_rsi.cli", "run", str(exp)],
                                     cwd=HARNESS, env=env, stdout=log, stderr=subprocess.STDOUT)
            state["coordinator_pid"] = child.pid
            while child.poll() is None:
                if (time.time() >= state["deadline_ts"] or requested_stop.is_set()) and "stop_requested_ts" not in state:
                    state["stop_requested_ts"] = time.time()
                    state["stop_reason"] = "user_stop" if requested_stop.is_set() else "24h_budget"
                    child.send_signal(signal.SIGTERM)
                if "stop_requested_ts" in state and time.time() - state["stop_requested_ts"] > plan["drain_seconds"]:
                    terminate_tree(child.pid)
                    child.wait()
                    raise RuntimeError("search exceeded its bounded drain period")
                refresh()
                time.sleep(10)
        result = read_json(exp / "state.json", {})
        if child.returncode != 0 or result.get("status") != "finished":
            raise RuntimeError(f"search did not finish normally: exit={child.returncode}, state={result}")
        state["search_finished_at"] = now_iso()
        state["harness_stop_reason"] = result.get("stop_reason")
        if requested_stop.is_set():
            state["phase"] = "stopped"
        else:
            state["phase"] = "confirmation"
            refresh()
            with (exp / "delivery.log").open("w") as log:
                child = subprocess.Popen([sys.executable, str(HARNESS / "scripts/duel_delivery.py"), str(exp),
                                          "--confirmation-task", str(exp / "private/confirmation-task")],
                                         cwd=HARNESS, env=env, stdout=log, stderr=subprocess.STDOUT)
                state["delivery_pid"] = child.pid
                began = time.monotonic()
                while child.poll() is None:
                    if requested_stop.is_set() or time.monotonic() - began > 2700:
                        terminate_tree(child.pid)
                        child.wait()
                        raise RuntimeError("confirmation interrupted or timed out; preserve lock for inspection")
                    refresh()
                    time.sleep(10)
                if child.returncode:
                    raise RuntimeError("confirmation/package failed; see delivery.log")
            state["phase"] = "finished"
            state["comparison"] = read_json(exp / "delivery/comparison.json")
    except Exception:
        state["phase"] = "failed"
        state["error"] = traceback.format_exc()
        if child is not None and child.poll() is None:
            terminate_tree(child.pid)
            child.wait()
    finally:
        state["finished_at"] = now_iso()
        refresh()
    # Keep the result viewer available after research stops. No model calls here.
    while not requested_stop.wait(60):
        pass
    server.shutdown()


if __name__ == "__main__":
    main()
