-- Threads CMS v2 — schema tambahan v2.1 (personas + AI)
-- Jalankan di atas schema.sql yg udah ada. Idempotent.

-- Persona per akun: gaya nulis + contoh + link referensi
CREATE TABLE IF NOT EXISTS personas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    handle         TEXT NOT NULL,              -- akun yg pakai persona ini
    name           TEXT NOT NULL,              -- nama persona (mis "Visioner EN")
    description    TEXT,                        -- ringkasan gaya (buat kamu inget)
    system_prompt  TEXT,                        -- instruksi gaya buat AI
    lang           TEXT DEFAULT 'id',           -- id | en
    reference_urls TEXT,                        -- JSON list URL Threads yg dipelajari
    learned_style  TEXT,                        -- hasil analisis gaya (auto dari link)
    sample_posts   TEXT,                        -- JSON list contoh post (few-shot)
    is_default     INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_persona_handle ON personas(handle);
