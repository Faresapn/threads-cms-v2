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
from lib import hooks  # noqa: E402

BASE = Path(__file__).resolve().parent
WEB = BASE / "web"
PORT = 8455
OAUTH_PORT = 8456           # HTTPS khusus OAuth callback
REDIRECT_URI = f"https://localhost:{OAUTH_PORT}/callback"
_lock = threading.RLock()
_last_ana_day = None   # tanggal terakhir auto-snapshot analytics jam 7 jalan


# ── soft-sell auto-reply ────────────────────────────────────────────────────
def _softsell_reply(post, results):
    """Reply soft-sell di bawah thread (BUKAN di utas). Isinya:
    - teks CTA auto-generate dari deskripsi produk (softsell_text)
    - gambar produk (kalau ada, disimpan di media part_index=-1)
    - link produk di akhir
    Skip kalau gak ada link DAN gak ada deskripsi DAN gak ada gambar."""
    link = (post.get("softsell_link") or "").strip()
    desc = (post.get("softsell_text") or "").strip()
    img = db.get_softsell_image(post["id"])
    # gak ada bahan soft-sell sama sekali = storytelling murni, skip
    if not link and not desc and not img:
        return None
    # cari root post id (post pertama di chain)
    root_id = None
    for r in (results or []):
        if r.get("post_id"):
            root_id = r["post_id"]
            break
    if not root_id:
        return {"error": "gak nemu root post id buat reply"}
    # teks reply: auto-generate dari deskripsi produk + link di akhir
    lang = (post.get("lang") or "id")
    try:
        if desc:
            reply_text = ai.softsell_reply_text(desc, link=link, lang=lang)
        else:
            reply_text = link
    except Exception as e:
        print(f"[softsell] generate teks gagal, fallback: {e}", flush=True)
        reply_text = f"{desc}\n\n{link}".strip() if desc else link
    try:
        res = threads_api.reply_to(post["handle"], root_id, reply_text, image_url=img)
        print(f"[softsell] reply ke {root_id}: {res.get('reply_id')} (img={bool(img)})", flush=True)
        return {"ok": True, **res}
    except Exception as e:
        print(f"[softsell] gagal reply: {e}", flush=True)
        return {"error": str(e)[:200]}


# ── scheduler ─────────────────────────────────────────────────────────────
def _plan_autopost(only_handle=None):
    """JAGA STOK: tiap akun enabled, pastiin ada N post 'scheduled' ke depan
    (N = posts_per_day). Kalau stok < N, generate kekurangannya aja. Begitu 1
    post kepost, tick berikut ngisi 1 lagi. Toggle OFF = skip total (gak generate
    baru; post yg udah terjadwal tetep jalan).
    Tiap post pakai tipe HOOK berbeda (dari hook library + referensi user) biar
    gak template. Bahasa ikut cfg.lang (id/en) konsisten tiap post.
    only_handle: kalau diisi, cuma proses akun itu (buat trigger langsung pas save)."""
    import random
    from lib import hooks as _hooks
    handles = [only_handle] if only_handle else db.list_enabled_autopost()
    for handle in handles:
        cfg = db.get_autopost(handle)
        if only_handle and not cfg.get("enabled"):
            continue  # dipanggil spesifik tapi akun OFF, skip
        niches = cfg.get("niches") or []
        if not niches:
            print(f"[autopost] @{handle} enabled tapi niche kosong, skip", flush=True)
            continue
        target = max(1, int(cfg.get("posts_per_day", 3)))
        have = db.count_pending_auto(handle)
        need = target - have
        if need <= 0:
            continue  # stok cukup, gak usah generate
        hours = list(cfg.get("best_hours") or db.DEFAULT_HOURS)
        persona = db.get_persona(cfg["persona_id"]) if cfg.get("persona_id") else None
        lang = cfg.get("lang", "id")
        guide = cfg.get("style_guide") or db.DEFAULT_STYLE_GUIDE
        pmin = int(cfg.get("num_parts_min", 1)); pmax = int(cfg.get("num_parts_max", 3))

        # pool hook: gabung hook dari library (10 tipe) biar tiap post beda.
        hook_cats = list(_hooks.HOOK_CATEGORIES.items())
        random.shuffle(hook_cats)

        made = 0
        for i in range(need):
            niche = random.choice(niches)
            nparts = random.randint(pmin, max(pmin, pmax))
            # pilih tipe hook beda tiap post (rotasi biar gak nabrak)
            hk_id, hk = hook_cats[(have + i) % len(hook_cats)]
            try:
                text = ai.generate_random(
                    niche, guide, lang=lang, num_parts=nparts, persona=persona,
                    hook_examples=hk.get("examples"), hook_name=hk.get("name"))
            except Exception as e:
                print(f"[autopost] @{handle} gagal generate ({niche}): {e}", flush=True)
                continue
            # jadwal anti-pola: tiap akun punya jitter sendiri (deterministik dari handle)
            # biar 50 akun gak numpuk di jam sama walau best_hours mirip.
            import hashlib
            acct_jitter = int(hashlib.md5(handle.encode()).hexdigest(), 16) % 37  # 0-36 menit offset khas akun
            now = datetime.now(db.WIB)
            from datetime import timedelta
            slot = None
            for hr in sorted(hours):
                cand = now.replace(hour=hr, minute=random.randint(0, 59),
                                   second=0, microsecond=0)
                if cand > now:
                    slot = cand
                    break
            if slot is None:  # semua jam hari ini lewat -> besok jam pertama
                hr = sorted(hours)[0]
                slot = (now + timedelta(days=1)).replace(
                    hour=hr, minute=random.randint(0, 59), second=0, microsecond=0)
            # offset khas-akun + spread acak tiap post -> jam tiap akun beda-beda
            slot = slot + timedelta(minutes=acct_jitter + random.randint(0, 25))
            db.new_post(handle, text, scheduled_at=slot.isoformat(), source="auto")
            made += 1
            print(f"[autopost] @{handle} +1 '{niche}' hook={hk.get('name')} "
                  f"lang={lang} @ {slot.strftime('%d/%m %H:%M')}", flush=True)


def scheduler_loop():
    print("[scheduler] mulai (cek tiap 30s)", flush=True)
    _tick = 0
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
                        ss = _softsell_reply(post, res)
                        if ss:
                            db.set_softsell_result(pid, ss)
                    except Exception as e:
                        db.set_result(pid, "failed", error=str(e)[:250])
                        print(f"[scheduler] FAIL {pid}: {e}", flush=True)
        except Exception as e:
            print(f"[scheduler] err: {e}", flush=True)
        # cek autopost planner tiap ~10 menit (20 tick x 30s)
        _tick += 1
        if _tick % 20 == 1:
            try:
                _plan_autopost()
            except Exception as e:
                print(f"[autopost] planner err: {e}", flush=True)
        # auto-snapshot analytics tiap hari jam 7 pagi (sekali per hari)
        try:
            global _last_ana_day
            _now = datetime.now(db.WIB)
            if _now.hour == 7 and _last_ana_day != _now.date():
                _last_ana_day = _now.date()
                print("[analytics] auto-snapshot jam 7 pagi...", flush=True)
                snap = threads_api.save_analytics_snapshot(limit=20)
                print(f"[analytics] snapshot tersimpan: {snap.get('count')} akun", flush=True)
        except Exception as e:
            print(f"[analytics] auto-snapshot err: {e}", flush=True)
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
            if path in ("/app.css", "/app.js"):
                return self._static(path.lstrip("/"))
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
            if path == "/api/analytics/all":
                return self._json(threads_api.all_accounts_analytics(
                    int(q.get("limit", ["25"])[0])))
            if path == "/api/analytics/overview":
                # baca snapshot cache (instant, gak narik API) + tren harian
                snap = threads_api.load_latest_snapshot()
                return self._json({
                    "ok": True,
                    "snapshot": snap,
                    "trend": threads_api.load_trend(14),
                    "has_data": snap is not None,
                })
            if path == "/api/analytics":
                return self._json(threads_api.account_analytics(
                    q.get("handle", [""])[0],
                    int(q.get("limit", ["25"])[0])))
            if path == "/api/hooks":
                return self._json(hooks.list_hooks())
            if path == "/api/personas":
                return self._json(db.list_personas(q.get("handle", [None])[0]))
            if path == "/api/persona":
                p = db.get_persona(int(q.get("id", ["0"])[0]))
                return self._json(p or {"error": "not found"}, 200 if p else 404)
            if path == "/api/autopost":
                return self._json(db.get_autopost(q.get("handle", [""])[0]))
            # ── OAuth (HTTP redirect, bukan JSON) ──
            if path == "/oauth/start":
                url, state = threads_api.oauth_authorize_url(REDIRECT_URI)
                if not url:
                    return self._json({"error": state}, 400)
                self.send_response(302)
                self.send_header("Location", url)
                self.end_headers()
                return
            if path == "/callback":
                return self._oauth_callback(q)
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
                                  body.get("scheduled_at"),
                                  softsell_link=body.get("softsell_link"),
                                  softsell_text=body.get("softsell_text"),
                                  source=body.get("source", "manual"))
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
            if path == "/api/instant":
                # Instant Content: pilih persona + judul + desk -> LLM auto-generate
                # (nentuin sendiri jumlah part). Opsi: langsung bikin post draft/jadwal.
                persona = db.get_persona(int(body["persona_id"])) if body.get("persona_id") else {}
                if not persona:
                    return self._json({"error": "persona wajib dipilih"}, 400)
                title = (body.get("title") or "").strip()
                if not title:
                    return self._json({"error": "judul wajib diisi"}, 400)
                text = ai.generate_instant(
                    persona, title, desc=body.get("desc", ""),
                    lang=body.get("lang") or persona.get("lang", "id"))
                # kalau cuma preview, balikin teks doang
                if body.get("preview"):
                    return self._json({"ok": True, "text": text})
                # bikin post beneran
                handle = body.get("handle")
                if not handle:
                    return self._json({"error": "akun wajib dipilih"}, 400)
                pid = db.new_post(handle, text, body.get("scheduled_at"), source="instant")
                return self._json({"ok": True, "id": pid, "text": text})
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
                                   lang=body.get("lang"),
                                   has_link=bool(body.get("has_link")),
                                   extra_brief=body.get("brief"))
                return self._json({"ok": True, "text": text})
            # ── autopost ──
            if path == "/api/autopost/save":
                db.save_autopost(
                    handle=body["handle"],
                    enabled=body.get("enabled"),
                    lang=body.get("lang"),
                    niches=body.get("niches"),
                    posts_per_day=body.get("posts_per_day"),
                    best_hours=body.get("best_hours"),
                    persona_id=body.get("persona_id"),
                    num_parts_min=body.get("num_parts_min"),
                    num_parts_max=body.get("num_parts_max"),
                    style_urls=body.get("style_urls"),
                    style_guide=body.get("style_guide"))
                cfg = db.get_autopost(body["handle"])
                # kalau ON, langsung generate di background biar response cepet
                # + hasil keliatan seketika (gak nunggu planner 10 menit)
                if cfg.get("enabled"):
                    _h = body["handle"]
                    threading.Thread(target=lambda: _plan_autopost(only_handle=_h),
                                     daemon=True).start()
                return self._json({"ok": True, "config": db.get_autopost(body["handle"])})
            if path == "/api/analytics/refresh":
                # narik fresh semua akun + simpan snapshot (manual Update / cron)
                snap = threads_api.save_analytics_snapshot(
                    limit=int(body.get("limit", 20)))
                return self._json({"ok": True, "snapshot": snap,
                                   "trend": threads_api.load_trend(14)})
            if path == "/api/autopost/toggle":
                cfg = db.get_autopost(body["handle"])
                new_state = 0 if cfg["enabled"] else 1
                db.save_autopost(body["handle"], enabled=new_state)
                # baru di-ON kan: langsung generate di background biar keliatan seketika
                if new_state:
                    _h = body["handle"]
                    threading.Thread(target=lambda: _plan_autopost(only_handle=_h),
                                     daemon=True).start()
                return self._json({"ok": True, "enabled": new_state})
            if path == "/api/autopost/generate_now":
                # generate 1 preview utas (gak dijadwal, buat dicek)
                cfg = db.get_autopost(body["handle"])
                niches = body.get("niches") or cfg.get("niches") or []
                if not niches:
                    return self._json({"error": "niche kosong"}, 400)
                import random as _r
                niche = body.get("niche") or _r.choice(niches)
                persona = db.get_persona(cfg["persona_id"]) if cfg.get("persona_id") else None
                text = ai.generate_random(
                    niche, cfg.get("style_guide"),
                    lang=body.get("lang") or cfg.get("lang", "id"),
                    num_parts=int(body.get("num_parts", 2)), persona=persona)
                return self._json({"ok": True, "niche": niche, "text": text})
            if path == "/api/hooks/generate":
                prompt = hooks.hook_prompt(
                    body.get("category", ""), body.get("topic", ""),
                    lang=body.get("lang", "id"))
                if not prompt:
                    return self._json({"error": "kategori gak valid"}, 400)
                out = ai._chat([{"role": "user", "content": prompt}], max_tokens=600)
                out = out.replace("—", ", ")
                return self._json({"ok": True, "text": out.strip()})
            # ── akun ──
            if path == "/api/account/add":
                res = threads_api.add_account(
                    body.get("token", ""),
                    exchange=bool(body.get("exchange", True)))
                if res.get("ok"):
                    db.upsert_account(res["handle"], display_name=res["handle"],
                                      user_id=res.get("user_id"))
                return self._json(res, 200 if res.get("ok") else 400)
            if path == "/api/account/delete":
                res = threads_api.remove_account(body.get("handle", ""))
                return self._json(res, 200 if res.get("ok") else 400)
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
                ss = _softsell_reply(post, res)
                if ss:
                    db.set_softsell_result(pid, ss)
                return self._json({"ok": True, "results": res, "softsell": ss})
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

    def _oauth_callback(self, q):
        """Handle redirect balik dari Meta: tuker code -> token -> simpan."""
        def _page(icon, msg, detail=""):
            html = f"""<!doctype html><html><head><meta charset=utf-8>
<title>Threads CMS</title><style>
body{{font-family:-apple-system,sans-serif;background:#0a0a0b;color:#e8e8ea;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.box{{text-align:center;max-width:420px;padding:30px}}
.icon{{font-size:52px;margin-bottom:14px}}
h1{{font-size:20px;margin:0 0 8px}}p{{color:#8a8a93;font-size:14px}}
a{{color:#5b8cff}}</style></head><body><div class=box>
<div class=icon>{icon}</div><h1>{msg}</h1><p>{detail}</p>
<p><a href="http://localhost:8455/">← balik ke dashboard</a></p>
<script>setTimeout(()=>{{window.close()}},2500)</script>
</div></body></html>"""
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        if "error" in q:
            return _page("❌", "Ditolak",
                         q.get("error_description", q.get("error", ["?"]))[0])
        code = (q.get("code") or [""])[0].split("#_")[0].strip()
        if not code:
            return _page("⚠️", "Gak ada code di callback")
        res = threads_api.oauth_exchange_code(code, REDIRECT_URI)
        if res.get("ok"):
            db.upsert_account(res["handle"], display_name=res["handle"],
                              user_id=res.get("user_id"))
            return _page("✅", f"@{res['handle']} terhubung!",
                         "Token long-lived tersimpan. Tab ini bakal nutup sendiri.")
        return _page("❌", "Gagal connect", res.get("error", "?")[:200])

    def _static(self, name):
        f = WEB / name
        if not f.exists():
            return self._json({"error": "no ui"}, 404)
        ext = f.suffix.lower()
        ctype = {".html": "text/html; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8"}.get(ext, "application/octet-stream")
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _start_oauth_https():
    """Listener HTTPS terpisah buat OAuth callback (Meta wajib HTTPS).
    Reuse handler H yang sama; cuma beda port + TLS."""
    import ssl
    cert = BASE / "tls-cert.pem"
    key = BASE / "tls-key.pem"
    if not (cert.exists() and key.exists()):
        print("[oauth] cert TLS gak ada, OAuth HTTPS nonaktif", flush=True)
        return
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
        httpsd = ThreadingHTTPServer(("127.0.0.1", OAUTH_PORT), H)
        httpsd.socket = ctx.wrap_socket(httpsd.socket, server_side=True)
        print(f"[oauth] https://localhost:{OAUTH_PORT} (callback)", flush=True)
        httpsd.serve_forever()
    except Exception as e:
        print(f"[oauth] gagal start HTTPS: {e}", flush=True)


def main():
    db.init_db()
    threading.Thread(target=scheduler_loop, daemon=True).start()
    threading.Thread(target=_start_oauth_https, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"[cms] http://127.0.0.1:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
