"""4chan read-only JSON API client (a.4cdn.org). Hard 1 req/sec throttle per API rules."""
import asyncio
import time
from urllib.parse import quote

import httpx

API = "https://a.4cdn.org"
MEDIA = "https://i.4cdn.org"


def _prox(url: str) -> str:
    return f"/api/proxy?url={quote(url, safe='')}"


class FourChanClient:
    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30)
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._boards_cache: tuple[float, list] | None = None

    async def _get(self, path: str):
        async with self._lock:
            wait = 1.0 - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
        resp = await self._http.get(f"{API}{path}", headers={"User-Agent": "reader-selfhosted/1.0"})
        resp.raise_for_status()
        return resp.json()

    async def boards(self) -> list[dict]:
        if self._boards_cache and time.time() - self._boards_cache[0] < 3600:
            return self._boards_cache[1]
        data = await self._get("/boards.json")
        boards = [
            {
                "board": b["board"],
                "title": b["title"],
                "description": b.get("meta_description", ""),
                "worksafe": bool(b.get("ws_board")),
                "per_page": b.get("per_page"),
                "pages": b.get("pages"),
            }
            for b in data.get("boards", [])
        ]
        self._boards_cache = (time.time(), boards)
        return boards

    def _norm_post(self, board: str, p: dict) -> dict:
        media = None
        if p.get("tim") and p.get("ext"):
            full = f"{MEDIA}/{board}/{p['tim']}{p['ext']}"
            thumb = f"{MEDIA}/{board}/{p['tim']}s.jpg"
            kind = "video" if p["ext"] in (".webm", ".mp4") else "image"
            media = {
                "kind": kind,
                "url": _prox(full),
                "thumb": _prox(thumb),
                "filename": f"{p.get('filename','')}{p['ext']}",
                "w": p.get("w"), "h": p.get("h"),
                "size": p.get("fsize"),
            }
        return {
            "no": p.get("no"),
            "resto": p.get("resto", 0),
            "name": p.get("name", "Anonymous"),
            "trip": p.get("trip"),
            "sub": p.get("sub"),
            "com": p.get("com", ""),  # HTML
            "time": p.get("time"),
            "replies": p.get("replies"),
            "images": p.get("images"),
            "sticky": bool(p.get("sticky")),
            "closed": bool(p.get("closed")),
            "media": media,
        }

    async def catalog(self, board: str, q: str | None = None) -> list[dict]:
        pages = await self._get(f"/{board}/catalog.json")
        threads = []
        for page in pages:
            for t in page.get("threads", []):
                threads.append(self._norm_post(board, t))
        if q:
            ql = q.lower()
            threads = [
                t for t in threads
                if ql in (t.get("sub") or "").lower() or ql in (t.get("com") or "").lower()
            ]
        return threads

    async def thread(self, board: str, no: int) -> list[dict]:
        data = await self._get(f"/{board}/thread/{no}.json")
        return [self._norm_post(board, p) for p in data.get("posts", [])]


client = FourChanClient()
