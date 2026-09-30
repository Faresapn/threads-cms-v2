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


def publishing_limit(handle):
    tok = _tokens().get(handle)
    uid = account_info(handle, force=True).get("id")
    if not (tok and uid):
        return {"error": "no token/uid"}
    url = (f"{GRAPH}/v1.0/{uid}/threads_publishing_limit?fields=quota_usage,config"
           f"&access_token={urllib.parse.quote(tok)}")
    return _http(url)
