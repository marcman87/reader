#!/usr/bin/env python3
"""Import an Arctic Shift subreddit dump into the directory.

Arctic Shift (github.com/ArthurHeitmann/arctic_shift) publishes periodic dumps
of all known subreddits as newline-delimited JSON, usually zstd-compressed
(.jsonl.zst / .ndjson.zst). Download the latest 'subreddits' dump from their
releases / download-links page, then:

    docker compose exec reader python scripts/import_arctic_shift.py /data/subreddits.jsonl.zst

or, if the file is on the host, copy it into the ./data volume first.
Handles .zst, .gz, and plain .jsonl/.ndjson. Millions of rows import in a few
minutes; existing rows are enriched, not overwritten with blanks.
"""
import gzip
import io
import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, ".")

from app import db  # noqa: E402

BATCH = 5000


def open_stream(path: str):
    if path.endswith(".zst"):
        import zstandard
        fh = open(path, "rb")
        return io.TextIOWrapper(
            zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(fh),
            encoding="utf-8", errors="replace",
        )
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def main(path: str):
    total, batch = 0, []
    with open_stream(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = d.get("display_name") or d.get("name")
            if not name or name.startswith(("u_", "u/")):
                continue  # skip user profiles
            batch.append({
                "name": name,
                "title": d.get("title") or "",
                "description": d.get("public_description") or d.get("description") or "",
                "subscribers": d.get("subscribers") or 0,
                "over18": d.get("over18") or d.get("over_18") or False,
                "icon": d.get("icon_img") or "",
                "created_utc": d.get("created_utc") or 0,
            })
            if len(batch) >= BATCH:
                db.upsert_subreddits(batch, source="import")
                total += len(batch)
                batch = []
                if total % 100000 == 0:
                    print(f"  {total:,} imported...")
    if batch:
        db.upsert_subreddits(batch, source="import")
        total += len(batch)
    print(f"Done. {total:,} subreddits imported/updated.")
    print(db.directory_stats())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
