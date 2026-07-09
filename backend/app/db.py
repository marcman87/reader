import os
import sqlite3
import threading

from .config import DB_PATH

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS subreddits (
    name TEXT PRIMARY KEY COLLATE NOCASE,
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    subscribers INTEGER DEFAULT 0,
    over18 INTEGER DEFAULT 0,
    icon TEXT DEFAULT '',
    source TEXT DEFAULT 'organic',   -- seed | prefix | import | organic
    created_utc REAL DEFAULT 0,
    last_seen REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sub_subscribers ON subreddits(subscribers DESC);
CREATE INDEX IF NOT EXISTS idx_sub_over18 ON subreddits(over18);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _local.conn = conn
    return conn


def upsert_subreddits(rows: list[dict], source: str):
    """rows: dicts with at least 'name'; optional title/description/subscribers/over18/icon/created_utc."""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        """
        INSERT INTO subreddits (name, title, description, subscribers, over18, icon, source, created_utc, last_seen)
        VALUES (:name, :title, :description, :subscribers, :over18, :icon, :source, :created_utc, strftime('%s','now'))
        ON CONFLICT(name) DO UPDATE SET
            title = CASE WHEN excluded.title != '' THEN excluded.title ELSE subreddits.title END,
            description = CASE WHEN excluded.description != '' THEN excluded.description ELSE subreddits.description END,
            subscribers = CASE WHEN excluded.subscribers > 0 THEN excluded.subscribers ELSE subreddits.subscribers END,
            over18 = MAX(subreddits.over18, excluded.over18),
            icon = CASE WHEN excluded.icon != '' THEN excluded.icon ELSE subreddits.icon END,
            created_utc = CASE WHEN excluded.created_utc > 0 THEN excluded.created_utc ELSE subreddits.created_utc END,
            last_seen = excluded.last_seen
        """,
        [
            {
                "name": r["name"],
                "title": r.get("title") or "",
                "description": r.get("description") or "",
                "subscribers": int(r.get("subscribers") or 0),
                "over18": 1 if r.get("over18") else 0,
                "icon": r.get("icon") or "",
                "source": source,
                "created_utc": float(r.get("created_utc") or 0),
            }
            for r in rows
            if r.get("name")
        ],
    )
    conn.commit()


def search_directory(q: str, nsfw: str, limit: int, offset: int) -> tuple[list[dict], int]:
    conn = get_conn()
    where = []
    params: list = []
    if q:
        where.append("(name LIKE ? OR title LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if nsfw == "sfw":
        where.append("over18 = 0")
    elif nsfw == "nsfw":
        where.append("over18 = 1")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) c FROM subreddits {clause}", params).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT name, title, description, subscribers, over18, icon, source
            FROM subreddits {clause}
            ORDER BY subscribers DESC, name ASC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows], total


def directory_stats() -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) total, SUM(over18) nsfw FROM subreddits"
    ).fetchone()
    by_source = {
        r["source"]: r["c"]
        for r in conn.execute("SELECT source, COUNT(*) c FROM subreddits GROUP BY source")
    }
    return {"total": row["total"], "nsfw": row["nsfw"] or 0, "by_source": by_source}
