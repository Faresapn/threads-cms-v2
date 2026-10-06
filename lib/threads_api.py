#!/usr/bin/env python3
"""threads_api.py — wrapper Threads Graph API buat CMS v2.
Reuse tokens.json dari bot lama (~/.threads-bot/tokens.json) biar akun yg udah
OAuth langsung kepakai. Support post chain + image (via URL publik R2).
"""
import json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from datetime import date, datetime

GRAPH = "https://graph.threads.net"
# Reuse token store bot lama biar gak perlu OAuth ulang.
TOKENS = Path.home() / ".threads-bot" / "tokens.json"
_cache = {}

# ── snapshot analytics (pola x-dashboard: simpan harian, baca cache) ─────────
_ANALYTICS_DIR = Path(__file__).resolve().parent.parent / "data" / "analytics"
_SNAP_DIR = _ANALYTICS_DIR / "snapshots"


def save_analytics_snapshot(limit=20):
    """Narik all_accounts_analytics (live, lama) lalu simpan snapshot harian.
    Return snapshot yg disimpan. Dipanggil manual (tombol Update) / cron jam 7."""
    _SNAP_DIR.mkdir(parents=True, exist_ok=True)
    data = all_accounts_analytics(limit=limit)
    today = date.today().isoformat()
    snap = {"date": today, "collected_at": datetime.now().isoformat(),
            "accounts": data.get("accounts", []), "count": data.get("count", 0)}
    (_SNAP_DIR / f"{today}.json").write_text(
        json.dumps(snap, indent=2, ensure_ascii=False))
    (_ANALYTICS_DIR / "latest.json").write_text(
        json.dumps({"date": today}, indent=2))
    return snap


def load_latest_snapshot():
    """Baca snapshot terakhir (instant, gak narik API). None kalau belum ada."""
    latest = _ANALYTICS_DIR / "latest.json"
    if not latest.exists():
        # fallback: cari file snapshot terbaru
        if _SNAP_DIR.exists():
            files = sorted(_SNAP_DIR.glob("*.json"), reverse=True)
            if files:
                return json.loads(files[0].read_text())
        return None
    d = json.loads(latest.read_text())
    p = _SNAP_DIR / f"{d['date']}.json"
    return json.loads(p.read_text()) if p.exists() else None


def load_trend(days=14):
    """Tren harian: total views + engagement per tanggal dari semua snapshot.
    Buat line chart. Return list {date, total_views, total_eng, per_handle}."""
    if not _SNAP_DIR.exists():
        return []
    out = []
    files = sorted(_SNAP_DIR.glob("*.json"))[-days:]
    for f in files:
        try:
            snap = json.loads(f.read_text())
        except Exception:
            continue
        accs = snap.get("accounts", [])
        tv = sum(a.get("views", 0) for a in accs)
        te = sum(a.get("engagement_total", 0) for a in accs)
        per = {a.get("handle"): a.get("views", 0) for a in accs}
        out.append({"date": snap.get("date"), "total_views": tv,
                    "total_eng": te, "per_handle": per})
    return out


def _tokens():
    if not TOKENS.exists():
        return {}
    return json.loads(TOKENS.read_text())


def _http(url, data=None, method=None):
    req = urllib.request.Request(url, data=data, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def account_info(handle, force=False):
    if not force and handle in _cache:
        return _cache[handle]
    tok = _tokens().get(handle)
    if not tok:
        return {"error": f"token @{handle} gak ada"}
    url = (f"{GRAPH}/v1.0/me?fields=id,username,threads_profile_picture_url"
           f"&access_token={urllib.parse.quote(tok)}")
    try:
        info = _http(url)
        _cache[handle] = info
        return info
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:200]}


def parse_parts(text):
    """Pisah post jadi chain part pakai delimiter '---' di baris sendiri.
    Tiap part yg >500 char (limit Threads) di-split otomatis jadi beberapa post,
    dipotong di batas paragraf/kalimat biar rapi."""
    raw, buf = [], []
    for line in (text or "").split("\n"):
        if line.strip() == "---":
            if buf:
                raw.append("\n".join(buf).strip()); buf = []
        else:
            buf.append(line)
    if buf:
        raw.append("\n".join(buf).strip())
    raw = [p for p in raw if p]
    # auto-split part yg kepanjangan
    out = []
    for part in raw:
        out.extend(_split_long(part, 490))
    return out


def _split_long(text, limit=490):
    """Split teks >limit char jadi beberapa chunk, potong di paragraf/kalimat."""
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    # coba potong per paragraf dulu
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) > limit:
            # paragraf sendiri kepanjangan, potong per kalimat
            import re as _re
            sentences = _re.split(r'(?<=[.!?])\s+', para)
            for s in sentences:
                if len(cur) + len(s) + 1 <= limit:
                    cur = (cur + " " + s).strip()
                else:
                    if cur:
                        chunks.append(cur)
                    cur = s if len(s) <= limit else s[:limit]
        else:
            if len(cur) + len(para) + 2 <= limit:
                cur = (cur + "\n\n" + para).strip()
            else:
                if cur:
                    chunks.append(cur)
                cur = para
    if cur:
        chunks.append(cur)
    return chunks


def post_thread(handle, text, images=None):
    """Post 1+ part ke Threads (chain reply). images[i]=URL publik utk part ke-i."""
    tok = _tokens().get(handle)
    if not tok:
        raise RuntimeError(f"token @{handle} gak ada")
    info = account_info(handle, force=True)
    uid = info.get("id")
    if not uid:
        raise RuntimeError(f"gak dapet user id: {info.get('error', '?')}")
    parts = parse_parts(text)
    if not parts:
        raise RuntimeError("teks kosong")
    images = images or []
    results, prev_id = [], None
    for i, part in enumerate(parts):
        img = images[i] if i < len(images) and images[i] else None
        p = {"text": part, "access_token": tok}
        if img:
            p["media_type"] = "IMAGE"; p["image_url"] = img
        else:
            p["media_type"] = "TEXT"
        if prev_id:
            p["reply_to_id"] = prev_id
        body = urllib.parse.urlencode(p).encode()
        cont = _http(f"{GRAPH}/v1.0/{uid}/threads", data=body, method="POST")
        cid = cont.get("id")
        if not cid:
            raise RuntimeError(f"container gagal: {str(cont)[:150]}")
        time.sleep(5 if img else 2)  # image butuh proses lebih lama
        pub_body = urllib.parse.urlencode({"creation_id": cid, "access_token": tok}).encode()
        pub = _http(f"{GRAPH}/v1.0/{uid}/threads_publish", data=pub_body, method="POST")
        pid = pub.get("id")
        results.append({"part": part[:80], "post_id": pid, "has_image": bool(img)})
        prev_id = pid or cid
    _cache.pop(handle, None)
    return results


def reply_to(handle, root_post_id, text, image_url=None):
    """Reply ke post sendiri. Bisa teks (link soft-sell) + opsional 1 gambar produk."""
    tok = _tokens().get(handle)
    if not tok:
        raise RuntimeError(f"token @{handle} gak ada")
    info = account_info(handle, force=True)
    uid = info.get("id")
    if not uid:
        raise RuntimeError(f"gak dapet user id: {info.get('error', '?')}")
    p = {"text": text, "reply_to_id": root_post_id, "access_token": tok}
    if image_url:
        p["media_type"] = "IMAGE"
        p["image_url"] = image_url
    else:
        p["media_type"] = "TEXT"
    body = urllib.parse.urlencode(p).encode()
    cont = _http(f"{GRAPH}/v1.0/{uid}/threads", data=body, method="POST")
    cid = cont.get("id")
    if not cid:
        raise RuntimeError(f"container reply gagal: {str(cont)[:150]}")
    time.sleep(3 if image_url else 2)
    pub_body = urllib.parse.urlencode({"creation_id": cid, "access_token": tok}).encode()
    pub = _http(f"{GRAPH}/v1.0/{uid}/threads_publish", data=pub_body, method="POST")
    return {"reply_id": pub.get("id"), "text": text[:80], "has_image": bool(image_url)}


def publishing_limit(handle):
    tok = _tokens().get(handle)
    uid = account_info(handle, force=True).get("id")
    if not (tok and uid):
        return {"error": "no token/uid"}
    url = (f"{GRAPH}/v1.0/{uid}/threads_publishing_limit?fields=quota_usage,config"
           f"&access_token={urllib.parse.quote(tok)}")
    return _http(url)


def list_live_posts(handle, limit=25):
    """Daftar post terkirim dari Threads API (bukan queue lokal).
    Retry 2x kalo kena 500 (Threads API kadang hiccup random)."""
    tok = _tokens().get(handle)
    if not tok:
        raise RuntimeError(f"token @{handle} gak ada")
    uid = account_info(handle, force=True).get("id")
    if not uid:
        raise RuntimeError("gak dapet user id")
    url = (f"{GRAPH}/v1.0/{uid}/threads?fields=id,media_type,text,permalink,"
           f"timestamp,is_reply&limit={limit}&access_token={urllib.parse.quote(tok)}")
    last_err = None
    for attempt in range(3):
        try:
            r = _http(url)
            break
        except urllib.error.HTTPError as e:
            last_err = e
            if (e.code >= 500 or e.code == 429 or e.code == 403) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    else:
        if last_err:
            raise last_err
        raise RuntimeError("gagal fetch post tanpa error jelas")
    out = []
    for p in r.get("data", []):
        out.append({
            "id": p.get("id"),
            "media_type": p.get("media_type"),
            "text": (p.get("text") or "")[:220],
            "permalink": p.get("permalink"),
            "timestamp": p.get("timestamp"),
            "is_reply": p.get("is_reply", False),
        })
    return out


def post_insight(handle, post_id):
    """Metrik 1 post: views, likes, replies, reposts, quotes.
    Retry kalo kena rate-limit (429/403/500) — Threads batesin call insight."""
    tok = _tokens().get(handle)
    if not tok:
        raise RuntimeError(f"token @{handle} gak ada")
    metrics = "views,likes,replies,reposts,quotes"
    url = (f"{GRAPH}/v1.0/{post_id}/insights?metric={metrics}"
           f"&access_token={urllib.parse.quote(tok)}")
    for attempt in range(3):
        try:
            r = _http(url)
            break
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
            # 429=rate limit, 403 sering juga rate-limit/transient, 5xx=server hiccup
            retryable = e.code in (429, 500, 502, 503) or \
                (e.code == 403 and ("limit" in body.lower() or "rate" in body.lower() or "reduce" in body.lower()))
            if retryable and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return {"error": body or f"HTTP {e.code}"}
    else:
        return {"error": "rate-limit, gagal setelah 3x coba"}
    out = {}
    for m in r.get("data", []):
        name = m.get("name")
        vals = m.get("values", [{}])
        out[name] = vals[0].get("value", 0) if vals else 0
    return out


def account_analytics(handle, limit=25):
    """Agregat performa akun pake USER-LEVEL insight (threads_insights).
    Bener semua waktu, 1 call per metric, no cap 25 post.
    Views: sum values harian window 90 hari (API max per request), paginate manual.
    Likes/replies/reposts/quotes: total_value window ~2 tahun.
    Top post: tetap pake list_live_posts + post_insight (buat ranking top saja).
    """
    import time as _time
    tok = _tokens().get(handle)
    if not tok:
        return {"error": f"token @{handle} gak ada"}
    try:
        uid = account_info(handle, force=False).get("id")
        if not uid:
            raise RuntimeError("gak dapet user id")
    except Exception as e:
        return {"error": f"user id @{handle}: {str(e)[:150]}"}

    now = int(_time.time())
    # ── VIEWS: sum per-day values, chunked 90d sampai 2 tahun ke belakang ──
    total_views = 0
    for i in range(8):  # 8 x 90 = 720 hari (~2 tahun)
        chunk_until = now - i * 90 * 86400
        chunk_since = chunk_until - 90 * 86400
        url = (f"{GRAPH}/v1.0/{uid}/threads_insights?metric=views"
               f"&since={chunk_since}&until={chunk_until}"
               f"&access_token={urllib.parse.quote(tok)}")
        try:
            r = _http(url)
            vals = r.get("data", [{}])[0].get("values", [])
            s = sum(int(v.get("value", 0) or 0) for v in vals)
            total_views += s
            # stop awal kalau 0 (akun belum ada aktifitas sejauh itu)
            if s == 0 and i > 0:
                break
        except Exception:
            break

    # ── likes/replies/reposts/quotes: total_value, window 2 tahun ──
    totals = {"views": total_views, "likes": 0, "replies": 0, "reposts": 0, "quotes": 0}
    since2y = now - 720 * 86400
    for m in ("likes", "replies", "reposts", "quotes"):
        url = (f"{GRAPH}/v1.0/{uid}/threads_insights?metric={m}"
               f"&since={since2y}&until={now}"
               f"&access_token={urllib.parse.quote(tok)}")
        try:
            r = _http(url)
            d = r.get("data", [{}])[0]
            totals[m] = int(d.get("total_value", {}).get("value", 0) or 0)
        except Exception:
            pass

    # ── top posts: masih per-post insight, limit kecil (buat ranking saja) ──
    detailed = []
    try:
        posts = list_live_posts(handle, limit=limit)
        for i, p in enumerate(posts):
            pid = p.get("id")
            if not pid or p.get("is_reply"):
                continue
            if i:
                _time.sleep(0.25)
            ins = post_insight(handle, pid)
            if isinstance(ins, dict) and not ins.get("error"):
                detailed.append({
                    "id": pid, "text": p.get("text", "")[:100],
                    "permalink": p.get("permalink"), "timestamp": p.get("timestamp"),
                    "views": int(ins.get("views", 0) or 0),
                    "likes": int(ins.get("likes", 0) or 0),
                    "replies": int(ins.get("replies", 0) or 0),
                    "reposts": int(ins.get("reposts", 0) or 0),
                    "quotes": int(ins.get("quotes", 0) or 0),
                })
    except Exception:
        pass

    n_posts = len(detailed)
    views = totals["views"]
    eng = totals["likes"] + totals["replies"] + totals["reposts"] + totals["quotes"]
    eng_rate = round(eng / views * 100, 2) if views else 0
    top = sorted(detailed, key=lambda x: x["views"], reverse=True)[:5]
    return {
        "ok": True, "handle": handle, "posts_analyzed": n_posts,
        "totals": totals, "engagement_total": eng, "engagement_rate": eng_rate,
        "avg_views": round(views / n_posts) if n_posts else 0,
        "top_posts": top, "all_posts": detailed,
    }


def all_accounts_analytics(limit=25):
    """Banding performa semua akun. Loop tiap akun, ringkas metrik utama,
    urutin dari views terbanyak. Akun yg error ditandai, gak bikin gagal total."""
    rows = []
    for handle in _tokens().keys():
        a = account_analytics(handle, limit=limit)
        if a.get("error"):
            rows.append({"handle": handle, "error": a["error"][:120],
                         "views": 0, "likes": 0, "replies": 0, "reposts": 0,
                         "engagement_total": 0, "engagement_rate": 0,
                         "avg_views": 0, "posts_analyzed": 0})
            continue
        t = a["totals"]
        rows.append({
            "handle": handle,
            "views": t["views"], "likes": t["likes"],
            "replies": t["replies"], "reposts": t["reposts"],
            "quotes": t.get("quotes", 0),
            "engagement_total": a["engagement_total"],
            "engagement_rate": a["engagement_rate"],
            "avg_views": a["avg_views"],
            "posts_analyzed": a["posts_analyzed"],
        })
    ranked = sorted(rows, key=lambda r: r["views"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    return {"ok": True, "accounts": ranked, "count": len(ranked)}


def refresh_token(handle):
    """Refresh long-lived token (extend 60 hari)."""
    tok = _tokens().get(handle)
    if not tok:
        return {"error": "akun gak ketemu"}
    url = (f"{GRAPH}/refresh_access_token?grant_type=th_refresh_token"
           f"&access_token={urllib.parse.quote(tok)}")
    try:
        res = _http(url)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:150]}"}
    if "access_token" in res:
        d = _tokens()
        d[handle] = res["access_token"]
        TOKENS.write_text(json.dumps(d, indent=2))
        TOKENS.chmod(0o600)
        _cache.pop(handle, None)
        return {"ok": True, "expires_in": res.get("expires_in")}
    return {"error": str(res)[:150]}


def _save_token(handle, token):
    d = _tokens()
    d[handle] = token
    TOKENS.parent.mkdir(parents=True, exist_ok=True)
    TOKENS.write_text(json.dumps(d, indent=2))
    TOKENS.chmod(0o600)
    _cache.pop(handle, None)


def _app_secret():
    """Baca app_secret dari app.json bot lama (buat exchange long-lived)."""
    appf = TOKENS.parent / "app.json"
    if appf.exists():
        try:
            d = json.loads(appf.read_text())
            s = d.get("app_secret", "")
            if s and not str(s).startswith("ISI_"):
                return s
        except Exception:
            pass
    return None


def exchange_long_lived(token):
    """Tuker short-lived token jadi long-lived (60 hari). Butuh app_secret."""
    secret = _app_secret()
    if not secret:
        return {"error": "app_secret gak ada di app.json, gak bisa exchange"}
    url = (f"{GRAPH}/access_token?grant_type=th_exchange_token"
           f"&client_secret={urllib.parse.quote(secret)}"
           f"&access_token={urllib.parse.quote(token)}")
    try:
        return _http(url)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}


def add_account(token, exchange=True):
    """Validasi token ke Meta, ambil username, (opsional exchange long-lived),
    simpan ke tokens.json. Return {ok, handle, username, ...} atau {error}."""
    token = (token or "").strip()
    if not token:
        return {"error": "token kosong"}
    # exchange dulu kalau diminta (token pendek -> panjang 60 hari)
    exchanged = False
    if exchange:
        ex = exchange_long_lived(token)
        if ex.get("access_token"):
            token = ex["access_token"]
            exchanged = True
        # kalau exchange gagal (mis. token udah long-lived), lanjut pakai token asli
    # validasi: ambil profil dari Meta
    url = (f"{GRAPH}/v1.0/me?fields=id,username"
           f"&access_token={urllib.parse.quote(token)}")
    try:
        me = _http(url)
    except urllib.error.HTTPError as e:
        return {"error": f"token invalid: HTTP {e.code}: {e.read().decode()[:180]}"}
    username = me.get("username")
    uid = me.get("id")
    if not username:
        return {"error": f"gak dapet username dari token: {str(me)[:150]}"}
    _save_token(username, token)
    return {"ok": True, "handle": username, "username": username,
            "user_id": uid, "exchanged": exchanged}


def remove_account(handle):
    d = _tokens()
    if handle in d:
        del d[handle]
        TOKENS.write_text(json.dumps(d, indent=2))
        TOKENS.chmod(0o600)
        _cache.pop(handle, None)
        return {"ok": True}
    return {"error": "akun gak ketemu"}


# ── OAuth flow (connect akun via login Meta) ─────────────────────────────
import secrets as _secrets

_BASE = TOKENS.parent  # ~/.threads-bot (share app.json + tokens)
_oauth_states = set()


def _app_config():
    """Baca app.json (app_id, app_secret, redirect_uri, scope). Cari di CMS dir dulu,
    fallback ke ~/.threads-bot."""
    from pathlib import Path as _P
    for base in [_P(__file__).resolve().parent.parent, _BASE]:
        f = base / "app.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
    return {}


def oauth_authorize_url(redirect_uri):
    """Build URL Meta authorize. Return (url, state) atau (None, error)."""
    cfg = _app_config()
    app_id = cfg.get("app_id")
    scope = cfg.get("scope", "threads_basic,threads_content_publish,"
                             "threads_manage_replies,threads_read_replies,"
                             "threads_manage_insights")
    if not app_id:
        return None, "app_id gak ada di app.json"
    state = _secrets.token_urlsafe(16)
    _oauth_states.add(state)
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "response_type": "code",
        "state": state,
    }
    return "https://threads.net/oauth/authorize?" + urllib.parse.urlencode(params), state


def oauth_exchange_code(code, redirect_uri):
    """Tuker authorization code -> short token -> long-lived, validasi, simpan.
    Return {ok, handle, ...} atau {error}."""
    cfg = _app_config()
    app_id = cfg.get("app_id")
    secret = cfg.get("app_secret")
    if not (app_id and secret):
        return {"error": "app_id/app_secret gak lengkap"}
    # step 1: code -> short-lived token
    data = urllib.parse.urlencode({
        "client_id": app_id,
        "client_secret": secret,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code,
    }).encode()
    try:
        tok = _http(f"{GRAPH}/oauth/access_token", data=data, method="POST")
    except urllib.error.HTTPError as e:
        return {"error": f"tuker code gagal: {e.read().decode()[:180]}"}
    short = tok.get("access_token")
    if not short:
        return {"error": f"gak dapet token: {str(tok)[:150]}"}
    # step 2: short -> long-lived
    long_token = short
    ex = exchange_long_lived(short)
    if ex.get("access_token"):
        long_token = ex["access_token"]
    # step 3: validasi + ambil username, simpan
    try:
        me = _http(f"{GRAPH}/v1.0/me?fields=id,username"
                   f"&access_token={urllib.parse.quote(long_token)}")
    except urllib.error.HTTPError as e:
        return {"error": f"validasi gagal: {e.read().decode()[:150]}"}
    username = me.get("username")
    if not username:
        return {"error": f"gak dapet username: {str(me)[:120]}"}
    _save_token(username, long_token)
    return {"ok": True, "handle": username, "user_id": me.get("id"),
            "exchanged": long_token != short}
