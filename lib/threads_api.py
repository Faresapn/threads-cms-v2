#!/usr/bin/env python3
"""threads_api.py — wrapper Threads Graph API buat CMS v2.
Reuse tokens.json dari bot lama (~/.threads-bot/tokens.json) biar akun yg udah
OAuth langsung kepakai. Support post chain + image (via URL publik R2).
"""
import json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

GRAPH = "https://graph.threads.net"
# Reuse token store bot lama biar gak perlu OAuth ulang.
TOKENS = Path.home() / ".threads-bot" / "tokens.json"
_cache = {}


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
    """Pisah post jadi chain part pakai delimiter '---' di baris sendiri."""
    parts, buf = [], []
    for line in (text or "").split("\n"):
        if line.strip() == "---":
            if buf:
                parts.append("\n".join(buf).strip()); buf = []
        else:
            buf.append(line)
    if buf:
        parts.append("\n".join(buf).strip())
    return [p for p in parts if p]


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


def reply_to(handle, root_post_id, text):
    """Reply teks (bisa berisi link) ke post sendiri. Buat soft-sell link produk."""
    tok = _tokens().get(handle)
    if not tok:
        raise RuntimeError(f"token @{handle} gak ada")
    info = account_info(handle, force=True)
    uid = info.get("id")
    if not uid:
        raise RuntimeError(f"gak dapet user id: {info.get('error', '?')}")
    p = {"text": text, "media_type": "TEXT", "reply_to_id": root_post_id,
         "access_token": tok}
    body = urllib.parse.urlencode(p).encode()
    cont = _http(f"{GRAPH}/v1.0/{uid}/threads", data=body, method="POST")
    cid = cont.get("id")
    if not cid:
        raise RuntimeError(f"container reply gagal: {str(cont)[:150]}")
    time.sleep(2)
    pub_body = urllib.parse.urlencode({"creation_id": cid, "access_token": tok}).encode()
    pub = _http(f"{GRAPH}/v1.0/{uid}/threads_publish", data=pub_body, method="POST")
    return {"reply_id": pub.get("id"), "text": text[:80]}


def publishing_limit(handle):
    tok = _tokens().get(handle)
    uid = account_info(handle, force=True).get("id")
    if not (tok and uid):
        return {"error": "no token/uid"}
    url = (f"{GRAPH}/v1.0/{uid}/threads_publishing_limit?fields=quota_usage,config"
           f"&access_token={urllib.parse.quote(tok)}")
    return _http(url)


def list_live_posts(handle, limit=25):
    """Daftar post terkirim dari Threads API (bukan queue lokal)."""
    tok = _tokens().get(handle)
    if not tok:
        raise RuntimeError(f"token @{handle} gak ada")
    uid = account_info(handle, force=True).get("id")
    if not uid:
        raise RuntimeError("gak dapet user id")
    url = (f"{GRAPH}/v1.0/{uid}/threads?fields=id,media_type,text,permalink,"
           f"timestamp,is_reply&limit={limit}&access_token={urllib.parse.quote(tok)}")
    r = _http(url)
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
    """Metrik 1 post: views, likes, replies, reposts, quotes."""
    tok = _tokens().get(handle)
    if not tok:
        raise RuntimeError(f"token @{handle} gak ada")
    metrics = "views,likes,replies,reposts,quotes"
    url = (f"{GRAPH}/v1.0/{post_id}/insights?metric={metrics}"
           f"&access_token={urllib.parse.quote(tok)}")
    try:
        r = _http(url)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:200]}
    out = {}
    for m in r.get("data", []):
        name = m.get("name")
        vals = m.get("values", [{}])
        out[name] = vals[0].get("value", 0) if vals else 0
    return out


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
