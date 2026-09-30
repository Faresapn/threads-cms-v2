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
def new_post(handle, text, scheduled_at=None):
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
        """INSERT INTO posts(id,handle,text,status,scheduled_at,created_at)
           VALUES(?,?,?,?,?,?)""",
        (pid, handle, text, status, sched, now_iso()),
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


if __name__ == "__main__":
    init_db()
    print(f"DB ready: {DB_PATH}")
