#!/usr/bin/env python3
"""scraper.py — Threads search scraper (Playwright persistent profile, ZERO API).

Buat auto-reply: cari post rame (TOP / banyak like) by keyword, buat di-reply
oleh akun target lewat API resmi. Akun scraper = akun buangan khusus baca data.

Pakai persistent browser profile (folder permanen) biar sesi login awet.
Login sekali via login_scraper.py, abis itu scrape tinggal pakai profil itu.

Pelajaran dari pola yg udah ada:
- Selector `div[data-pressable-container]` KELUAS (kena sidebar/feed saran).
  Di sini kita scope ketat + validasi: keyword harus muncul di teks, ada
  permalink /post/, username wajar, like count keparse.
"""
from __future__ import annotations
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE / "scraper_profile"   # persistent chrome profile (login tersimpan)
PROFILE_DIR.mkdir(exist_ok=True)

SEARCH_URL = "https://www.threads.com/search?q={q}&serp_type=default&filter={filt}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _num(s):
    """'1.2K' / '3,456' / '1,8 rb' / '2 jt' -> int. Dukung format EN + Indo."""
    if not s:
        return 0
    s = str(s).strip().lower().replace("\u00a0", " ")
    # format Indonesia: "1,8 rb" = 1800, "2,5 jt" = 2500000
    m_id = re.search(r"([\d.,]+)\s*(rb|jt|k|m|b)?", s)
    if not m_id:
        return 0
    numpart = m_id.group(1)
    suffix = (m_id.group(2) or "").lower()
    # koma = desimal di Indo (1,8), titik = ribuan ATAU desimal. Normalisasi:
    if "," in numpart and "." in numpart:
        numpart = numpart.replace(".", "").replace(",", ".")  # 1.234,5 -> 1234.5
    elif "," in numpart:
        # koma: desimal kalau 1 digit setelahnya (1,8), ribuan kalau 3 (1,234)
        parts = numpart.split(",")
        numpart = (parts[0] + "." + parts[1]) if len(parts[-1]) <= 2 else numpart.replace(",", "")
    try:
        v = float(numpart)
    except Exception:
        return 0
    mult = {"": 1, "rb": 1_000, "k": 1_000, "jt": 1_000_000, "m": 1_000_000, "b": 1_000_000_000}
    return int(v * mult.get(suffix, 1))


def _launch(pw, headless=True):
    """Persistent context: profil login awet di PROFILE_DIR."""
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 1600},
        user_agent=UA,
        locale="id-ID",
    )


def is_logged_in(headless=True):
    """Cek sesi scraper masih valid (gak ketendang ke login)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = _launch(pw, headless=headless)
        try:
            pg = ctx.new_page()
            pg.goto("https://www.threads.com/", wait_until="commit", timeout=40000)
            time.sleep(4)
            # kalau ada dialog login / tombol "Continue with Instagram" = belum login
            html = pg.content()
            logged = ("Continue with Instagram" not in html
                      and "Log in" not in (pg.title() or ""))
            return logged
        finally:
            ctx.close()


def fetch_post_text(url, headless=True, timeout=30000):
    """Ambil teks post dari URL Threads via Playwright (butuh sesi login).
    Threads skrg SSR kosong → harus render JS. Return string atau '' kalau gagal.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    with sync_playwright() as pw:
        ctx = _launch(pw, headless=headless)
        try:
            pg = ctx.new_page()
            pg.goto(url, wait_until="domcontentloaded", timeout=timeout)
            # tunggu article post render
            try:
                pg.wait_for_selector('div[role="article"], article', timeout=15000)
            except PWTimeout:
                pass
            time.sleep(3)
            # strategi 1: ambil dari meta og:description (Threads kadang set after JS)
            try:
                og = pg.locator('meta[property="og:description"]').first
                desc = og.get_attribute("content", timeout=1500) or ""
                if desc and len(desc) > 20:
                    return desc.strip()
            except Exception:
                pass
            # strategi 2: baca text container di article pertama (post utama)
            try:
                art = pg.locator('div[role="article"], article').first
                # Threads bungkus teks post di span-span dalam div[dir]
                txt = art.locator('div[dir="auto"]').first.inner_text(timeout=4000)
                if txt and len(txt.strip()) > 10:
                    return txt.strip()
            except Exception:
                pass
            # strategi 3: fallback regex dari HTML (cari text terpanjang di JSON state)
            html = pg.content()
            import re
            # cari pola "text":"..." dengan panjang > 30 char di JSON payload Threads
            matches = re.findall(r'"text":"((?:[^"\\]|\\.){30,800})"', html)
            if matches:
                # ambil yang terpanjang (biasanya post utama)
                best = max(matches, key=len)
                # unescape sederhana
                best = best.replace('\\n', '\n').replace('\\"', '"').replace('\\/', '/')
                return best.strip()
            return ""
        finally:
            ctx.close()


def search_posts(keyword, min_likes=100, max_age_hours=24, limit=15,
                 search_type="top", headless=True, scrolls=5):
    """Scrape hasil search Threads buat 1 keyword.
    Return list post: {id, url, username, text, likes, ts_iso}
    Filter: keyword muncul di teks, likes >= min_likes, umur <= max_age_hours.
    search_type: 'top' (populer/rame) atau 'recent' (terbaru).
    """
    from playwright.sync_api import sync_playwright
    filt = "recent" if search_type == "recent" else "top"
    q = keyword.replace(" ", "%20")
    url = SEARCH_URL.format(q=q, filt=filt)
    out = []
    seen_ids = set()
    kw_lower = keyword.lower()
    now = time.time()
    with sync_playwright() as pw:
        ctx = _launch(pw, headless=headless)
        try:
            pg = ctx.new_page()
            pg.goto(url, wait_until="commit", timeout=45000)
            time.sleep(3.5)
            # scroll buat muat lebih banyak hasil
            for _ in range(scrolls):
                pg.mouse.wheel(0, 1600)
                time.sleep(1.4)
            # ambil tiap post: artikel punya link /post/ + <time>
            # scope ketat: cuma elemen yg punya permalink status + time
            articles = pg.locator('div[data-pressable-container="true"]')
            n = min(articles.count(), 60)
            for i in range(n):
                try:
                    art = articles.nth(i)
                    # permalink /post/ (wajib, buang container non-post)
                    link_el = art.locator('a[href*="/post/"]').first
                    href = link_el.get_attribute("href", timeout=1500) or ""
                    m = re.search(r"/@([^/]+)/post/([A-Za-z0-9_-]+)", href)
                    if not m:
                        continue
                    username, pid = m.group(1), m.group(2)
                    if pid in seen_ids:
                        continue
                    # teks post
                    try:
                        text = art.inner_text(timeout=1500)
                    except Exception:
                        text = ""
                    text_clean = " ".join(text.split())
                    # VALIDASI 1: keyword relevan di teks (buang sampah sidebar).
                    # Longgar: lolos kalau frasa utuh ADA, ATAU mayoritas kata ada.
                    tl = text_clean.lower()
                    kw_words = [w for w in kw_lower.split() if len(w) >= 3]
                    if kw_words:
                        hit = sum(1 for w in kw_words if w in tl)
                        # butuh minimal separuh kata (dibulatkan ke atas) ATAU frasa utuh
                        need = (len(kw_words) + 1) // 2
                        if kw_lower not in tl and hit < need:
                            continue
                    # timestamp dari <time datetime="...">
                    ts_iso, age_ok = None, True
                    try:
                        t_el = art.locator("time").first
                        ts_iso = t_el.get_attribute("datetime", timeout=1000)
                        if ts_iso:
                            from datetime import datetime, timezone
                            dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
                            age_h = (now - dt.timestamp()) / 3600
                            age_ok = age_h <= max_age_hours
                    except Exception:
                        pass
                    if not age_ok:
                        continue
                    # like count: cari angka deket ikon like. Threads gak kasih label
                    # bersih, jadi ambil angka terbesar dari teks metrik di bawah post.
                    likes = _extract_likes(art)
                    if likes < min_likes:
                        continue
                    seen_ids.add(pid)
                    out.append({
                        "id": pid,
                        "url": f"https://www.threads.com/@{username}/post/{pid}",
                        "username": username,
                        "text": text_clean[:500],
                        "likes": likes,
                        "ts_iso": ts_iso,
                    })
                    if len(out) >= limit:
                        break
                except Exception:
                    continue
        finally:
            ctx.close()
    return out


def _extract_likes(art):
    """Like count ada di tombol aksi (bukan span teks). Urutan tombol Threads:
    like, reply, repost, share. Angka PERTAMA (paling kiri) = like count."""
    try:
        btns = art.get_by_role("button").all()
    except Exception:
        return 0
    for b in btns:
        try:
            txt = (b.inner_text(timeout=400) or "").strip()
        except Exception:
            continue
        if not txt:
            continue
        # tombol metrik: isinya angka (+ suffix rb/jt/K). Ambil yg pertama ketemu.
        if re.match(r"^[\d.,]+\s*(rb|jt|k|m|b)?$", txt.lower()):
            v = _num(txt)
            if v > 0:
                return v
    return 0


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        print("logged_in:", is_logged_in(headless=True))
    elif len(sys.argv) > 2 and sys.argv[1] == "search":
        kw = sys.argv[2]
        ml = int(sys.argv[3]) if len(sys.argv) > 3 else 100
        res = search_posts(kw, min_likes=ml, headless=True)
        print(f"ketemu {len(res)} post:")
        for p in res:
            print(f"  @{p['username']} | {p['likes']} likes | {p['text'][:70]}")
            print(f"    {p['url']}")
    else:
        print("usage: python scraper.py check | search <keyword> [min_likes]")
