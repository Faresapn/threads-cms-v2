# Threads CMS v2

Upgrade dari bot Threads lama (`~/.threads-bot`). Repo terpisah, self-hosted (local).

CMS untuk kelola konten Threads: compose, drag-drop image (auto-upload R2),
schedule, dan auto-post lewat scheduler. Data di SQLite (bukan JSON lagi).

## Beda dari v1

| | v1 (`.threads-bot`) | v2 (repo ini) |
|---|---|---|
| Storage | `queue.json` file | SQLite (`db/cms.db`) |
| Image | manual URL | drag-drop → auto-upload R2 → CDN |
| UI | basic | dashboard dark, tab, filter, thumbnail, char/part counter |
| Media | — | media library (reusable) + attach per part |
| **AI generate** | — | generate thread pakai persona (9Router lokal) |
| **Persona** | — | per akun, belajar gaya dari link Threads |
| Insight/analytics | ✓ | ✓ (diport) |
| OAuth/refresh token | ✓ | ✓ (diport) |

## AI Generate (fitur baru)

- Pakai **9Router lokal** (`localhost:20128`, OpenAI-compatible) — model yg lagi
  jalan (default `cc/claude-sonnet-5`). Config di `.env` (`AI_BASE_URL`,
  `AI_API_KEY`, `AI_MODEL`).
- **Persona per akun**: nama, instruksi gaya, bahasa, + link Threads referensi.
- **Belajar gaya**: fetch post dari link (Graph API kalau akun sendiri, fallback
  scrape `og:description`) → AI rangkum ciri gaya → disimpan → dipakai pas generate.
- Aturan playbook auto: NO em-dash, soft-sell (link di reply bukan thread).

## Arsitektur

- **Python stdlib HTTP server** + scheduler thread (cek tiap 30s).
- **SQLite** — posts, accounts, media, media_library.
- **Cloudflare R2** (S3-compat via boto3) — bucket `media`, prefix `threads/`,
  publik lewat CDN `https://cdn.promptedsite.com`. Shared bucket dgn PromptedSite
  tapi prefix kepisah.
- **Threads Graph API** — reuse `tokens.json` dari bot lama (akun yg udah OAuth
  langsung kepakai, gak perlu OAuth ulang).

> Kenapa self-hosted, bukan Vercel: scheduler butuh proses nyala 24/7 dan
> Threads API cuma nerima image via URL publik. Vercel serverless gak cocok buat
> loop scheduler; R2+CDN yg handle image publik.

## Setup

```bash
# 1. install dep (pakai venv yg punya boto3)
~/x-browser-bot/venv/bin/python3 -m pip install boto3

# 2. .env — R2 credential (lihat .env.example)
cp .env.example .env   # lalu isi

# 3. init DB + migrate akun/queue dari bot lama
python3 lib/db.py
python3 scripts/migrate.py

# 4. jalanin
./run.sh
# → http://127.0.0.1:8455
```

## .env

```
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_MEDIA_BUCKET=media
R2_CDN_URL=https://cdn.promptedsite.com
R2_PREFIX=threads
```

## Cara post pakai gambar

1. Buka dashboard, pilih akun.
2. Tulis teks. Pisah part chain pakai `---` di baris sendiri.
3. Seret foto ke drop-zone (auto-upload R2). Gambar ke-N nempel di part ke-N.
4. Isi jadwal (opsional). Kosong = simpan draft.
5. Klik Simpan. Scheduler auto-post pas waktunya, atau "Post sekarang" manual.

## API

| Method | Path | Body |
|---|---|---|
| GET | `/api/accounts` | — |
| GET | `/api/posts?status&handle` | — |
| GET | `/api/post?id` | — |
| POST | `/api/post` | `{handle,text,scheduled_at?}` |
| POST | `/api/post/update` | `{id,text?,scheduled_at?,unset_time?,status?}` |
| POST | `/api/post/delete` | `{id}` |
| POST | `/api/post/publish` | `{id}` |
| POST | `/api/upload` | multipart `file` |
| POST | `/api/post/attach` | `{id,part_index,public_url,r2_key?}` |
| GET | `/api/library` | — |
| GET | `/api/limit?handle` | — |

## Status post

`draft` → `scheduled` → `posting` → `posted` / `failed`
