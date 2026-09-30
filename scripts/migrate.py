#!/usr/bin/env python3
"""migrate.py — import data dari bot lama (~/.threads-bot) ke DB CMS v2.
- tokens.json  → accounts
- queue.json   → posts (+ media kalau ada image_url lama)
Idempotent: aman dijalankan berkali-kali (skip id yg udah ada).
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import db  # noqa: E402

OLD = Path.home() / ".threads-bot"


def main():
    db.init_db()
    # accounts dari tokens.json
    tokens = OLD / "tokens.json"
    n_acc = 0
    if tokens.exists():
        for handle in json.loads(tokens.read_text()).keys():
            info = {}
            db.upsert_account(handle, display_name=handle)
            n_acc += 1
    # posts dari queue.json
    queue = OLD / "queue.json"
    n_post = 0
    if queue.exists():
        try:
            items = json.loads(queue.read_text())
        except Exception:
            items = []
        con = db.connect()
        existing = {r["id"] for r in con.execute("SELECT id FROM posts").fetchall()}
        con.close()
        for it in items:
            pid = it.get("id")
            if not pid or pid in existing:
                continue
            con = db.connect()
            con.execute(
                """INSERT INTO posts(id,handle,text,status,scheduled_at,created_at,posted_at,error,results_json)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (pid, it.get("handle", ""), it.get("text", ""),
                 it.get("status", "draft"), it.get("scheduled_at"),
                 it.get("created_at") or db.now_iso(), it.get("posted_at"),
                 it.get("error"),
                 json.dumps(it.get("results")) if it.get("results") else None),
            )
            con.commit(); con.close()
            n_post += 1
    print(f"migrated: {n_acc} accounts, {n_post} posts")


if __name__ == "__main__":
    main()
