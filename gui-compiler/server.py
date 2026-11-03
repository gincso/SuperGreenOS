#!/usr/bin/env python3
"""SuperGreenOS GUI compiler - stdlib only, no pip deps.
Runs on the VPS, serves the settings editor, and runs the ESP-IDF
docker build for the chosen profile. Token auth: the token is read
from token.txt next to this file (600 perms). It is never logged.
"""
import json, os, re, shutil, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("SGL_REPO", os.path.abspath(os.path.join(BASE, "..")))
OUT = os.path.join(BASE, "builds")
os.makedirs(OUT, exist_ok=True)

PROFILES = {
    "driver": "config.driver.json",
    "controller": "config.controller.json",
    "pickle": "config.pickle.json",
    "solo": "config.solo.json",
    "screen": "config.screen.json",
    "tips": "config.tips.json",
}

def token():
    p = os.path.join(BASE, "token.txt")
    if not os.path.exists(p):
        import secrets
        with open(p, "w") as f:
            f.write(secrets.token_urlsafe(24))
        os.chmod(p, 0o600)
    with open(p) as f:
        return f.read().strip()

TOKEN = token()
state = {"running": False, "last_exit": None, "last_profile": None,
         "last_started": None, "last_finished": None, "log": ""}
lock = threading.Lock()

BUILD_SCRIPT = r'''#!/bin/bash
set -x
cd REPO_DIR
docker run --rm -v REPO_DIR:/project -w /project espressif/idf:v3.3.6 bash -c "
set -e
NODE_VERSION=v16.20.2
curl -fsSL -o /tmp/node.tar.xz https://nodejs.org/dist/\$NODE_VERSION/node-\$NODE_VERSION-linux-x64.tar.xz
tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
npm install -g ejs-cli
./update_templates.sh CONFIGFILE
. \$IDF_PATH/export.sh
make defconfig
make -j4
echo BUILD_EXIT:0
ls -lh build/firmware.bin build/bootloader/bootloader.bin build/partitions.bin build/ota_data_initial.bin
"
'''

def run_build(profile):
    cfg = PROFILES[profile]
    script = BUILD_SCRIPT.replace("CONFIGFILE", cfg).replace("REPO_DIR", REPO)
    script_path = os.path.join(BASE, "run-build.sh")
    with open(script_path, "w") as f:
        f.write(script)
    os.chmod(script_path, 0o755)
    with lock:
        state["running"] = True
        state["last_profile"] = profile
        state["last_started"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state["log"] = ""
    proc = subprocess.Popen([script_path], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        with lock:
            state["log"] += line
            state["log"] = state["log"][-200000:]
    proc.wait()
    with lock:
        state["running"] = False
        state["last_exit"] = proc.returncode
        state["last_finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if proc.returncode == 0:
        ts = time.strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(OUT, f"{profile}-{ts}")
        os.makedirs(dest, exist_ok=True)
        for name in ["firmware.bin", "bootloader.bin", "partitions.bin", "ota_data_initial.bin"]:
            src = os.path.join(REPO, "build", name)
            if name == "bootloader.bin":
                src = os.path.join(REPO, "build", "bootloader", "bootloader.bin")
            if os.path.exists(src):
                shutil.copy(src, os.path.join(dest, name))
        with lock:
            state["last_build_dir"] = dest

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def _auth(self, qs=None):
        hdr = self.headers.get("X-SGL-Token", "")
        q = (qs or {}).get("token", [""])[0]
        return hdr == TOKEN or q == TOKEN
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj))
    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == "/":
            with open(os.path.join(BASE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html")
            return
        if not self._auth(qs):
            self._json({"error": "token required"}, 401)
            return
        if u.path == "/api/profiles":
            self._json({"profiles": list(PROFILES.keys())})
        elif u.path == "/api/config":
            prof = qs.get("profile", ["driver"])[0]
            fn = PROFILES.get(prof)
            if not fn:
                self._json({"error": "bad profile"}, 400); return
            with open(os.path.join(REPO, fn)) as f:
                self._json(json.load(f))
        elif u.path == "/api/status":
            with lock:
                s = dict(state)
                s["log_tail"] = s["log"][-8000:]
                del s["log"]
            # list builds
            builds = []
            if os.path.isdir(OUT):
                for d in sorted(os.listdir(OUT), reverse=True)[:20]:
                    p = os.path.join(OUT, d)
                    files = os.listdir(p) if os.path.isdir(p) else []
                    builds.append({"dir": d, "files": files})
            s["builds"] = builds
            self._json(s)
        elif u.path == "/api/download":
            name = qs.get("file", [""])[0]
            bdir = qs.get("build", [""])[0]
            if not re.match(r"^[A-Za-z0-9._-]+$", name) or not re.match(r"^[A-Za-z0-9._-]+$", bdir):
                self._json({"error": "bad name"}, 400); return
            path = os.path.join(OUT, bdir, name)
            if not os.path.isfile(path):
                self._json({"error": "not found"}, 404); return
            with open(path, "rb") as f:
                self._send(200, f.read(), "application/octet-stream")
        else:
            self._json({"error": "not found"}, 404)
    def do_POST(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if not self._auth(qs):
            self._json({"error": "token required"}, 401); return
        if u.path == "/api/config":
            try:
                data = json.loads(body.decode())
                prof = qs.get("profile", ["driver"])[0]
                fn = PROFILES.get(prof)
                if not fn:
                    self._json({"error": "bad profile"}, 400); return
                # validate: must look like a SuperGreenOS config
                if "modules" not in data:
                    self._json({"error": "config must contain modules"}, 400); return
                path = os.path.join(REPO, fn)
                with open(path + ".bak", "w") as f:
                    json.dump(json.load(open(path)), f)
                with open(path, "w") as f:
                    json.dump(data, f, indent=2)
                self._json({"ok": True, "profile": prof})
            except Exception as e:
                self._json({"error": str(e)}, 400)
        elif u.path == "/api/compile":
            prof = qs.get("profile", ["driver"])[0]
            if prof not in PROFILES:
                self._json({"error": "bad profile"}, 400); return
            with lock:
                if state["running"]:
                    self._json({"error": "build already running"}, 409); return
            threading.Thread(target=run_build, args=(prof,), daemon=True).start()
            self._json({"ok": True, "profile": prof})
        else:
            self._json({"error": "not found"}, 404)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8002
    print(f"SGL compiler on :{port}, repo {REPO}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
