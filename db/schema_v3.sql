-- Threads CMS v2 — schema v2.2 (auto random-post)
-- Jalan di atas schema.sql + schema_v2.sql. Idempotent.

-- Config auto random-post per akun
CREATE TABLE IF NOT EXISTS autopost_config (
    handle          TEXT PRIMARY KEY,
    enabled         INTEGER DEFAULT 0,          -- on/off toggle
    lang            TEXT DEFAULT 'id',           -- id | en (bahasa post)
    niches          TEXT,                         -- JSON list niche
    posts_per_day   INTEGER DEFAULT 2,           -- maks 2x sehari (anti-spam)
    best_hours      TEXT,                         -- JSON list jam terbaik (0-23)
    persona_id      INTEGER,                      -- persona opsional buat gaya
    num_parts_min   INTEGER DEFAULT 1,
    num_parts_max   INTEGER DEFAULT 3,
    last_scheduled  TEXT,                         -- tanggal terakhir digenerate (YYYY-MM-DD)
    style_urls      TEXT,                         -- JSON list link referensi gaya (editable)
    style_guide     TEXT,                         -- rangkuman gaya (built-in + hasil belajar)
    updated_at      TEXT
);

-- Tandai post hasil auto-random (biar kepisah dari manual)
-- kolom ditambah via ALTER di db.init_db (idempotent).
