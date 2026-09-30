#!/usr/bin/env python3
"""ai.py — generate thread pakai AI (9Router lokal :20128, OpenAI-compatible).
Fitur:
  - learn_style_from_urls: fetch post dari link Threads → AI simpulin gaya nulis
  - generate: bikin thread dari topik + persona (niru gaya)

Config dibaca dari .env (fallback ke config Hermes).
Aturan konten dari playbook: NO em-dash, soft-sell (link di reply bukan thread).
"""
import os, json, re, urllib.request, urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def _load_env():
    envf = BASE / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

AI_BASE = os.environ.get("AI_BASE_URL", "http://localhost:20128/v1").rstrip("/")
AI_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "cc/claude-sonnet-5")


def _chat(messages, max_tokens=1200, temperature=None):
    """Panggil chat completion (non-stream). temperature opsional (sebagian model nolak)."""
    if not AI_KEY:
        raise RuntimeError("AI_API_KEY belum di-set di .env")
    payload = {
        "model": AI_MODEL, "messages": messages,
        "max_tokens": max_tokens, "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{AI_BASE}/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {AI_KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"AI HTTP {e.code}: {e.read().decode()[:200]}")
    return data["choices"][0]["message"]["content"].strip()


# ── ambil teks post dari link Threads ──────────────────────────────────────
def fetch_thread_texts(urls, handle=None):
    """Coba ambil teks post dari list URL Threads.
    Strategi:
      1. Kalau akun sendiri (handle) → pakai Graph API list_posts (paling akurat).
      2. Fallback: scrape og:description / judul dari HTML publik.
    Return list string teks post.
    """
    texts = []
    # strategi 1: Graph API kalau ada handle + token
    if handle:
        try:
            from lib import threads_api
            info = threads_api.account_info(handle, force=True)
            uid = info.get("id")
            tok = threads_api._tokens().get(handle)
            if uid and tok:
                import urllib.parse
                u = (f"https://graph.threads.net/v1.0/{uid}/threads"
                     f"?fields=text,media_type,permalink&limit=25"
                     f"&access_token={urllib.parse.quote(tok)}")
                r = threads_api._http(u)
                for p in r.get("data", []):
                    t = (p.get("text") or "").strip()
                    if t:
                        texts.append(t)
        except Exception:
            pass
    # strategi 2: scrape HTML publik dari tiap URL
    for url in urls:
        if not url.strip():
            continue
        try:
            import urllib.request as _ureq
            req = _ureq.Request(url.strip(), headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"})
            with _ureq.urlopen(req, timeout=20) as r:
                html = r.read().decode("utf-8", "ignore")
            # og:description biasanya isi teks post
            m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
            if m:
                t = re.sub(r'&quot;', '"', m.group(1))
                t = re.sub(r'&#039;', "'", t)
                t = re.sub(r'&amp;', "&", t).strip()
                if t and t not in texts:
                    texts.append(t)
        except Exception:
            continue
    return texts[:30]


# ── analisis gaya dari contoh post ─────────────────────────────────────────
def learn_style(texts, lang="id"):
    """Kasih AI contoh post → dia rangkum ciri gaya nulis (buat dipakai generate)."""
    if not texts:
        return ""
    joined = "\n\n---\n\n".join(texts[:25])
    sys = ("Kamu analis gaya penulisan. Baca contoh-contoh post Threads berikut, "
           "lalu rangkum CIRI GAYA penulisnya dalam poin-poin ringkas dan konkret: "
           "tone, panjang kalimat, diksi khas, pola pembuka, penggunaan emoji, "
           "cara hook, topik yang sering diangkat. Output bahasa Indonesia, ringkas, "
           "dipakai sebagai instruksi buat meniru gaya. JANGAN pakai em-dash.")
    out = _chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": f"Contoh post:\n\n{joined}\n\nRangkum ciri gayanya:"}
    ], max_tokens=600)
    return out


# ── generate thread ────────────────────────────────────────────────────────
def generate(topic, persona, num_parts=1, lang=None, has_link=False, extra_brief=None):
    """Generate thread dari topik, niru gaya persona.
    persona: dict {name, system_prompt, learned_style, sample_posts, lang}
    has_link: True kalau ada link produk (boleh soft-sell CTA di thread, TAPI link
              tetap di reply). False = murni storytelling, JANGAN nawarin produk.
    extra_brief: penjelasan tambahan dari user "mau seperti apa".
    Return teks siap-post (part dipisah '---' kalau >1).
    """
    lang = lang or persona.get("lang", "id")
    style = persona.get("learned_style") or ""
    custom = persona.get("system_prompt") or ""
    samples = persona.get("sample_posts") or []

    rules = (
        "ATURAN WAJIB:\n"
        "- JANGAN pakai em-dash (—) sama sekali. Pakai koma / titik / kata sambung.\n"
        "- Tulis natural, manusiawi, bukan gaya AI kaku.\n"
        f"- Bahasa: {'Indonesia santai' if lang == 'id' else 'English, global tone'}.\n"
    )
    if has_link:
        rules += (
            "- Ini konten SOFT-SELL. Boleh ada CTA halus di bagian akhir yg bikin orang "
            "penasaran sama produk/link, TAPI JANGAN taruh link di dalam thread. "
            "Link ditaruh di reply/komen (di-handle otomatis, kamu gak usah nulis link).\n")
    else:
        rules += (
            "- Ini MURNI STORYTELLING. JANGAN nawarin produk, JANGAN ada CTA jualan, "
            "JANGAN nyerempet promosi apapun. Fokus cerita/insight/value aja yg natural.\n")
    if num_parts > 1:
        rules += (f"- Buat thread {num_parts} bagian. Pisah tiap bagian dengan baris "
                  "berisi '---' saja. Bagian pertama = hook kuat.\n")
    else:
        rules += "- Satu post saja, padat dan nge-hook.\n"

    sys = "Kamu content creator Threads yang jago bikin post viral & natural.\n"
    if custom:
        sys += f"\nPERSONA: {custom}\n"
    if style:
        sys += f"\nGAYA NULIS YANG HARUS DITIRU:\n{style}\n"
    sys += "\n" + rules
    if samples:
        ex = "\n\n".join(f"- {s}" for s in samples[:5])
        sys += f"\nCONTOH POST GAYA INI (tiru vibe-nya, jangan jiplak):\n{ex}\n"

    user_msg = f"Bikin post Threads tentang: {topic}"
    if extra_brief:
        user_msg += f"\n\nArahan tambahan dari user: {extra_brief}"
    out = _chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": user_msg}
    ], max_tokens=1200)
    # bersihin em-dash kalau lolos
    out = out.replace("—", ", ").replace(" –", ",")
    return out.strip()


if __name__ == "__main__":
    import sys
    print(json.dumps({"base": AI_BASE, "model": AI_MODEL, "key_set": bool(AI_KEY)}, indent=2))
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print(_chat([{"role": "user", "content": "balas: siap"}], max_tokens=10))
