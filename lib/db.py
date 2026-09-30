#!/usr/bin/env python3
"""db.py — helper SQLite buat Threads CMS v2."""
import sqlite3, json, uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "db" / "cms.db"
SCHEMA = BASE / "db" / "schema.sql"
WIB = timezone(timedelta(hours=7))


def now_iso():
    return datetime.now(WIB).isoformat()


def connect():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    con = connect()
    con.executescript(SCHEMA.read_text())
    v2 = BASE / "db" / "schema_v2.sql"
    if v2.exists():
        con.executescript(v2.read_text())
    v3 = BASE / "db" / "schema_v3.sql"
    if v3.exists():
        con.executescript(v3.read_text())
    # migrasi kolom soft-sell (idempotent)
    cols = {r["name"] for r in con.execute("PRAGMA table_info(posts)").fetchall()}
    if "softsell_link" not in cols:
        con.execute("ALTER TABLE posts ADD COLUMN softsell_link TEXT")
    if "softsell_text" not in cols:
        con.execute("ALTER TABLE posts ADD COLUMN softsell_text TEXT")
    if "softsell_result" not in cols:
        con.execute("ALTER TABLE posts ADD COLUMN softsell_result TEXT")
    if "source" not in cols:
        con.execute("ALTER TABLE posts ADD COLUMN source TEXT DEFAULT 'manual'")
    con.commit()
    con.close()


# ── accounts ────────────────────────────────────────────────────────────
def upsert_account(handle, display_name=None, user_id=None):
    con = connect()
    con.execute(
        """INSERT INTO accounts(handle, display_name, user_id, added_at)
           VALUES(?,?,?,?)
           ON CONFLICT(handle) DO UPDATE SET
             display_name=COALESCE(excluded.display_name, accounts.display_name),
             user_id=COALESCE(excluded.user_id, accounts.user_id)""",
        (handle, display_name, user_id, now_iso()),
    )
    con.commit(); con.close()


def list_accounts():
    con = connect()
    rows = con.execute("SELECT * FROM accounts ORDER BY handle").fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── posts ───────────────────────────────────────────────────────────────
def new_post(handle, text, scheduled_at=None, softsell_link=None, softsell_text=None,
             source="manual"):
    pid = "q_" + uuid.uuid4().hex[:8]
    status = "draft"
    sched = None
    if scheduled_at:
        dt = datetime.fromisoformat(scheduled_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=WIB)
        sched = dt.isoformat()
        status = "scheduled"
    con = connect()
    con.execute(
        """INSERT INTO posts(id,handle,text,status,scheduled_at,created_at,softsell_link,softsell_text,source)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (pid, handle, text, status, sched, now_iso(),
         softsell_link or None, softsell_text or None, source),
    )
    con.commit(); con.close()
    return pid


def get_post(pid):
    con = connect()
    row = con.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    if not row:
        con.close(); return None
    post = dict(row)
    media = con.execute(
        "SELECT * FROM media WHERE post_id=? ORDER BY part_index", (pid,)
    ).fetchall()
    con.close()
    post["media"] = [dict(m) for m in media]
    post["results"] = json.loads(post["results_json"]) if post["results_json"] else []
    return post


def list_posts(status=None, handle=None, limit=200):
    con = connect()
    q = "SELECT * FROM posts WHERE 1=1"
    args = []
    if status:
        q += " AND status=?"; args.append(status)
    if handle:
        q += " AND handle=?"; args.append(handle)
    q += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
    rows = con.execute(q, args).fetchall()
    posts = []
    for r in rows:
        p = dict(r)
        m = con.execute(
            "SELECT * FROM media WHERE post_id=? ORDER BY part_index", (p["id"],)
        ).fetchall()
        p["media"] = [dict(x) for x in m]
        posts.append(p)
    con.close()
    return posts


def update_post(pid, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    con = connect()
    con.execute(f"UPDATE posts SET {cols} WHERE id=?", (*fields.values(), pid))
    con.commit(); con.close()


def set_result(pid, status, results=None, error=None, posted_at=None):
    update_post(
        pid,
        status=status,
        results_json=json.dumps(results, ensure_ascii=False) if results else None,
        error=error,
        posted_at=posted_at,
    )


def set_softsell_result(pid, result):
    update_post(pid, softsell_result=json.dumps(result, ensure_ascii=False))


def delete_post(pid):
    con = connect()
    con.execute("DELETE FROM posts WHERE id=?", (pid,))
    con.commit(); con.close()


def due_posts(now=None):
    """Post scheduled yg udah waktunya."""
    now = now or datetime.now(WIB)
    con = connect()
    rows = con.execute(
        "SELECT * FROM posts WHERE status='scheduled' AND scheduled_at IS NOT NULL"
    ).fetchall()
    con.close()
    due = []
    for r in rows:
        try:
            when = datetime.fromisoformat(r["scheduled_at"])
            if when.tzinfo is None:
                when = when.replace(tzinfo=WIB)
            if when <= now:
                due.append(dict(r))
        except Exception:
            continue
    return due


# ── media ───────────────────────────────────────────────────────────────
def add_media(post_id, part_index, r2_key, public_url, filename=None, size=None):
    con = connect()
    con.execute(
        """INSERT INTO media(post_id,part_index,r2_key,public_url,filename,size_bytes,uploaded_at)
           VALUES(?,?,?,?,?,?,?)""",
        (post_id, part_index, r2_key, public_url, filename, size, now_iso()),
    )
    con.commit(); con.close()


def get_media_urls(post_id, num_parts):
    """Return list URL per part_index (None kalau part itu text-only)."""
    con = connect()
    rows = con.execute(
        "SELECT part_index, public_url FROM media WHERE post_id=?", (post_id,)
    ).fetchall()
    con.close()
    urls = [None] * num_parts
    for r in rows:
        idx = r["part_index"]
        if 0 <= idx < num_parts:
            urls[idx] = r["public_url"]
    return urls


def clear_media(post_id):
    con = connect()
    con.execute("DELETE FROM media WHERE post_id=?", (post_id,))
    con.commit(); con.close()


def add_library(r2_key, public_url, filename=None, size=None):
    con = connect()
    con.execute(
        """INSERT OR IGNORE INTO media_library(r2_key,public_url,filename,size_bytes,uploaded_at)
           VALUES(?,?,?,?,?)""",
        (r2_key, public_url, filename, size, now_iso()),
    )
    con.commit(); con.close()


def list_library(limit=100):
    con = connect()
    rows = con.execute(
        "SELECT * FROM media_library ORDER BY uploaded_at DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── personas ────────────────────────────────────────────────────────────
def list_personas(handle=None):
    con = connect()
    if handle:
        rows = con.execute(
            "SELECT * FROM personas WHERE handle=? ORDER BY is_default DESC, name",
            (handle,)).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM personas ORDER BY handle, is_default DESC, name").fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["reference_urls"] = json.loads(d["reference_urls"]) if d["reference_urls"] else []
        d["sample_posts"] = json.loads(d["sample_posts"]) if d["sample_posts"] else []
        out.append(d)
    return out


def get_persona(pid):
    con = connect()
    r = con.execute("SELECT * FROM personas WHERE id=?", (pid,)).fetchone()
    con.close()
    if not r:
        return None
    d = dict(r)
    d["reference_urls"] = json.loads(d["reference_urls"]) if d["reference_urls"] else []
    d["sample_posts"] = json.loads(d["sample_posts"]) if d["sample_posts"] else []
    return d


def save_persona(handle, name, description=None, system_prompt=None, lang="id",
                 reference_urls=None, learned_style=None, sample_posts=None,
                 is_default=0, pid=None):
    con = connect()
    ref = json.dumps(reference_urls or [], ensure_ascii=False)
    samp = json.dumps(sample_posts or [], ensure_ascii=False)
    if pid:
        con.execute(
            """UPDATE personas SET handle=?,name=?,description=?,system_prompt=?,
               lang=?,reference_urls=?,learned_style=COALESCE(?,learned_style),
               sample_posts=?,is_default=?,updated_at=? WHERE id=?""",
            (handle, name, description, system_prompt, lang, ref, learned_style,
             samp, is_default, now_iso(), pid))
        out_id = pid
    else:
        cur = con.execute(
            """INSERT INTO personas(handle,name,description,system_prompt,lang,
               reference_urls,learned_style,sample_posts,is_default,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (handle, name, description, system_prompt, lang, ref, learned_style,
             samp, is_default, now_iso()))
        out_id = cur.lastrowid
    if is_default:  # unset default lain di akun sama
        con.execute("UPDATE personas SET is_default=0 WHERE handle=? AND id!=?",
                    (handle, out_id))
    con.commit(); con.close()
    return out_id


def update_persona_style(pid, learned_style):
    con = connect()
    con.execute("UPDATE personas SET learned_style=?, updated_at=? WHERE id=?",
                (learned_style, now_iso(), pid))
    con.commit(); con.close()


def delete_persona(pid):
    con = connect()
    con.execute("DELETE FROM personas WHERE id=?", (pid,))
    con.commit(); con.close()


# ── autopost config ─────────────────────────────────────────────────────
DEFAULT_HOURS = [8, 12, 18, 21]   # jam terbaik default (WIB)

# Style guide built-in dari 3 referensi yg Branko kasih (hook + value + soft CTA).
DEFAULT_STYLE_GUIDE = (
    "Gaya utas edukasi Threads yg nge-hook:\n"
    "- Buka dgn hook penasaran/kontroversi: 'Jujur agak kesel liat...', "
    "'Eh tau nggak sih...', 'LIST KESALAHAN...', 'Baru ngonten di Threads? Ini...'\n"
    "- Bongkar realita yg orang lain skip. Kasih value konkret: tools, cara benerin, "
    "list actionable, angka nyata.\n"
    "- Bahasa ngobrol, personal, kayak cerita ke temen. Bukan formal/korporat.\n"
    "- Pakai bullet/list biar gampang dibaca. Kalimat pendek.\n"
    "- Tutup dgn soft CTA: 'Save biar gak ilang', 'Pilih salah satu', "
    "'cek di komen', tanya yg mancing komentar.\n"
    "- JANGAN em-dash. JANGAN sok pintar. Relatable + berbobot."
)


def get_autopost(handle):
    con = connect()
    r = con.execute("SELECT * FROM autopost_config WHERE handle=?", (handle,)).fetchone()
    con.close()
    if not r:
        return {"handle": handle, "enabled": 0, "lang": "id", "niches": [],
                "posts_per_day": 3, "best_hours": DEFAULT_HOURS, "persona_id": None,
                "num_parts_min": 1, "num_parts_max": 3, "last_scheduled": None,
                "style_urls": [], "style_guide": DEFAULT_STYLE_GUIDE}
    d = dict(r)
    d["niches"] = json.loads(d["niches"]) if d["niches"] else []
    d["best_hours"] = json.loads(d["best_hours"]) if d["best_hours"] else DEFAULT_HOURS
    d["style_urls"] = json.loads(d["style_urls"]) if d.get("style_urls") else []
    d["style_guide"] = d.get("style_guide") or DEFAULT_STYLE_GUIDE
    return d


def save_autopost(handle, enabled=None, lang=None, niches=None, posts_per_day=None,
                  best_hours=None, persona_id=None, num_parts_min=None,
                  num_parts_max=None, style_urls=None, style_guide=None):
    cur = get_autopost(handle)
    con = connect()
    con.execute(
        """INSERT INTO autopost_config(handle,enabled,lang,niches,posts_per_day,
           best_hours,persona_id,num_parts_min,num_parts_max,style_urls,style_guide,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(handle) DO UPDATE SET
             enabled=excluded.enabled, lang=excluded.lang, niches=excluded.niches,
             posts_per_day=excluded.posts_per_day, best_hours=excluded.best_hours,
             persona_id=excluded.persona_id, num_parts_min=excluded.num_parts_min,
             num_parts_max=excluded.num_parts_max, style_urls=excluded.style_urls,
             style_guide=excluded.style_guide, updated_at=excluded.updated_at""",
        (handle,
         cur["enabled"] if enabled is None else int(enabled),
         cur["lang"] if lang is None else lang,
         json.dumps(cur["niches"] if niches is None else niches, ensure_ascii=False),
         cur["posts_per_day"] if posts_per_day is None else int(posts_per_day),
         json.dumps(cur["best_hours"] if best_hours is None else best_hours),
         cur["persona_id"] if persona_id is None else persona_id,
         cur["num_parts_min"] if num_parts_min is None else int(num_parts_min),
         cur["num_parts_max"] if num_parts_max is None else int(num_parts_max),
         json.dumps(cur["style_urls"] if style_urls is None else style_urls, ensure_ascii=False),
         cur["style_guide"] if style_guide is None else style_guide,
         now_iso()))
    con.commit(); con.close()


def mark_autopost_scheduled(handle, date_str):
    con = connect()
    con.execute("UPDATE autopost_config SET last_scheduled=? WHERE handle=?",
                (date_str, handle))
    con.commit(); con.close()


def list_enabled_autopost():
    con = connect()
    rows = con.execute("SELECT handle FROM autopost_config WHERE enabled=1").fetchall()
    con.close()
    return [r["handle"] for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"DB ready: {DB_PATH}")
