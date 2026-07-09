"""Subreddit directory population.

Layers:
  seed   - paginate /subreddits/{popular,new,default} (~3K subs, ~1 min)
  prefix - sweep /subreddits/search across a-z0-9 single chars (~30-60K, ~30-40 min at 100 QPM)
  deep   - two-character pairs on top of prefix (1,296 queries; several hours)
  import - Arctic Shift bulk dump via scripts/import_arctic_shift.py (millions)
  organic- every listing/search response upserts what it saw (automatic)
"""
import asyncio
import itertools
import string
import time

from . import db
from .reddit import client as reddit

_state = {
    "running": False,
    "mode": None,
    "started": None,
    "finished": None,
    "queries_done": 0,
    "queries_total": 0,
    "upserted": 0,
    "error": None,
}
_task: asyncio.Task | None = None

# Stay comfortably under the 100 QPM script-app budget so browsing still works.
CRAWL_DELAY = 1.0  # seconds between crawl requests (~60 QPM for the crawler)

CHARS = string.ascii_lowercase + string.digits


def status() -> dict:
    s = dict(_state)
    s["directory"] = db.directory_stats()
    return s


async def _paginate_subreddit_listing(which: str):
    after = None
    while True:
        data = await reddit.subreddit_listing(which, after, 100)
        rows = data["rows"]
        db.upsert_subreddits(rows, source="seed")
        _state["upserted"] += len(rows)
        _state["queries_done"] += 1
        after = data["after"]
        if not after or not rows:
            break
        await asyncio.sleep(CRAWL_DELAY)


async def _prefix_sweep(queries: list[str]):
    for q in queries:
        after = None
        while True:
            data = await reddit.search_subreddits(q, after, 100, include_nsfw=True)
            # search_subreddits already upserts as 'organic'; re-tag count only
            _state["upserted"] += len(data["subreddits"])
            after = data["after"]
            _state["queries_done"] += 1
            if not after or not data["subreddits"]:
                break
            await asyncio.sleep(CRAWL_DELAY)
        await asyncio.sleep(CRAWL_DELAY)


async def _run(mode: str):
    _state.update(running=True, mode=mode, started=time.time(), finished=None,
                  queries_done=0, upserted=0, error=None)
    try:
        if mode in ("seed", "full"):
            _state["queries_total"] = 30  # ~10 pages per listing
            for which in ("popular", "new", "default"):
                await _paginate_subreddit_listing(which)
        if mode in ("prefix", "full"):
            queries = list(CHARS)
            _state["queries_total"] = _state["queries_done"] + len(queries) * 10
            await _prefix_sweep(queries)
        if mode == "deep":
            queries = ["".join(p) for p in itertools.product(CHARS, repeat=2)]
            _state["queries_total"] = len(queries) * 3
            await _prefix_sweep(queries)
    except Exception as e:  # surface, don't crash the app
        _state["error"] = str(e)
    finally:
        _state["running"] = False
        _state["finished"] = time.time()


def start(mode: str) -> dict:
    global _task
    if _state["running"]:
        return {"ok": False, "reason": "crawl already running", **status()}
    if mode not in ("seed", "prefix", "deep", "full"):
        return {"ok": False, "reason": f"unknown mode {mode}"}
    _task = asyncio.get_event_loop().create_task(_run(mode))
    return {"ok": True, **status()}
