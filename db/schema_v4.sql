-- schema_v4.sql — auto-reply engine
-- Config auto-reply per akun + dedupe post yg udah di-reply.

CREATE TABLE IF NOT EXISTS autoreply_config (
  handle          TEXT PRIMARY KEY,
  enabled         INTEGER DEFAULT 0,
  keywords        TEXT,              -- JSON array keyword yg dicari
  min_likes       INTEGER DEFAULT 10,
  max_age_hours   INTEGER DEFAULT 72,  -- post rame tapi gak lebih tua dari 3 hari
  per_day         INTEGER DEFAULT 4, -- maks reply per hari per akun
  gap_hours       REAL DEFAULT 2.5,  -- jeda antar reply (jam)
  persona_id      INTEGER,           -- gaya reply (opsional)
  lang            TEXT DEFAULT 'id',
  last_reply_at   TEXT,              -- timestamp reply terakhir (buat jeda)
  updated_at      TEXT
);

-- dedupe: post yg udah pernah di-reply (jgn reply 2x), per akun
CREATE TABLE IF NOT EXISTS autoreply_seen (
  handle      TEXT,
  post_id     TEXT,                  -- id post Threads yg di-reply
  replied_at  TEXT,
  reply_text  TEXT,
  PRIMARY KEY (handle, post_id)
);

-- log reply harian buat ngitung kuota per_day
CREATE INDEX IF NOT EXISTS idx_autoreply_seen_handle ON autoreply_seen(handle, replied_at);
