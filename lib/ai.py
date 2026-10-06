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
    # strategi 2: scrape HTML publik dari tiap URL (og:description legacy)
    #   Note: Threads SKRG ga ekspos og:description di SSR, strategi ini mayoritas gagal.
    #   Dipertahankan sbg fast-path kalau suatu saat Meta nyalain lagi SSR.
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
    # strategi 3: Playwright scraper (butuh scraper_profile udah login)
    #   dipake kalau strategi 1 + 2 belum ngasih apa2
    if not texts:
        try:
            from lib import scraper
            for url in urls:
                if not url.strip():
                    continue
                try:
                    t = scraper.fetch_post_text(url.strip(), headless=True)
                    if t and t not in texts:
                        texts.append(t)
                except Exception:
                    continue
        except Exception:
            pass
    return texts[:30]


# ── reply soft-sell: teks CTA dari deskripsi produk ────────────────────────
def softsell_reply_text(product_desc, link="", lang="id"):
    """Bikin teks reply soft-sell natural dari deskripsi singkat produk.
    Dipakai di reply bawah thread (bareng gambar produk), BUKAN di utas.
    link: opsional, kalau diisi ditaruh di akhir. Return teks siap-post."""
    if not product_desc or not product_desc.strip():
        return link or ""
    lang_rule = ("Bahasa Indonesia santai, ramah, kayak rekomen ke temen."
                 if lang == "id" else
                 "Casual friendly English, like recommending to a friend.")
    sys = (
        "Kamu copywriter soft-selling. Bikin 1 reply PENDEK (2-4 kalimat) buat "
        "nawarin produk secara halus, muncul SETELAH thread story (bukan hard-sell).\n"
        "ATURAN:\n"
        f"- {lang_rule}\n"
        "- JANGAN pakai em-dash. Pakai koma/titik.\n"
        "- Nyambung natural dari cerita, bukan iklan kaku.\n"
        "- Sebut manfaat/hasil, bukan fitur teknis doang.\n"
        "- Tutup dgn ajakan halus (cek, lihat, coba).\n"
        "- JANGAN tulis link (link ditambahin sistem terpisah).\n"
        "- Output HANYA teks reply, tanpa tanda kutip."
    )
    user = f"Deskripsi produk: {product_desc.strip()}"
    out = _chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": user}
    ], max_tokens=400)
    out = out.replace("—", ", ").replace(" –", ",").strip().strip('"')
    if link:
        out = f"{out}\n\n{link}"
    return out


# ── INSTANT CONTENT: LLM nentuin sendiri jumlah part + isi dari persona+judul ──
def generate_instant(persona, title, desc="", lang=None):
    """Generate konten instant. LLM bebas nentuin berapa part (1 post atau thread)
    yang paling pas buat judul + gaya persona. Minim input: judul + desk singkat.
    persona: dict {name, system_prompt, learned_style, sample_posts, lang}
    Return teks siap-post (part dipisah '---' kalau thread)."""
    lang = lang or persona.get("lang", "id")
    style = persona.get("learned_style") or ""
    custom = persona.get("system_prompt") or ""
    samples = persona.get("sample_posts") or []
    pname = persona.get("name") or "default"
    lang_rule = ("Bahasa Indonesia santai, natural, relatable."
                 if lang == "id" else
                 "Casual natural English, relatable tone.")
    sys = (
        f"Kamu content creator Threads dgn PERSONA: {pname}.\n"
    )
    if custom:
        sys += f"KARAKTER: {custom}\n"
    if style:
        sys += f"\nGAYA WAJIB DITIRU (dari referensi):\n{style}\n"
    if samples:
        ex = "\n---\n".join(samples[:4])
        sys += f"\nCONTOH POST GAYA INI:\n{ex}\n"
    sys += (
        "\nTUGAS: bikin konten Threads dari judul yg dikasih. KAMU yg nentuin sendiri "
        "formatnya: kalau cocok 1 post pendek ya 1 post, kalau butuh thread panjang "
        "(2-6 part) ya bikin thread. Pilih yg paling natural buat topik + gaya ini.\n\n"
        "ATURAN:\n"
        f"- {lang_rule}\n"
        "- JANGAN pakai em-dash (—). Pakai koma/titik.\n"
        "- Kalau thread: pisah tiap part dgn baris berisi '---' doang. Part 1 = hook kuat.\n"
        "- Kalau 1 post: gak usah ada '---'.\n"
        "- Tulis kayak manusia, natural, ada opini/emosi. BUKAN gaya AI kaku.\n"
        "- Konten utuh siap-post. JANGAN kasih penjelasan/meta, langsung isinya."
    )
    user = f"Judul/ide: {title}"
    if desc and desc.strip():
        user += f"\nDeskripsi tambahan: {desc.strip()}"
    user += "\n\nBikin kontennya sekarang, pilih format yg paling pas."
    out = _chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": user}
    ], max_tokens=2600)
    out = out.replace("—", ", ").replace(" –", ",")
    return _trim_incomplete(out.strip())


# ── auto-reply: generate reply nyambung konteks post orang ─────────────────
def generate_reply(post_text, persona=None, lang="id"):
    """Bikin reply SINGKAT & natural buat post orang (engagement, bukan spam).
    post_text: isi post yg mau di-reply.
    persona: opsional, buat warna gaya.
    Return teks reply (1-2 kalimat, gak jualan, nyambung konteks)."""
    lang_rule = ("Bahasa Indonesia santai, kayak bales temen di komentar."
                 if lang == "id" else
                 "Casual English, like replying to a friend's post.")
    pstyle = ""
    if persona and persona.get("system_prompt"):
        pstyle = f"\nKarakter kamu: {persona['system_prompt']}\n"
    sys = (
        "Kamu user Threads yg lagi scroll dan nemu post menarik, lalu ikut komentar.\n"
        f"{pstyle}"
        "TUGAS: bikin 1 reply singkat yg NYAMBUNG sama isi post.\n"
        "ATURAN KETAT:\n"
        f"- {lang_rule}\n"
        "- MAKS 1-2 kalimat pendek. Jangan panjang.\n"
        "- NYAMBUNG konteks post (nanggepin isinya, bukan asal komen).\n"
        "- JANGAN jualan, JANGAN promosi, JANGAN taruh link.\n"
        "- JANGAN pakai em-dash. JANGAN hashtag. JANGAN mention.\n"
        "- Natural kayak manusia: setuju, nambahin, nanya, atau reaksi jujur.\n"
        "- Hindari template ('keren banget!', 'setuju bgt'). Spesifik ke isinya.\n"
        "- Output HANYA teks reply, tanpa tanda kutip."
    )
    user = f"Post yg mau di-reply:\n\"{post_text[:600]}\"\n\nTulis 1 reply natural yg nyambung."
    out = _chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": user}
    ], max_tokens=200)
    out = out.replace("—", ", ").replace(" –", ",").strip().strip('"')
    return out


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
    ], max_tokens=2200)
    # bersihin em-dash kalau lolos
    out = out.replace("—", ", ").replace(" –", ",")
    return _trim_incomplete(out.strip())


# ── random auto-post (edukasi, niche-based) ─────────────────────────────────
def generate_random(niche, style_guide, lang="id", num_parts=2, persona=None,
                    topic_hint=None, hook_examples=None, hook_name=None,
                    avoid_topics=None):
    """Bikin utas edukasi random sesuai niche + style guide referensi.
    lang: 'id' atau 'en' (ikut bahasa akun).
    persona: opsional, kalau ada dipakai buat nambah karakter.
    hook_examples: list contoh hook (dari hook library / referensi user) biar
                   opening tiap post BEDA, gak template. hook_name = nama tipe-nya.
    avoid_topics: list teks/hook post yg SUDAH pernah dibahas akun ini. LLM wajib
                  bikin topik yg beda total dari daftar ini (anti-duplikat).
    Return teks siap-post (part dipisah '---').
    """
    lang_rule = ("Bahasa Indonesia santai, ngobrol, relatable."
                 if lang == "id" else
                 "English, casual but insightful, global audience tone.")
    hook_block = ""
    if hook_examples:
        ex = "\n".join(f"  - {h}" for h in hook_examples[:6])
        tipe = f" (tipe: {hook_name})" if hook_name else ""
        hook_block = (
            f"\nHOOK WAJIB{tipe}: Bagian 1 HARUS pakai gaya hook di bawah ini. "
            f"Tiru POLA/vibe-nya, bikin yang BARU & spesifik buat niche ini, JANGAN copy mentah:\n"
            f"{ex}\n"
        )
    avoid_block = ""
    if avoid_topics:
        av = "\n".join(f"  - {a}" for a in avoid_topics[:12])
        avoid_block = (
            f"\nTOPIK YANG SUDAH DIBAHAS (HARAM DIULANG):\n{av}\n"
            "WAJIB: pilih topik/sudut yang BENAR-BENAR BEDA dari daftar di atas. "
            "Jangan ngebahas hal yang sama walau beda kata. Kalau niche-nya mirip, "
            "cari sub-topik, angle, atau kasus spesifik yang belum pernah muncul.\n"
        )
    sys = (
        "Kamu content creator Threads jago bikin utas edukasi yg viral & natural.\n\n"
        f"NICHE: {niche}\n\n"
        f"GAYA WAJIB DITIRU:\n{style_guide}\n"
        f"{hook_block}"
        f"{avoid_block}\n"
        "ATURAN:\n"
        f"- {lang_rule}\n"
        "- JANGAN pakai em-dash (—). Pakai koma/titik.\n"
        f"- Buat {num_parts} bagian. Pisah tiap bagian dgn baris '---' saja.\n"
        "- Bagian 1 = HOOK kuat yg bikin berhenti scroll.\n"
        "- Isi value konkret & actionable, bukan omong kosong motivasi.\n"
        "- Ini KONTEN EDUKASI murni. JANGAN jualan/promosi produk apapun.\n"
        "- Tutup dgn soft CTA (save/komen/pilih).\n"
        "- Tulis kayak manusia beneran, bukan AI. Natural, ada opini."
    )
    if persona and persona.get("system_prompt"):
        sys += f"\n\nKARAKTER TAMBAHAN: {persona['system_prompt']}"
    user = f"Bikin 1 utas edukasi tentang niche '{niche}'."
    if topic_hint:
        user += f" Fokus ke sudut: {topic_hint}."
    user += " Pilih angle yg fresh & spesifik, jangan generik, jangan ngulang topik lama."
    out = _chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": user}
    ], max_tokens=2600)
    out = out.replace("—", ", ").replace(" –", ",")
    return _trim_incomplete(out.strip())


def _trim_incomplete(text):
    """Kalau teks kepotong di tengah kalimat (gak diakhiri . ! ? : atau emoji),
    potong balik ke kalimat utuh terakhir biar gak ada 'itu al' nyantol.
    Jaga struktur part (---) tetep utuh."""
    if not text:
        return text
    # kalau ending udah wajar, biarin
    if text[-1] in ".!?:\"')👇🔥✨":
        return text
    # pisah per part, cek part terakhir
    parts = text.split("\n---\n")
    last = parts[-1].rstrip()
    # cari akhir kalimat terakhir di part itu
    import re as _re
    ends = [m.end() for m in _re.finditer(r'[.!?:](?=\s|$)', last)]
    if ends:
        last = last[:ends[-1]].rstrip()
        parts[-1] = last
        return "\n---\n".join(parts).strip()
    # part terakhir gak ada kalimat utuh -> buang part itu (kalau ada part lain)
    if len(parts) > 1:
        return "\n---\n".join(parts[:-1]).strip()
    return text


if __name__ == "__main__":
    import sys
    print(json.dumps({"base": AI_BASE, "model": AI_MODEL, "key_set": bool(AI_KEY)}, indent=2))
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print(_chat([{"role": "user", "content": "balas: siap"}], max_tokens=10))
