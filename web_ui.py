"""Chronicle Forge — browser-based pipeline UI.

Opens a local web interface for running the pipeline without any
command-line interaction. All options are set via the web form.

Usage:
    python web_ui.py             # opens http://localhost:5000
    python web_ui.py --port 8080

Features:
  - Full settings form (topic, duration, TTS, voice, style)
  - Resume from checkpoint checkbox
  - Real-time log stream with colour-coded output
  - Live image preview — updates as each scene is generated
  - Step progress bar (6 steps)
  - Elapsed timer
  - Download link for final MP4

Requires: pip install flask
"""
import collections
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Command used to launch the pipeline subprocess.
# On Windows we default to ["py", "-3.11"] (Windows Python Launcher) so the
# correct Python version is always selected regardless of which env runs the UI.
# Override via .env: PYTHON_EXEC=Z:\Programs\Anaconda\python.exe
_PY_CMD = [os.getenv("PYTHON_EXEC", sys.executable)]

try:
    from flask import Flask, Response, jsonify, request, send_file, stream_with_context
except ImportError:
    print("Flask not installed. Run: pip install flask")
    sys.exit(1)

app = Flask(__name__)
app.secret_key = os.urandom(16)

# ── Pipeline state ─────────────────────────────────────────────────────────────

_lock  = threading.Lock()
_state = {
    "running":     False,
    "step":        0,
    "step_label":  "idle",
    "return_code": None,
    "image_count": 0,
    "total_images": 0,
    "start_time":  None,
    "verbose":     False,
}

_log_buffer: collections.deque = collections.deque(maxlen=1000)
_clients:    list[queue.Queue]  = []
_proc:       subprocess.Popen | None = None

def _send_ctrlc():
    """
    Send CTRL_BREAK_EVENT to the pipeline subprocess.
    Python receives this as KeyboardInterrupt, which triggers the checkpoint-save
    handler in main.py, then exits cleanly.
    Requires the subprocess to be started with CREATE_NEW_PROCESS_GROUP so the
    signal reaches only that process group, not Flask itself.
    """
    with _lock:
        proc = _proc
    if proc is None or proc.poll() is not None:
        return
    try:
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
    except (OSError, AttributeError, PermissionError):
        pass


def _update_state(**kw):
    with _lock:
        _state.update(kw)


def _get_state() -> dict:
    with _lock:
        return dict(_state)


def _push_to_clients(item) -> None:
    """Deliver an item to every live SSE client queue. Drops dead clients."""
    dead = []
    for q in list(_clients):
        try:
            q.put_nowait(item)
        except queue.Full:
            dead.append(q)
    for q in dead:
        try:
            _clients.remove(q)
        except ValueError:
            pass


def _broadcast(line: str) -> None:
    """Append a log line to the buffer and push it to all SSE clients."""
    _log_buffer.append(line)
    _push_to_clients(("line", line))


def _push_event(data: dict) -> None:
    """Push a non-log state event to SSE clients only (not buffered)."""
    _push_to_clients(("event", data))


# ── Step detection ─────────────────────────────────────────────────────────────

_STEP_RE    = re.compile(r'\[(\d)/6\]')
_SCENE_RE   = re.compile(r'Scene (\d+)/(\d+)')
_TQDM_RE    = re.compile(r'it/s|Moviepy - Writing|chunk:')


def _parse_line(line: str):
    m = _STEP_RE.search(line)
    if m:
        _update_state(step=int(m.group(1)))
    m = _SCENE_RE.search(line)
    if m:
        _update_state(image_count=int(m.group(1)),
                      total_images=int(m.group(2)))


# ── Pipeline runner ────────────────────────────────────────────────────────────

def _run(params: dict):
    global _proc

    cmd = [*_PY_CMD, "main.py"]
    if params.get("model"):
        cmd += ["--model", params["model"]]
    if params.get("resume"):
        cmd.append("--resume")
    else:
        cmd += [
            "--topic",    params["topic"],
            "--duration", str(int(params.get("duration", 300))),
        ]
    # Only pass tts/style/voice when explicitly provided — omitting lets main.py
    # fall back to checkpoint values on resume, or its own defaults on fresh runs.
    if params.get("tts") in ("edge", "kokoro"):
        cmd += ["--tts", params["tts"]]
    if params.get("style") in ("stickman", "refined"):
        cmd += ["--style", params["style"]]
    if params.get("voice"):
        cmd += ["--voice", params["voice"]]
    if params.get("verbose"):
        cmd.append("--logging")
    _update_state(
        running=True, step=0, step_label="starting",
        return_code=None, start_time=time.time(),
        image_count=0, total_images=0,
        verbose=bool(params.get("verbose", False)),
    )
    # Notify any open browser tabs immediately so they switch to running state
    # even when the pipeline was started externally (e.g. via Agent CORE API).
    _push_event({"running": True, "step": 0, "verbose": bool(params.get("verbose", False))})

    try:
        _proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        _last_tqdm_t = [0.0]
        for line in _proc.stdout:
            line = line.rstrip()
            if line:
                _parse_line(line)
                if _TQDM_RE.search(line):
                    now = time.time()
                    if now - _last_tqdm_t[0] < 1.0:
                        continue
                    _last_tqdm_t[0] = now
                _broadcast(line)

        _proc.wait()
        rc = _proc.returncode
        # Check atomically: did the user stop it (api_stop already set "stopped")?
        # If so, preserve that label — don't overwrite with "error".
        with _lock:
            was_stopped = _state.get("step_label") == "stopped"
            if was_stopped:
                _state["return_code"] = rc
            else:
                _state.update({
                    "running":    False,
                    "return_code": rc,
                    "step_label": "done" if rc == 0 else "error",
                })
        label = "stopped" if was_stopped else ("done" if rc == 0 else "error")
        msg   = ("Stopped by user." if was_stopped else
                 "Pipeline complete." if rc == 0 else f"Pipeline exited with code {rc}.")
        _broadcast(f"[CF] {msg}")
    except Exception as exc:
        _broadcast(f"[CF ERROR] {exc}")
        _update_state(running=False, return_code=-1, step_label="error")
    finally:
        _proc = None


# ── Routes ─────────────────────────────────────────────────────────────────────

def _available_models():
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    response = requests.get(f"{base}/api/tags", timeout=5)
    response.raise_for_status()
    models = []
    for item in response.json().get("models", []):
        name = item.get("name") or item.get("model")
        if not name:
            continue
        details = requests.post(f"{base}/api/show", json={"model": name}, timeout=5)
        details.raise_for_status()
        info = details.json()
        # Embedding-only and other non-text models cannot write narration.
        if "completion" not in info.get("capabilities", []):
            continue
        cloud = bool(info.get("remote_host") or item.get("remote_host") or name.endswith(":cloud"))
        models.append({"name": name, "cloud": cloud})
    return sorted(models, key=lambda model: (model["cloud"], model["name"]))


@app.route("/api/models")
def api_models():
    try:
        return jsonify({"models": _available_models(),
                        "configured": os.getenv("OLLAMA_MODEL", "gemma4:e4b")})
    except (requests.RequestException, ValueError):
        return jsonify({"error": "Could not load models. Check that Ollama is running, then refresh."}), 503

@app.route("/api/start", methods=["POST"])
def api_start():
    if _get_state()["running"]:
        return jsonify({"error": "Pipeline already running"}), 409
    params = request.json or {}
    if not params.get("resume") and not params.get("topic", "").strip():
        return jsonify({"error": "topic is required"}), 400
    if "model" in params:
        try:
            available = {model["name"] for model in _available_models()}
        except (requests.RequestException, ValueError):
            return jsonify({"error": "Cannot verify selected model. Check Ollama and refresh models."}), 503
        if not isinstance(params["model"], str) or params["model"] not in available:
            return jsonify({"error": "Choose an available text model and try again."}), 400
    t = threading.Thread(target=_run, args=(params,), daemon=True)
    t.start()
    return jsonify({"status": "started"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Stop button in the UI — stops the pipeline, keeps Flask alive for a new run."""
    _broadcast("[CF SYS] Ctrl+C sent to pipeline — saving checkpoint...")
    _send_ctrlc()
    _update_state(running=False, step_label="stopped")
    return jsonify({"status": "stopped"})


@app.route("/api/close", methods=["POST"])
def api_close():
    """Tab close — stops the pipeline then exits Flask so the terminal also cleans up."""
    _send_ctrlc()
    _update_state(running=False, step_label="stopped")

    def _exit():
        time.sleep(1)   # let the response reach sendBeacon before we die
        os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
    return jsonify({"status": "closing"})


@app.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    return jsonify({"ok": True})


@app.route("/api/checkpoint")
def api_checkpoint():
    """Return the saved pipeline settings from the last checkpoint."""
    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "video_data.json")
    if not os.path.exists(data_path):
        return jsonify({"found": False})
    try:
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return jsonify({"found": False})
    out_dir   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    has_audio = (os.path.exists(os.path.join(out_dir, "narration.mp3")) or
                 os.path.exists(os.path.join(out_dir, "narration.wav")))
    return jsonify({
        "found":     True,
        "topic":     data.get("topic", ""),
        "duration":  data.get("target_seconds", 300),
        "tts":       data.get("tts", "edge"),
        "voice":     data.get("voice_key", "andrew"),
        "style":     data.get("style", "refined"),
        "has_audio": has_audio,
    })


@app.route("/api/services")
def api_services():
    """Check whether Ollama (11434) and InvokeAI (9090) are reachable."""
    import socket

    def _port_alive(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except OSError:
                return False

    return jsonify({
        "ollama":   _port_alive(11434),
        "invokeai": _port_alive(9090),
    })


@app.route("/api/clients")
def api_clients():
    """Number of browsers currently connected to the SSE stream."""
    return jsonify({"count": len(_clients)})


@app.route("/api/status")
def api_status():
    state = _get_state()
    if state.get("start_time"):
        state["elapsed_s"] = int(time.time() - state["start_time"])
    return jsonify(state)


@app.route("/api/stream")
def api_stream():
    """SSE endpoint — new connections receive the full log buffer then live updates.

    Pass ?skip_buffer=true to skip the replay (used by Agent CORE to avoid
    re-forwarding previous-run log lines to Telegram on reconnect).
    """
    client_q: queue.Queue = queue.Queue(maxsize=500)
    skip_buffer = request.args.get("skip_buffer", "").lower() == "true"

    if not skip_buffer:
        for line in list(_log_buffer):
            try:
                client_q.put_nowait(line)
            except queue.Full:
                break
    _clients.append(client_q)

    def event_gen():
        try:
            while True:
                try:
                    item = client_q.get(timeout=15)
                    if isinstance(item, tuple):
                        kind, payload = item
                        if kind == "event":
                            yield f"data: {json.dumps(payload)}\n\n"
                        else:
                            yield f"data: {json.dumps({'line': payload})}\n\n"
                    else:
                        # Plain string from buffer catchup
                        yield f"data: {json.dumps({'line': item})}\n\n"
                except queue.Empty:
                    yield 'data: {"heartbeat":true}\n\n'
        except GeneratorExit:
            try:
                _clients.remove(client_q)
            except ValueError:
                pass

    return Response(
        stream_with_context(event_gen()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/image/latest")
def api_image_latest():
    folder = os.path.join(os.path.dirname(__file__), "output", "images")
    if not os.path.isdir(folder):
        return jsonify({"image": None})
    pngs = [f for f in os.listdir(folder) if f.endswith(".png") and
            os.path.getsize(os.path.join(folder, f)) > 1024]
    if not pngs:
        return jsonify({"image": None})
    latest = max(pngs, key=lambda f: os.path.getmtime(os.path.join(folder, f)))
    mtime  = int(os.path.getmtime(os.path.join(folder, latest)) * 1000)
    return jsonify({"image": f"/api/image/file/{latest}", "name": latest, "mtime": mtime})


@app.route("/api/image/file/<filename>")
def api_image_file(filename):
    path = os.path.join(os.path.dirname(__file__), "output", "images", filename)
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, mimetype="image/png")


@app.route("/api/video")
def api_video():
    path = os.path.join(os.path.dirname(__file__), "output", "final_video.mp4")
    return jsonify({"video": "/api/video/file" if os.path.exists(path) else None})


@app.route("/api/video/file")
def api_video_file():
    path = os.path.join(os.path.dirname(__file__), "output", "final_video.mp4")
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, mimetype="video/mp4", as_attachment=True,
                     download_name="chronicle_forge.mp4")


_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="6" fill="#0d1117"/>'
    '<rect x="1" y="1" width="30" height="30" rx="5" fill="none"'
    ' stroke="#58a6ff" stroke-width="1.5"/>'
    # top sprocket holes (orange)
    '<rect x="3" y="3" width="4" height="3" rx="1" fill="#f0883e"/>'
    '<rect x="14" y="3" width="4" height="3" rx="1" fill="#f0883e"/>'
    '<rect x="25" y="3" width="4" height="3" rx="1" fill="#f0883e"/>'
    # bottom sprocket holes (orange)
    '<rect x="3" y="26" width="4" height="3" rx="1" fill="#f0883e"/>'
    '<rect x="14" y="26" width="4" height="3" rx="1" fill="#f0883e"/>'
    '<rect x="25" y="26" width="4" height="3" rx="1" fill="#f0883e"/>'
    # frame area outline
    '<rect x="3" y="8" width="26" height="16" rx="2" fill="none"'
    ' stroke="#58a6ff" stroke-width="0.8" opacity="0.5"/>'
    # C/F initials
    '<text x="16" y="20" text-anchor="middle"'
    ' font-family="Segoe UI,system-ui,sans-serif"'
    ' font-size="10" font-weight="700" fill="#58a6ff">C/F</text>'
    '</svg>'
)


@app.route("/favicon.svg")
def favicon():
    return Response(_FAVICON_SVG, content_type="image/svg+xml")


@app.route("/")
def index():
    return _HTML


# ── HTML / CSS / JS ────────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chronicle Forge</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}

/* ── Header ── */
header{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.logo{font-size:18px;font-weight:700;color:#e6edf3;letter-spacing:-0.3px}
.logo em{color:#58a6ff;font-style:normal}
.hdr-right{display:flex;align-items:center;gap:16px;font-size:12px;color:#8b949e}
.status-pill{display:flex;align-items:center;gap:6px;background:#0d1117;border:1px solid #30363d;border-radius:20px;padding:4px 10px}
.dot{width:7px;height:7px;border-radius:50%;background:#484f58;flex-shrink:0}
.dot.idle{background:#484f58}
.dot.running{background:#3fb950;animation:pulse 1.5s ease-in-out infinite}
.dot.done{background:#3fb950}
.dot.error{background:#f85149}
.dot.stopped{background:#d29922}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}

/* ── Layout ── */
.main{display:flex;flex:1;overflow:hidden}

/* ── Sidebar ── */
.sidebar{width:280px;min-width:280px;background:#161b22;border-right:1px solid #30363d;display:flex;flex-direction:column;overflow-y:auto}
.sidebar-inner{padding:16px;display:flex;flex-direction:column;gap:14px;flex:1}
.form-group{display:flex;flex-direction:column;gap:5px}
.form-label{font-size:11px;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.6px}
input[type=text]{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:7px 10px;border-radius:6px;font-size:13px;outline:none;width:100%;transition:border-color .15s}
input[type=text]:focus{border-color:#58a6ff}
select{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:7px 10px;border-radius:6px;font-size:13px;outline:none;width:100%;cursor:pointer}
select:focus{border-color:#58a6ff}

.range-row{display:flex;align-items:center;gap:8px}
input[type=range]{flex:1;-webkit-appearance:none;background:#21262d;height:4px;border-radius:2px;outline:none;cursor:pointer}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;background:#58a6ff;cursor:pointer;box-shadow:0 0 0 2px #0d1117}
.range-val{font-size:12px;color:#e6edf3;min-width:46px;text-align:right;font-weight:600}

.radio-group{display:flex;gap:6px}
.radio-opt{flex:1;border:1px solid #30363d;border-radius:6px;padding:7px 4px;text-align:center;cursor:pointer;font-size:12px;color:#8b949e;transition:all .15s;line-height:1.4}
.radio-opt:hover{border-color:#58a6ff44;color:#c9d1d9}
.radio-opt.active{border-color:#58a6ff;background:#0d1a2d;color:#58a6ff;font-weight:600}
.radio-opt small{display:block;font-size:10px;opacity:.65;margin-top:1px}

.divider{border:none;border-top:1px solid #21262d;margin:2px 0}
.resume-row{display:flex;align-items:center;gap:7px;font-size:12px;color:#8b949e;cursor:pointer;user-select:none}
.resume-row input{cursor:pointer;accent-color:#58a6ff}

.btn{width:100%;padding:9px;border:none;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s;letter-spacing:.2px}
.btn+.btn{margin-top:6px}
.btn-generate{background:#238636;color:#fff}
.btn-generate:hover:not(:disabled){background:#2ea043}
.btn-generate:disabled{background:#21262d;color:#484f58;cursor:not-allowed}
.btn-stop{background:#b62324;color:#fff;display:none}
.btn-stop:hover{background:#d33b3c}
.btn-secondary{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-secondary:hover{border-color:#58a6ff;color:#58a6ff}

.video-card{background:#0d2a1a;border:1px solid #3fb950;border-radius:6px;padding:10px;text-align:center;display:none}
.video-card a{color:#3fb950;font-weight:600;font-size:13px;text-decoration:none}
.video-card a:hover{text-decoration:underline}

/* ── Content ── */
.content{flex:1;display:flex;flex-direction:column;overflow:hidden;padding:14px;gap:10px}

/* ── Steps ── */
.steps-wrap{flex-shrink:0}
.steps-bar{display:flex;gap:5px;margin-bottom:4px}
.step-seg{flex:1;height:3px;background:#21262d;border-radius:2px;transition:background .4s}
.step-seg.done{background:#3fb950}
.step-seg.active{background:#58a6ff;animation:pulse 1.5s infinite}
.steps-labels{display:flex;gap:5px}
.step-lbl{flex:1;text-align:center;font-size:10px;color:#484f58;transition:color .3s}
.step-lbl.done{color:#3fb950}
.step-lbl.active{color:#58a6ff}

/* ── Log ── */
.log-wrap{flex:1;display:flex;flex-direction:column;background:#0d1117;border:1px solid #30363d;border-radius:6px;overflow:hidden;min-height:0}
.log-hdr{background:#161b22;border-bottom:1px solid #30363d;padding:6px 12px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
.log-hdr-left{font-size:11px;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}
.log-meta{font-size:11px;color:#484f58}
.log-body{flex:1;overflow-y:auto;padding:10px 12px;font-family:'Cascadia Code','Consolas','Courier New',monospace;font-size:11.5px;line-height:1.65}
.log-body::-webkit-scrollbar{width:5px}
.log-body::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px}
.ll{white-space:pre-wrap;word-break:break-all}
.ll.t-step{color:#58a6ff;font-weight:700}
.ll.t-pass{color:#d2a679}
.ll.t-prog{color:#3fb950}
.ll.t-warn{color:#d29922}
.ll.t-err{color:#f85149}
.ll.t-sys{color:#484f58;font-style:italic}
.ll.t-done{color:#3fb950;font-weight:600}

/* ── Image preview ── */
.preview-wrap{flex-shrink:0;height:200px;background:#161b22;border:1px solid #30363d;border-radius:6px;overflow:hidden;position:relative;display:flex;align-items:center;justify-content:center}
.preview-wrap img{max-width:100%;max-height:100%;object-fit:contain;opacity:0;transition:opacity .4s}
.preview-wrap img.loaded{opacity:1}
.preview-ph{color:#484f58;font-size:12px;text-align:center;line-height:1.6;pointer-events:none}
.preview-badge{position:absolute;bottom:7px;right:8px;font-size:10px;color:#8b949e;background:rgba(13,17,23,.85);padding:2px 6px;border-radius:3px;backdrop-filter:blur(4px)}
.preview-new{animation:flash .6s}
@keyframes flash{0%{box-shadow:0 0 0 2px #58a6ff}100%{box-shadow:none}}

/* ── Tooltip for radio hints ── */
[title]{cursor:help}

/* ── Service status (Ollama / InvokeAI) ── */
.svc-status{display:flex;align-items:center;gap:10px}
.svc-item{display:flex;align-items:center;gap:4px;font-size:11px;color:#484f58;white-space:nowrap}
.svc-dot{width:6px;height:6px;border-radius:50%;background:#484f58;flex-shrink:0;transition:background .3s}
.svc-item.online .svc-dot{background:#3fb950}
.svc-item.online span{color:#3fb950}
.svc-item.offline .svc-dot{background:#f85149}
.svc-item.offline span{color:#f85149}

/* ── Backend-dead toast ── */
.toast-overlay{position:fixed;inset:0;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;z-index:9999}
.toast-box{background:#161b22;border:2px solid #f85149;border-radius:10px;padding:28px 36px;text-align:center;max-width:380px;box-shadow:0 8px 32px rgba(0,0,0,.6)}
.toast-box h3{color:#f85149;font-size:16px;margin-bottom:10px}
.toast-box p{color:#8b949e;font-size:13px;line-height:1.7;margin-bottom:6px}
.toast-box code{color:#58a6ff;background:#0d1117;padding:2px 8px;border-radius:4px;font-family:monospace;font-size:12px}
</style>
</head>
<body>

<header>
  <div class="logo"><img src="/favicon.svg" width="26" height="26" style="vertical-align:middle;margin-right:7px;position:relative;top:-1px">Chronicle <em>Forge</em></div>
  <div class="hdr-right">
    <div class="svc-status">
      <div class="svc-item" id="svc-ollama" title="Ollama — local LLM (steps 1–3)">
        <div class="svc-dot"></div><span>Ollama</span>
      </div>
      <div class="svc-item" id="svc-invoke" title="InvokeAI — image generation (step 5)">
        <div class="svc-dot"></div><span>Invoke</span>
      </div>
    </div>
    <span id="elapsed" style="display:none;font-variant-numeric:tabular-nums"></span>
    <div class="status-pill">
      <div class="dot idle" id="dot"></div>
      <span id="status-text">Ready</span>
    </div>
  </div>
</header>

<div class="main">

  <!-- ── Sidebar ── -->
  <div class="sidebar">
  <div class="sidebar-inner">

    <div class="form-group">
      <label class="form-label">Topic</label>
      <input type="text" id="topic" placeholder="e.g. the invention of dynamite"
             onkeydown="if(event.key==='Enter')startPipeline()">
    </div>

    <div class="form-group">
      <label class="form-label">Duration</label>
      <div class="range-row">
        <input type="range" id="dur" min="180" max="900" step="60" value="300"
               oninput="updateDur()">
        <div class="range-val" id="dur-lbl">5 min</div>
      </div>
    </div>

    <div class="form-group">
      <label class="form-label" for="model">Text model</label>
      <select id="model" onchange="updateModelHint()"><option value="">Loading models…</option></select>
      <button type="button" onclick="loadModels()">Refresh models</button>
      <div id="model-hint" role="status" style="font-size:12px;margin-top:6px"></div>
    </div>

    <div class="form-group">
      <label class="form-label">TTS Engine</label>
      <div class="radio-group" id="tts-group">
        <div class="radio-opt active" data-val="edge" onclick="pickTTS(this)">
          edge-tts<small>online · Azure</small>
        </div>
        <div class="radio-opt" data-val="kokoro" onclick="pickTTS(this)">
          Kokoro<small>offline · CPU</small>
        </div>
      </div>
    </div>

    <div class="form-group">
      <label class="form-label">Voice</label>
      <select id="voice"></select>
    </div>

    <div class="form-group">
      <label class="form-label">Image Style</label>
      <div class="radio-group" id="style-group">
        <div class="radio-opt active" data-val="refined" onclick="pickStyle(this)"
             title="High-quality 2D illustration with cel shading">
          Refined<small>2D illus.</small>
        </div>
        <div class="radio-opt" data-val="stickman" onclick="pickStyle(this)"
             title="Simple stick figures, flat colors — Zenn aesthetic">
          Stickman<small>flat / Zenn</small>
        </div>
      </div>
    </div>

    <hr class="divider">

    <label class="resume-row">
      <input type="checkbox" id="verbose">
      Verbose logging
    </label>
    <label class="resume-row">
      <input type="checkbox" id="resume" onchange="onResumeChange()">
      Resume from checkpoint
    </label>
    <div id="resume-info" style="display:none;font-size:11px;color:#3fb950;padding:2px 0 4px;line-height:1.4"></div>

    <div style="margin-top:auto">
      <button class="btn btn-generate" id="btn-gen" onclick="startPipeline()">Generate Video</button>
      <button class="btn btn-stop" id="btn-stop" onclick="stopPipeline()">Stop Pipeline</button>
      <div class="video-card" id="video-card">
        ✓ Complete &mdash; <a href="/api/video/file" download="chronicle_forge.mp4">Download MP4</a>
      </div>
    </div>

  </div>
  </div>

  <!-- ── Content ── -->
  <div class="content">

    <!-- Step bar -->
    <div class="steps-wrap">
      <div class="steps-bar">
        <div class="step-seg" id="s1"></div>
        <div class="step-seg" id="s2"></div>
        <div class="step-seg" id="s3"></div>
        <div class="step-seg" id="s4"></div>
        <div class="step-seg" id="s5"></div>
        <div class="step-seg" id="s6"></div>
      </div>
      <div class="steps-labels">
        <div class="step-lbl" id="sl1">Research</div>
        <div class="step-lbl" id="sl2">Script</div>
        <div class="step-lbl" id="sl3">Metadata</div>
        <div class="step-lbl" id="sl4">TTS</div>
        <div class="step-lbl" id="sl5">Images</div>
        <div class="step-lbl" id="sl6">Video</div>
      </div>
    </div>

    <!-- Log terminal -->
    <div class="log-wrap">
      <div class="log-hdr">
        <span class="log-hdr-left">Live Output</span>
        <span class="log-meta" id="log-meta">0 lines</span>
      </div>
      <div class="log-body" id="log"></div>
    </div>

    <!-- Image preview -->
    <div class="preview-wrap" id="preview">
      <div class="preview-ph" id="preview-ph">
        Images will appear here as scenes are rendered
      </div>
      <img id="preview-img" alt="Latest scene">
      <div class="preview-badge" id="preview-badge" style="display:none"></div>
    </div>

  </div>
</div>

<script>
// ── Voice data ──────────────────────────────────────────────────────────────
const VOICES = {
  edge: {
    andrew:      'Andrew — US male, natural (default)',
    guy:         'Guy — US male, confident narrator',
    christopher: 'Christopher — US male, deep & authoritative',
    eric:        'Eric — US male, clear and engaging',
    aria:        'Aria — US female, warm and expressive',
    jenny:       'Jenny — US female, natural and clear',
    ryan:        'Ryan — British male, classic storyteller',
    sonia:       'Sonia — British female, elegant',
    william:     'William — Australian male, casual authority',
  },
  kokoro: {
    heart:   'Heart — US female, warm (default)',
    bella:   'Bella — US female, bright',
    sarah:   'Sarah — US female, natural',
    nova:    'Nova — US female, expressive',
    adam:    'Adam — US male',
    michael: 'Michael — US male, clear',
    george:  'George — British male, classic',
    lewis:   'Lewis — British male, strong',
    emma:    'Emma — British female, warm',
  },
};

// ── State ───────────────────────────────────────────────────────────────────
let tts         = 'edge';
let style       = 'refined';
let running     = false;
let currentStep = 0;
let verboseMode = false;
let logLines    = 0;
let sse         = null;
let pollImg     = null;
let pollStat    = null;
let lastMtime   = 0;
let startedAt   = null;
let elTimer     = null;
let resumeActive = false;

// ── Init ────────────────────────────────────────────────────────────────────
populateVoices('edge');
checkStatus();   // recover UI if page refreshed mid-run

// ── Backend-dead toast ───────────────────────────────────────────────────────
let _hbFailCount = 0;
let _backendDeadShown = false;
function showBackendDeadToast() {
  if (_backendDeadShown) return;
  _backendDeadShown = true;
  const overlay = document.createElement('div');
  overlay.className = 'toast-overlay';
  overlay.innerHTML =
    '<div class="toast-box">' +
    '<h3>&#9888; Backend Closed</h3>' +
    '<p>The Flask server was shut down<br>(another tab may have closed it).</p>' +
    '<p>Restart it in your terminal:</p>' +
    '<p><code>python web_ui.py</code></p>' +
    '</div>';
  document.body.appendChild(overlay);
}

// Heartbeat — tell the server the tab is alive every 5 s.
// Two consecutive failures → assume backend is gone, show toast.
setInterval(async () => {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 3000);
    await fetch('/api/heartbeat', { method: 'POST', signal: ctrl.signal });
    clearTimeout(t);
    _hbFailCount = 0;
  } catch {
    if (++_hbFailCount >= 2) showBackendDeadToast();
  }
}, 5000);

// ── Service status (Ollama / InvokeAI) ──────────────────────────────────────
async function checkServices() {
  try {
    const d = await fetch('/api/services').then(r => r.json());
    const setStatus = (id, online) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.classList.remove('online', 'offline');
      el.classList.add(online ? 'online' : 'offline');
    };
    setStatus('svc-ollama', d.ollama);
    setStatus('svc-invoke', d.invokeai);
  } catch {}
}
checkServices();
setInterval(checkServices, 15000);

// Tab/browser close → stop pipeline AND exit Flask (terminal also closes).
// /api/close is different from /api/stop: it calls os._exit(0) after signalling.
// pagehide fires on close, back-nav, and tab switch-away (more reliable than beforeunload).
window.addEventListener('pagehide',     () => { navigator.sendBeacon('/api/close'); });
window.addEventListener('beforeunload', () => { navigator.sendBeacon('/api/close'); });

// ── Text model selection ────────────────────────────────────────────────────
let textModels = [];
function updateModelHint() {
  const selected = textModels.find(m => m.name === document.getElementById('model').value);
  document.getElementById('model-hint').textContent = !selected
    ? 'Select a text model before starting.'
    : selected.cloud ? 'Cloud · requires internet and Ollama credits or a paid allowance.'
    : 'Local · uses your hardware, with no Ollama cloud charge. Other pipeline steps may use online services.';
}
async function loadModels() {
  const select = document.getElementById('model');
  const previous = select.value;
  select.disabled = true;
  document.getElementById('model-hint').textContent = 'Loading available text models…';
  try {
    const response = await fetch('/api/models');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not load models.');
    textModels = data.models;
    select.replaceChildren();
    if (!textModels.length) throw new Error('No text models found. Install a text model in Ollama, then refresh.');
    for (const model of textModels) {
      const option = document.createElement('option');
      option.value = model.name;
      option.textContent = `${model.name} · ${model.cloud ? 'Cloud' : 'Local'}`;
      select.appendChild(option);
    }
    let remembered = previous;
    try { remembered = remembered || localStorage.getItem('cf-text-model'); } catch {}
    // Prefer local inference on first use; keep explicit user choices thereafter.
    select.value = textModels.find(m => m.name === remembered)?.name
      || textModels.find(m => !m.cloud && m.name === data.configured)?.name
      || textModels.find(m => !m.cloud)?.name || textModels[0].name;
    updateModelHint();
  } catch (error) {
    select.replaceChildren(new Option('Models unavailable', ''));
    document.getElementById('model-hint').textContent = error.message;
  } finally { select.disabled = false; }
}
loadModels();

// ── Duration slider ─────────────────────────────────────────────────────────
function updateDur() {
  const s = +document.getElementById('dur').value;
  const m = Math.floor(s / 60), r = s % 60;
  document.getElementById('dur-lbl').textContent = r ? `${m}m ${r}s` : `${m} min`;
}

// ── Radio pickers ───────────────────────────────────────────────────────────
function pickTTS(el) {
  el.closest('.radio-group').querySelectorAll('.radio-opt').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  tts = el.dataset.val;
  populateVoices(tts);
}
function pickStyle(el) {
  el.closest('.radio-group').querySelectorAll('.radio-opt').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  style = el.dataset.val;
}
function pickTTSByVal(val) {
  document.querySelectorAll('#tts-group .radio-opt').forEach(el => {
    el.classList.toggle('active', el.dataset.val === val);
  });
  tts = val;
  populateVoices(val);
}
function pickStyleByVal(val) {
  document.querySelectorAll('#style-group .radio-opt').forEach(el => {
    el.classList.toggle('active', el.dataset.val === val);
  });
  style = val;
}
function lockFields(lockTTS) {
  resumeActive = true;
  document.getElementById('topic').disabled = true;
  document.getElementById('dur').disabled   = true;
  // Lock TTS + voice only when narration already exists; leave free when missing.
  if (lockTTS) {
    document.getElementById('voice').disabled = true;
    document.querySelectorAll('#tts-group .radio-opt').forEach(el => {
      el.style.pointerEvents = 'none';
      el.style.opacity       = '0.55';
    });
  }
  document.getElementById('btn-gen').textContent = '▶ Resume Pipeline';
}
function unlockFields() {
  resumeActive = false;
  document.getElementById('topic').disabled = false;
  document.getElementById('dur').disabled   = false;
  document.getElementById('voice').disabled = false;
  document.querySelectorAll('#tts-group .radio-opt').forEach(el => {
    el.style.pointerEvents = '';
    el.style.opacity       = '';
  });
  document.getElementById('btn-gen').textContent = 'Generate Video';
  document.getElementById('resume-info').style.display = 'none';
}
async function onResumeChange() {
  const checked = document.getElementById('resume').checked;
  if (!checked) { unlockFields(); return; }
  try {
    const d = await fetch('/api/checkpoint').then(r => r.json());
    if (!d.found) {
      document.getElementById('resume').checked = false;
      addLine('[CF] No checkpoint found — start a new run first.');
      return;
    }
    // Pre-fill topic/duration/TTS/voice from checkpoint (these are locked)
    document.getElementById('topic').value = d.topic || '';
    document.getElementById('dur').value   = d.duration || 300;
    updateDur();
    pickTTSByVal(d.tts || 'edge');
    document.getElementById('voice').value = d.voice || 'andrew';
    // Pre-select previous style but leave it unlocked so user can change it
    pickStyleByVal(d.style || 'refined');
    // Lock TTS + voice only when narration already exists
    lockFields(d.has_audio);
    const prevStyleLabel = d.style === 'stickman' ? 'Stickman' : 'Refined';
    const info = document.getElementById('resume-info');
    if (d.has_audio) {
      info.textContent = `Resuming: "${d.topic}" · Narration exists — TTS & voice locked · Previously: ${prevStyleLabel}`;
    } else {
      info.textContent = `Resuming: "${d.topic}" · No narration yet — choose TTS & voice below · Previously: ${prevStyleLabel}`;
    }
    info.style.display = 'block';
  } catch(e) {
    document.getElementById('resume').checked = false;
    addLine('[CF ERROR] Could not read checkpoint.');
  }
}

function populateVoices(engine) {
  const sel = document.getElementById('voice');
  sel.innerHTML = '';
  Object.entries(VOICES[engine]).forEach(([k, v]) => {
    const o = document.createElement('option');
    o.value = k; o.textContent = v;
    sel.appendChild(o);
  });
}

// ── Log helpers ─────────────────────────────────────────────────────────────
function classLine(line) {
  if (/^\[CF\]/.test(line))                          return 't-sys';
  if (/\[\d\/6\]/.test(line))                        return 't-step';
  if (/Pass [123]:|Expanding|annotation|prompts/i.test(line)) return 't-pass';
  if (/Scene \d+\/\d+|image \d/i.test(line))        return 't-prog';
  if (/Warning:/i.test(line))                        return 't-warn';
  if (/error|failed|crash/i.test(line))              return 't-err';
  if (/complete|saved|done|finished/i.test(line))    return 't-done';
  return '';
}

function addLine(line) {
  const cls = classLine(line);
  // In non-verbose mode, drop grey system lines ([CF] prefix).
  if (!verboseMode && cls === 't-sys') return;
  const body = document.getElementById('log');
  const d = document.createElement('div');
  d.className = 'll ' + cls;
  d.textContent = line;
  body.appendChild(d);
  body.scrollTop = body.scrollHeight;
  logLines++;
  document.getElementById('log-meta').textContent = logLines + ' lines';
}

// ── Step bar ─────────────────────────────────────────────────────────────────
function setSteps(cur) {
  for (let i = 1; i <= 6; i++) {
    const seg = document.getElementById('s' + i);
    const lbl = document.getElementById('sl' + i);
    if (i < cur)       { seg.className = 'step-seg done';   lbl.className = 'step-lbl done'; }
    else if (i === cur){ seg.className = 'step-seg active';  lbl.className = 'step-lbl active'; }
    else               { seg.className = 'step-seg';         lbl.className = 'step-lbl'; }
  }
}
function setAllDone() {
  for (let i = 1; i <= 6; i++) {
    document.getElementById('s' + i).className  = 'step-seg done';
    document.getElementById('sl' + i).className = 'step-lbl done';
  }
}

// ── UI state ─────────────────────────────────────────────────────────────────
function setRunning(on) {
  running = on;
  document.getElementById('btn-gen').style.display  = on ? 'none' : 'block';
  document.getElementById('btn-stop').style.display = on ? 'block' : 'none';
  document.getElementById('btn-gen').disabled = false;

  const dot = document.getElementById('dot');
  const txt = document.getElementById('status-text');
  if (on) {
    dot.className = 'dot running';
    txt.textContent = 'Running';
    startedAt = Date.now();
    document.getElementById('elapsed').style.display = 'inline';
    elTimer = setInterval(() => {
      const s = Math.floor((Date.now() - startedAt) / 1000);
      const m = Math.floor(s / 60), r = s % 60;
      document.getElementById('elapsed').textContent =
        m + ':' + String(r).padStart(2,'0');
    }, 1000);
  } else {
    dot.className = 'dot idle';
    txt.textContent = 'Ready';
    clearInterval(elTimer);
  }
}

// ── Image polling ─────────────────────────────────────────────────────────────
function startImgPoll() {
  if (pollImg) clearInterval(pollImg);
  pollImg = setInterval(async () => {
    // Only fetch during step 5 (image generation) — no-op otherwise.
    if (!running || currentStep !== 5) return;
    try {
      const d = await fetch('/api/image/latest').then(r => r.json());
      if (d.image && d.mtime > lastMtime) {
        lastMtime = d.mtime;
        const img  = document.getElementById('preview-img');
        const ph   = document.getElementById('preview-ph');
        const bdg  = document.getElementById('preview-badge');
        const wrap = document.getElementById('preview');
        img.classList.remove('loaded');
        img.src = d.image + '?t=' + d.mtime;
        img.style.display = 'block';
        ph.style.display  = 'none';
        bdg.style.display = 'block';
        bdg.textContent   = d.name;
        img.onload = () => { img.classList.add('loaded'); wrap.classList.add('preview-new'); setTimeout(()=>wrap.classList.remove('preview-new'), 700); };
      }
    } catch(_) {}
  }, 1000);
}

// ── Status polling ────────────────────────────────────────────────────────────
function startStatPoll() {
  if (pollStat) clearInterval(pollStat);
  pollStat = setInterval(async () => {
    if (!running) { clearInterval(pollStat); return; }
    try {
      const d = await fetch('/api/status').then(r => r.json());
      if (d.step > 0) {
        currentStep = d.step;
        setSteps(d.step);
      }
      if (!d.running && running) {
        setRunning(false);
        clearInterval(pollImg);
        clearInterval(pollStat);
        // One final image check in case last scene landed after step counter advanced.
        if (d.return_code === 0) {
          setAllDone();
          document.getElementById('dot').className = 'dot done';
          document.getElementById('status-text').textContent = 'Complete';
          checkLatestImage();
          checkVideo();
        } else if (d.step_label === 'stopped') {
          document.getElementById('dot').className = 'dot stopped';
          document.getElementById('status-text').textContent = 'Stopped';
        } else {
          document.getElementById('dot').className = 'dot error';
          document.getElementById('status-text').textContent = 'Error';
        }
      }
    } catch(_) {}
  }, 1000);
}

async function checkLatestImage() {
  try {
    const d = await fetch('/api/image/latest').then(r => r.json());
    if (d.image && d.mtime > lastMtime) {
      lastMtime = d.mtime;
      const img  = document.getElementById('preview-img');
      const ph   = document.getElementById('preview-ph');
      const bdg  = document.getElementById('preview-badge');
      img.classList.remove('loaded');
      img.src = d.image + '?t=' + d.mtime;
      img.style.display = 'block';
      ph.style.display  = 'none';
      bdg.style.display = 'block';
      bdg.textContent   = d.name;
      img.onload = () => img.classList.add('loaded');
    }
  } catch(_) {}
}

async function checkVideo() {
  const d = await fetch('/api/video').then(r => r.json());
  if (d.video) document.getElementById('video-card').style.display = 'block';
}

// ── SSE ───────────────────────────────────────────────────────────────────────
function handleStateUpdate(s) {
  // Called when the pipeline starts externally (e.g. via Agent CORE API).
  // Switches the UI to running state if it wasn't already.
  if (s.running && !running) {
    verboseMode = s.verbose !== undefined ? s.verbose : true;
    setRunning(true);
    if (s.step > 0) { currentStep = s.step; setSteps(s.step); }
    startImgPoll();
    startStatPoll();
  }
}

function connectSSE() {
  if (sse) sse.close();
  sse = new EventSource('/api/stream');
  sse.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.line !== undefined) addLine(d.line);
    if (d.running !== undefined) handleStateUpdate(d);
  };
  sse.onerror = () => {
    // auto-reconnect via browser
  };
}

// ── Actions ──────────────────────────────────────────────────────────────────
async function startPipeline() {
  const model = document.getElementById('model').value;
  if (!model || document.getElementById('model').disabled) {
    addLine('[CF ERROR] Load and select a text model first.');
    return;
  }
  const topic = document.getElementById('topic').value.trim();
  if (!resumeActive && !topic) {
    const el = document.getElementById('topic');
    el.style.borderColor = '#f85149';
    el.focus();
    setTimeout(() => el.style.borderColor = '', 2000);
    return;
  }

  // Reset log and preview
  document.getElementById('log').innerHTML = '';
  document.getElementById('preview-img').style.display  = 'none';
  document.getElementById('preview-img').classList.remove('loaded');
  document.getElementById('preview-ph').style.display   = 'block';
  document.getElementById('preview-badge').style.display = 'none';
  document.getElementById('video-card').style.display   = 'none';
  logLines = 0; lastMtime = 0;
  setSteps(0);

  verboseMode = document.getElementById('verbose').checked;
  const params = {
    model,
    topic,
    duration: +document.getElementById('dur').value,
    tts,
    voice:   document.getElementById('voice').value,
    style,
    verbose:  verboseMode,
    resume:  document.getElementById('resume').checked,
  };

  const res  = await fetch('/api/start', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(params),
  });
  const data = await res.json();
  if (data.error) { addLine('[CF ERROR] ' + data.error); return; }
  try { localStorage.setItem('cf-text-model', model); } catch {}

  setRunning(true);
  connectSSE();
  startImgPoll();
  startStatPoll();
}

async function stopPipeline() {
  await fetch('/api/stop', { method: 'POST' });
}

async function checkStatus() {
  try {
    const d = await fetch('/api/status').then(r => r.json());
    if (d.running) {
      verboseMode = d.verbose !== undefined ? d.verbose : true;
      setRunning(true);
      if (d.step > 0) { currentStep = d.step; setSteps(d.step); }
      startImgPoll();
      startStatPoll();
    } else if (d.return_code === 0) {
      setAllDone();
      document.getElementById('dot').className = 'dot done';
      document.getElementById('status-text').textContent = 'Complete';
      checkLatestImage();
      checkVideo();
    }
  } catch(_) {}
  // Always connect SSE — receives live log lines and external-start events
  // (e.g. when Agent CORE resumes the pipeline while this tab is already open).
  connectSSE();
}
</script>
</body>
</html>
"""

# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import webbrowser

    ap = argparse.ArgumentParser(description="Chronicle Forge — web UI")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    url = f"http://localhost:{a.port}"
    print(f"Chronicle Forge Web UI  →  {url}")
    print("Press Ctrl+C to stop the server.\n")

    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=a.port, debug=False, threaded=True)
