# Threads CMS v2

Self-hosted CMS buat kelola konten Threads: compose, drag-drop image
(auto-upload ke object storage), schedule, dan auto-post lewat scheduler.
Data disimpan di SQLite.

## Fitur

| | |
|---|---|
| Storage | SQLite (`db/cms.db`) |
| Image | drag-drop → auto-upload object storage → CDN publik |
| UI | dashboard dark, tab, filter, thumbnail, char/part counter |
| Media | media library (reusable) + attach per part |
| **AI generate** | generate thread pakai persona (LLM OpenAI-compatible) |
| **Persona** | per akun, belajar gaya dari link Threads |
| Insight/analytics | ✓ |
| OAuth/refresh token | ✓ |

## AI Generate

- Pakai LLM **OpenAI-compatible** (endpoint & model diatur lewat `.env`:
  `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`).
- **Persona per akun**: nama, instruksi gaya, bahasa, + link Threads referensi.
- **Belajar gaya**: fetch post dari link (Graph API kalau akun sendiri, fallback
  scrape) → AI rangkum ciri gaya → disimpan → dipakai pas generate.
- Aturan playbook auto: NO em-dash, soft-sell (link di reply bukan thread).

## Arsitektur

- **Python stdlib HTTP server** + scheduler thread (cek tiap 30s).
- **SQLite** — posts, accounts, media, media_library.
- **Object storage (S3-compatible, via boto3)** — bucket + prefix diatur lewat
  `.env`, file diakses publik lewat CDN URL (juga dari `.env`).
- **Threads Graph API** — token akun dibaca dari file token lokal (akun yang
  udah OAuth langsung kepakai, gak perlu OAuth ulang).

> Kenapa self-hosted, bukan serverless: scheduler butuh proses nyala 24/7 dan
> Threads API cuma nerima image via URL publik. Platform serverless gak cocok
> buat loop scheduler; object storage + CDN yang handle image publik.

## Setup

```bash
# 1. install dep (butuh boto3 di venv)
python3 -m pip install boto3

# 2. .env — isi credential object storage (lihat .env.example)
cp .env.example .env   # lalu isi

# 3. init DB + migrate akun/queue
python3 lib/db.py
python3 scripts/migrate.py

# 4. jalanin
./run.sh
# → http://127.0.0.1:8455
```

## Autostart (macOS, nyala sendiri pas login)

```bash
bash deploy/install.sh
```

Pakai launchd, KeepAlive on (auto-restart kalau mati). Server + scheduler +
auto-post jalan terus di background.

## .env

Lihat `.env.example` untuk daftar lengkap. Variabel object storage:

```
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_MEDIA_BUCKET=<nama-bucket>
R2_CDN_URL=https://<cdn-domain-kamu>
R2_PREFIX=<prefix>
```

> Jangan commit `.env` — semua credential, nama bucket, dan domain CDN sifatnya
> rahasia dan sudah di-gitignore.

## Cara post pakai gambar

1. Buka dashboard, pilih akun.
2. Tulis teks. Pisah part chain pakai `---` di baris sendiri.
3. Seret foto ke drop-zone (auto-upload). Gambar ke-N nempel di part ke-N.
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
