-- Threads CMS v2 — schema SQLite
-- Migrasi dari queue.json (file JSON) ke DB beneran.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Akun Threads (multi-account)
CREATE TABLE IF NOT EXISTS accounts (
    handle       TEXT PRIMARY KEY,          -- username tanpa @
    display_name TEXT,
    user_id      TEXT,                       -- Threads user id (di-cache)
    added_at     TEXT NOT NULL
);

-- Post / item di queue
CREATE TABLE IF NOT EXISTS posts (
    id            TEXT PRIMARY KEY,          -- q_xxxxxxxx
    handle        TEXT NOT NULL,
    text          TEXT NOT NULL,             -- body; "---" pisah antar part (chain)
    status        TEXT NOT NULL DEFAULT 'draft',  -- draft|scheduled|posting|posted|failed
    scheduled_at  TEXT,                      -- ISO WIB, null kalau draft
    created_at    TEXT NOT NULL,
    posted_at     TEXT,
    error         TEXT,
    results_json  TEXT,                      -- JSON hasil post per part
    FOREIGN KEY (handle) REFERENCES accounts(handle) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_posts_status   ON posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_sched    ON posts(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_posts_handle   ON posts(handle);

-- Media (gambar) per post-part. part_index = urutan di chain (0-based).
CREATE TABLE IF NOT EXISTS media (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     TEXT NOT NULL,
    part_index  INTEGER NOT NULL DEFAULT 0,
    r2_key      TEXT NOT NULL,               -- key di bucket R2 (threads/...)
    public_url  TEXT NOT NULL,               -- URL publik yg dipost ke Threads
    filename    TEXT,
    size_bytes  INTEGER,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_media_post ON media(post_id);

-- Media library: gambar reusable (nggak harus keiket ke 1 post)
CREATE TABLE IF NOT EXISTS media_library (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    r2_key      TEXT NOT NULL UNIQUE,
    public_url  TEXT NOT NULL,
    filename    TEXT,
    size_bytes  INTEGER,
    uploaded_at TEXT NOT NULL
);
