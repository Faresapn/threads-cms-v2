#!/usr/bin/env python3
"""server.py — Threads CMS v2 backend.
HTTP JSON API + scheduler + static dashboard.

Endpoints:
  GET  /                       → dashboard
  GET  /api/accounts           → list akun
  GET  /api/posts?status&handle→ list post
  GET  /api/post?id            → detail 1 post
  POST /api/post               → {handle, text, scheduled_at?}  bikin post
  POST /api/post/update        → {id, text?, scheduled_at?, unset_time?, status?}
  POST /api/post/delete        → {id}
  POST /api/post/publish       → {id}  post sekarang (manual)
  POST /api/upload             → multipart file → {r2_key, public_url}  (masuk library)
  POST /api/post/attach        → {id, part_index, public_url}  pasang image ke part
  POST /api/post/detach        → {id}  hapus semua media post
  GET  /api/library            → list media library
  GET  /api/limit?handle       → publishing limit
"""
import json, sys, threading, time, cgi, io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import db, r2, threads_api, ai  # noqa: E402

BASE = Path(__file__).resolve().parent
WEB = BASE / "web"
PORT = 8455
_lock = threading.RLock()


# ── scheduler ─────────────────────────────────────────────────────────────
def scheduler_loop():
    print("[scheduler] mulai (cek tiap 30s)", flush=True)
    while True:
        try:
            with _lock:
                for post in db.due_posts():
                    pid = post["id"]
                    db.update_post(pid, status="posting")
                    parts = threads_api.parse_parts(post["text"])
                    urls = db.get_media_urls(pid, len(parts))
                    print(f"[scheduler] post {pid} @{post['handle']}...", flush=True)
                    try:
                        res = threads_api.post_thread(post["handle"], post["text"], urls)
                        db.set_result(pid, "posted", results=res,
                                      posted_at=db.now_iso())
                        print(f"[scheduler] OK {pid}", flush=True)
                    except Exception as e:
                        db.set_result(pid, "failed", error=str(e)[:250])
                        print(f"[scheduler] FAIL {pid}: {e}", flush=True)
        except Exception as e:
            print(f"[scheduler] err: {e}", flush=True)
        time.sleep(30)


# ── HTTP handler ──────────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path
        try:
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path == "/api/accounts":
                return self._json(db.list_accounts())
            if path == "/api/posts":
                return self._json(db.list_posts(
                    status=q.get("status", [None])[0],
                    handle=q.get("handle", [None])[0]))
            if path == "/api/post":
                p = db.get_post(q.get("id", [""])[0])
                return self._json(p or {"error": "not found"}, 200 if p else 404)
            if path == "/api/library":
                return self._json(db.list_library())
            if path == "/api/limit":
                return self._json(threads_api.publishing_limit(q.get("handle", [""])[0]))
            if path == "/api/live_posts":
                return self._json(threads_api.list_live_posts(
                    q.get("handle", [""])[0],
                    int(q.get("limit", ["25"])[0])))
            if path == "/api/insight":
                return self._json(threads_api.post_insight(
                    q.get("handle", [""])[0], q.get("post_id", [""])[0]))
            if path == "/api/personas":
                return self._json(db.list_personas(q.get("handle", [None])[0]))
            if path == "/api/persona":
                p = db.get_persona(int(q.get("id", ["0"])[0]))
                return self._json(p or {"error": "not found"}, 200 if p else 404)
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        try:
            if path == "/api/upload":
                return self._upload()
            body = self._body()
            if path == "/api/post":
                pid = db.new_post(body["handle"], body["text"],
                                  body.get("scheduled_at"))
                return self._json({"id": pid, "ok": True})
            if path == "/api/post/update":
                pid = body["id"]
                fields = {}
                if "text" in body:
                    fields["text"] = body["text"]
                if body.get("unset_time"):
                    fields["scheduled_at"] = None
                    fields["status"] = "draft"
                elif body.get("scheduled_at"):
                    dt = datetime.fromisoformat(body["scheduled_at"])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=db.WIB)
                    fields["scheduled_at"] = dt.isoformat()
                    fields["status"] = "scheduled"
                if body.get("status"):
                    fields["status"] = body["status"]
                db.update_post(pid, **fields)
                return self._json({"ok": True})
            if path == "/api/post/delete":
                db.delete_post(body["id"])
                return self._json({"ok": True})
            if path == "/api/post/attach":
                db.add_media(body["id"], int(body.get("part_index", 0)),
                             body.get("r2_key", ""), body["public_url"],
                             body.get("filename"), body.get("size"))
                return self._json({"ok": True})
            if path == "/api/post/detach":
                db.clear_media(body["id"])
                return self._json({"ok": True})
            if path == "/api/post/publish":
                return self._publish_now(body["id"])
            if path == "/api/refresh":
                return self._json(threads_api.refresh_token(body.get("handle", "")))
            # ── personas ──
            if path == "/api/persona/save":
                pid = db.save_persona(
                    handle=body["handle"], name=body["name"],
                    description=body.get("description"),
                    system_prompt=body.get("system_prompt"),
                    lang=body.get("lang", "id"),
                    reference_urls=body.get("reference_urls", []),
                    sample_posts=body.get("sample_posts", []),
                    is_default=1 if body.get("is_default") else 0,
                    pid=body.get("id"))
                return self._json({"ok": True, "id": pid})
            if path == "/api/persona/delete":
                db.delete_persona(int(body["id"]))
                return self._json({"ok": True})
            if path == "/api/persona/learn":
                # fetch link → analisis gaya → simpan ke persona
                pid = int(body["id"])
                persona = db.get_persona(pid)
                if not persona:
                    return self._json({"error": "persona not found"}, 404)
                urls = body.get("reference_urls") or persona.get("reference_urls", [])
                texts = ai.fetch_thread_texts(urls, handle=persona["handle"])
                if not texts:
                    return self._json({"error": "gak ada teks kebaca dari link/akun"}, 400)
                style = ai.learn_style(texts, lang=persona.get("lang", "id"))
                db.update_persona_style(pid, style)
                return self._json({"ok": True, "learned_style": style,
                                   "samples_found": len(texts)})
            if path == "/api/generate":
                persona = {}
                if body.get("persona_id"):
                    persona = db.get_persona(int(body["persona_id"])) or {}
                else:
                    persona = {
                        "system_prompt": body.get("system_prompt", ""),
                        "learned_style": body.get("learned_style", ""),
                        "sample_posts": body.get("sample_posts", []),
                        "lang": body.get("lang", "id"),
                    }
                text = ai.generate(body["topic"], persona,
                                   num_parts=int(body.get("num_parts", 1)),
                                   lang=body.get("lang"))
                return self._json({"ok": True, "text": text})
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _publish_now(self, pid):
        post = db.get_post(pid)
        if not post:
            return self._json({"error": "not found"}, 404)
        with _lock:
            db.update_post(pid, status="posting")
            parts = threads_api.parse_parts(post["text"])
            urls = db.get_media_urls(pid, len(parts))
            try:
                res = threads_api.post_thread(post["handle"], post["text"], urls)
                db.set_result(pid, "posted", results=res, posted_at=db.now_iso())
                return self._json({"ok": True, "results": res})
            except Exception as e:
                db.set_result(pid, "failed", error=str(e)[:250])
                return self._json({"error": str(e)}, 500)

    def _upload(self):
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            return self._json({"error": "need multipart"}, 400)
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        env = {"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype,
               "CONTENT_LENGTH": str(n)}
        fs = cgi.FieldStorage(fp=io.BytesIO(raw), environ=env,
                              keep_blank_values=True)
        if "file" not in fs:
            return self._json({"error": "no file field"}, 400)
        item = fs["file"]
        data = item.file.read()
        fname = item.filename or "upload.bin"
        key, url = r2.upload_bytes(data, fname,
                                   content_type=item.type or None)
        db.add_library(key, url, fname, len(data))
        return self._json({"ok": True, "r2_key": key, "public_url": url,
                           "filename": fname, "size": len(data)})

    def _static(self, name):
        f = WEB / name
        if not f.exists():
            return self._json({"error": "no ui"}, 404)
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    db.init_db()
    threading.Thread(target=scheduler_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"[cms] http://127.0.0.1:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
