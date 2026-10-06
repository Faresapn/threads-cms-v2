#!/usr/bin/env python3
"""login_scraper.py — Login manual akun scraper Threads (sekali doang).

Jalankan: ~/x-browser-bot/venv/bin/python login_scraper.py
Browser kebuka (non-headless). Login manual pakai akun BUANGAN (+ 2FA kalau ada).
Setelah masuk ke home Threads, balik ke terminal, tekan ENTER. Sesi tersimpan
permanen di scraper_profile/ -> scrape berikutnya tinggal pakai.
"""
import sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROFILE_DIR = BASE / "scraper_profile"
PROFILE_DIR.mkdir(exist_ok=True)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

from playwright.sync_api import sync_playwright

print("=" * 60)
print("LOGIN AKUN SCRAPER THREADS (pakai akun BUANGAN, bukan akun penting)")
print("=" * 60)
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        viewport={"width": 1280, "height": 900},
        user_agent=UA,
        locale="id-ID",
    )
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://www.threads.com/login")
    print("\n👉 Browser kebuka. Login manual sebagai akun SCRAPER.")
    print("   (klik 'Continue with Instagram' / login IG, handle 2FA kalau diminta)")
    print("   Setelah masuk ke home/feed Threads, BALIK ke terminal ini.\n")
    input("Tekan ENTER kalau udah login sukses... ")
    # verifikasi
    try:
        pg.goto("https://www.threads.com/", wait_until="commit", timeout=30000)
        time.sleep(4)
        html = pg.content()
        if "Continue with Instagram" in html:
            print("⚠ Masih keliatan halaman login. Coba login lagi, ulangi script.")
        else:
            print("✅ Sesi tersimpan di scraper_profile/. Scraper siap dipakai.")
    except Exception as e:
        print(f"verifikasi gagal ({str(e)[:80]}), tapi sesi mungkin tetep kesimpen.")
    ctx.close()
