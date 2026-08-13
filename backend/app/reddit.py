"""Reddit public Atom feed (.rss) client — no API credentials.

Reddit declined the Data API application, so this reads the public Atom feeds
on www.reddit.com instead. Feeds are unauthenticated and IP rate-limited
(observed ~10 req/min with burst penalties), hence the global throttle and
response cache. Feeds carry no scores, comment counts, per-post NSFW flags,
or media metadata — those fields are None/best-effort:
  - score / num_comments        -> None
  - over_18                     -> subreddit-level lookup in the local directory
  - selftext / comment bodies   -> reddit-rendered HTML (selftext_html / body_html)
  - galleries                   -> plain links (items not enumerable via RSS)
  - v.redd.it video             -> still works: DASH manifests need no auth
"""
import asyncio
import html
import re
import time
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx

from . import config, db

BASE = "https://www.reddit.com"
NS = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}

THROTTLE = 30.0     # seconds between upstream requests (global; AWS IPs get ~2 req/min)
CACHE_TTL = 300.0   # seconds a fetched feed stays fresh (stale copies serve instantly + refresh)
COOLDOWN = 60.0     # seconds to back off after a 429
MAX_QUEUE_WAIT = 60.0  # fail fast instead of queuing past proxy timeouts

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp")
VIDEO_EXT = (".mp4", ".webm")

_MD_BLOCK = re.compile(r"<!--\s*SC_OFF\s*-->(.*?)<!--\s*SC_ON\s*-->", re.S)
_LINK_ANCHOR = re.compile(r'<a href="([^"]+)">\s*\[link\]\s*</a>')
_TAG = re.compile(r"<[^>]+>")


class RedditError(Exception):
    pass


def _prox(url: str | None) -> str | None:
    return f"/api/proxy?url={quote(url, safe='')}" if url else None


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


def _strip_tags(s: str) -> str:
    return html.unescape(_TAG.sub("", s)).strip()


class RedditClient:
    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30, follow_redirects=True)
        self._lock = asyncio.Lock()
        self._last_req = 0.0
        self._cooldown_until = 0.0
        self._cache: dict[str, tuple[float, ET.Element]] = {}
        self._refreshing: set[str] = set()
        self._waiters = 0
        # feed-level subreddit metadata harvested from listing fetches
        self._about_cache: dict[str, dict] = {}

    async def _fetch(self, path: str, params: dict | None = None) -> ET.Element:
        qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in (params or {}).items() if v is not None)
        url = f"{BASE}{path}" + (f"?{qs}" if qs else "")

        cached = self._cache.get(url)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            return cached[1]
        if cached:
            # stale-while-revalidate: answer now, refresh in the background —
            # but only when nothing else is waiting for the rate budget
            if (url not in self._refreshing and self._waiters == 0
                    and time.monotonic() >= self._cooldown_until):
                self._refreshing.add(url)
                asyncio.create_task(self._background_refresh(url))
            return cached[1]

        if time.monotonic() < self._cooldown_until:
            raise RedditError(
                "Backing off after a Reddit rate limit (429) — retry in a minute."
            )
        return await self._fetch_fresh(url)

    async def _background_refresh(self, url: str):
        try:
            await self._fetch_fresh(url)
        except Exception:
            pass  # stale copy stays; next visitor triggers another attempt
        finally:
            self._refreshing.discard(url)

    async def _fetch_fresh(self, url: str) -> ET.Element:
        if self._waiters * THROTTLE > MAX_QUEUE_WAIT:
            raise RedditError(
                "Feed queue is full (Reddit allows this server ~2 requests/min) — retry shortly."
            )
        self._waiters += 1
        try:
            async with self._lock:
                wait = THROTTLE - (time.monotonic() - self._last_req)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_req = time.monotonic()
        finally:
            self._waiters -= 1

        resp = await self._http.get(url, headers={"User-Agent": config.USER_AGENT})
        if resp.status_code == 429:
            self._cooldown_until = time.monotonic() + COOLDOWN
            raise RedditError(
                "Reddit rate limit hit (429). RSS feeds are throttled per IP — wait a minute and retry."
            )
        if resp.status_code >= 400:
            raise RedditError(f"Reddit {resp.status_code} on {url.removeprefix(BASE)}")
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            raise RedditError(f"Bad feed XML from {url.removeprefix(BASE)}: {e}") from e

        # cap cache size; oldest entries are cheapest to lose
        if len(self._cache) > 200:
            for k in sorted(self._cache, key=lambda k: self._cache[k][0])[:50]:
                del self._cache[k]
        self._cache[url] = (time.monotonic(), root)
        return root

    # ---------- parsing ----------

    @staticmethod
    def _entry_text(entry: ET.Element, tag: str) -> str:
        el = entry.find(f"atom:{tag}", NS)
        return (el.text or "") if el is not None else ""

    def _parse_post(self, entry: ET.Element) -> dict:
        raw_id = self._entry_text(entry, "id")             # t3_xxx
        pid = raw_id.split("_", 1)[-1]
        author_el = entry.find("atom:author/atom:name", NS)
        author = (author_el.text or "").removeprefix("/u/") if author_el is not None else "[deleted]"
        cat = entry.find("atom:category", NS)
        subreddit = cat.get("term") if cat is not None else None
        link = entry.find("atom:link", NS)
        permalink_abs = link.get("href") if link is not None else ""
        permalink = permalink_abs.replace(BASE, "") or None
        if not subreddit and permalink:
            pm = re.match(r"/r/([^/]+)/", permalink)
            subreddit = pm.group(1) if pm else None
        content = self._entry_text(entry, "content")
        created = _epoch(self._entry_text(entry, "published") or self._entry_text(entry, "updated"))

        # self-post body (reddit-rendered HTML between SC_OFF/SC_ON markers)
        m = _MD_BLOCK.search(content)
        selftext_html = m.group(1).strip() if m else ""

        # external target: the [link] anchor; equals the permalink for self posts
        url = permalink_abs
        lm = _LINK_ANCHOR.search(content)
        if lm:
            url = html.unescape(lm.group(1))
        is_self = url.rstrip("/") == permalink_abs.rstrip("/")

        thumb_el = entry.find("media:thumbnail", NS)
        thumb = _prox(thumb_el.get("url")) if thumb_el is not None else None

        media: dict = {"kind": "self"} if is_self else {"kind": "link"}
        bare = url.split("?")[0].lower()
        if not is_self:
            if "v.redd.it/" in url:
                vid = url.split("v.redd.it/")[1].split("/")[0].split("?")[0]
                media = {
                    "kind": "video",
                    "video_id": vid,
                    "dash": f"/api/vreddit/{vid}/DASHPlaylist.mpd" if vid.isalnum() else None,
                    "fallback": None,
                    "is_gif": False,
                }
            elif bare.endswith(IMAGE_EXT):
                media = {"kind": "image", "url": _prox(url)}
            elif bare.endswith(VIDEO_EXT):
                media = {"kind": "rawvideo", "url": _prox(url)}

        domain = ""
        if not is_self and "://" in url:
            domain = url.split("://", 1)[1].split("/", 1)[0].removeprefix("www.")

        return {
            "id": pid,
            "subreddit": subreddit,
            "title": html.unescape(self._entry_text(entry, "title")),
            "author": author,
            "score": None,             # not exposed via RSS
            "num_comments": None,      # not exposed via RSS
            "created_utc": created,
            "over_18": False,          # filled from directory lookup by caller
            "spoiler": False,
            "stickied": False,
            "selftext": "",
            "selftext_html": selftext_html,
            "url": None if is_self else url,
            "permalink": permalink,
            "link_flair_text": None,
            "domain": domain or None,
            "thumb": thumb,
            "media": media,
        }

    def _harvest_feed_about(self, root: ET.Element):
        """Listing feeds carry the sub's title/description/logo — keep them for about()."""
        cat = root.find("atom:category", NS)
        name = cat.get("term") if cat is not None else None
        if not name:
            return
        logo = root.find("atom:logo", NS)
        self._about_cache[name.lower()] = {
            "name": name,
            "title": (root.findtext("atom:title", "", NS) or name),
            "description": root.findtext("atom:subtitle", "", NS) or "",
            "icon": (logo.text or "") if logo is not None else "",
        }

    def _fill_nsfw_and_index(self, posts: list[dict]):
        """Set over_18 from the local directory (subreddit-level) and organically index names."""
        names = sorted({p["subreddit"] for p in posts if p["subreddit"]})
        known = db.over18_lookup(names)
        for p in posts:
            sub = (p["subreddit"] or "").lower()
            p["over_18"] = bool(known.get(sub))
        try:
            db.upsert_subreddits([{"name": n} for n in names], source="organic")
        except Exception:
            pass  # indexing must never break a read

    @staticmethod
    def _apply_nsfw(posts: list[dict], nsfw: str) -> list[dict]:
        # Subreddit-level only: RSS has no per-post flag. Unknown subs count as SFW.
        if nsfw == "sfw":
            return [p for p in posts if not p["over_18"]]
        if nsfw == "nsfw":
            return [p for p in posts if p["over_18"]]
        return posts

    def _posts_page(self, root: ET.Element, nsfw: str, limit: int) -> dict:
        entries = root.findall("atom:entry", NS)
        # search feeds prepend community (t5_) matches — posts are t3_ only
        t3 = [e for e in entries if (e.findtext("atom:id", "", NS)).startswith("t3_")]
        posts = [self._parse_post(e) for e in t3]
        posts = [p for p in posts if p["id"]]
        self._fill_nsfw_and_index(posts)
        # 'after' continues from the last post entry regardless of nsfw filtering
        after = None
        if t3 and len(entries) >= limit:
            after = t3[-1].findtext("atom:id", "", NS) or None
        return {"posts": self._apply_nsfw(posts, nsfw), "after": after}

    # ---------- endpoints ----------

    async def listing(self, subreddit: str | None, sort: str, t: str, after: str | None,
                      limit: int, nsfw: str) -> dict:
        sort = "hot" if sort == "best" else sort  # 'best' needs a logged-in session
        base = f"/r/{subreddit}" if subreddit else "/r/all"
        params = {"limit": limit}
        if sort == "top":
            params["t"] = t
        if after:
            params["after"] = after
        root = await self._fetch(f"{base}/{sort}.rss", params)
        self._harvest_feed_about(root)
        return self._posts_page(root, nsfw, limit)

    async def subreddit_about(self, name: str) -> dict:
        """Directory DB + feed-harvested cache first — an upstream fetch only for
        subs the directory has never heard of (rate budget is precious)."""
        key = name.lower()
        about = self._about_cache.get(key)
        stored = db.get_subreddit(name)
        if not about and not stored:
            root = await self._fetch(f"/r/{name}/hot.rss", {"limit": 1})
            self._harvest_feed_about(root)
            about = self._about_cache.get(key)
            if about:
                db.upsert_subreddits([about], source="organic")
        about = about or {}
        stored = stored or {}
        return {
            "name": about.get("name") or stored.get("name") or name,
            "title": about.get("title") or stored.get("title") or name,
            "description": about.get("description") or stored.get("description") or "",
            "icon": about.get("icon") or stored.get("icon") or "",
            "subscribers": stored.get("subscribers") or None,
            "over18": bool(stored.get("over18")),
            "created_utc": stored.get("created_utc") or None,
        }

    async def comments(self, subreddit: str, post_id: str, sort: str, comment: str | None) -> dict:
        # sort/comment ignored: one canonical URL per thread keeps the cache warm,
        # and the feed serves its own fixed order anyway
        root = await self._fetch(f"/r/{subreddit}/comments/{post_id}/.rss", {"limit": 500})
        entries = root.findall("atom:entry", NS)
        if not entries:
            raise RedditError("Thread feed came back empty")

        post = self._parse_post(entries[0])
        post["subreddit"] = post["subreddit"] or subreddit
        self._fill_nsfw_and_index([post])

        out = []
        for e in entries[1:]:
            raw_id = e.findtext("atom:id", "", NS)          # t1_xxx
            author_el = e.find("atom:author/atom:name", NS)
            author = (author_el.text or "").removeprefix("/u/") if author_el is not None else "[deleted]"
            content = e.findtext("atom:content", "", NS) or ""
            m = _MD_BLOCK.search(content)
            body_html = m.group(1).strip() if m else content
            out.append({
                "id": raw_id.split("_", 1)[-1],
                "author": author,
                "body": "",
                "body_html": body_html,
                "score": None,
                "created_utc": _epoch(e.findtext("atom:updated", "", NS)),
                "stickied": False,
                "is_submitter": bool(post["author"]) and author == post["author"],
                "distinguished": None,
                "replies": [],   # RSS is flat: no parent/child structure
            })
        return {"post": post, "comments": out}

    async def search(self, q: str, subreddit: str | None, sort: str, t: str,
                     after: str | None, nsfw: str, limit: int) -> dict:
        base = f"/r/{subreddit}/search.rss" if subreddit else "/search.rss"
        params = {"q": q, "sort": sort, "t": t, "limit": limit, "type": "link"}
        if subreddit:
            params["restrict_sr"] = "on"
        if nsfw in ("nsfw", "all"):
            params["include_over_18"] = "on"
        if after:
            params["after"] = after
        root = await self._fetch(base, params)
        return self._posts_page(root, nsfw, limit)

    def _parse_subreddit_entry(self, entry: ET.Element) -> dict | None:
        link = entry.find("atom:link", NS)
        href = link.get("href") if link is not None else ""
        m = re.search(r"/r/([^/]+)/?", href or "")
        if not m:
            return None
        content = entry.findtext("atom:content", "", NS) or ""
        icon = ""
        im = re.search(r'<img src="([^"]+)"', content)
        if im:
            icon = html.unescape(im.group(1))
        description = _strip_tags(content).replace("[link]", "").strip()
        return {
            "name": m.group(1),
            "title": html.unescape(entry.findtext("atom:title", "", NS) or ""),
            "description": description[:500],
            "subscribers": 0,                                   # not exposed via RSS
            "over18": False,
            "icon": icon,
            "created_utc": _epoch(entry.findtext("atom:updated", "", NS)) or 0,
        }

    async def _subreddits_feed(self, path: str, params: dict) -> dict:
        root = await self._fetch(path, params)
        entries = root.findall("atom:entry", NS)
        rows = [r for r in (self._parse_subreddit_entry(e) for e in entries) if r]
        # enrich over18 from what the directory already knows
        known = db.over18_lookup([r["name"] for r in rows])
        for r in rows:
            r["over18"] = bool(known.get(r["name"].lower()))
        after = None
        if entries and len(entries) >= int(params.get("limit") or 25):
            after = entries[-1].findtext("atom:id", "", NS) or None
        return {"rows": rows, "after": after}

    async def search_subreddits(self, q: str, after: str | None, limit: int,
                                include_nsfw: bool = True) -> dict:
        params = {"q": q, "limit": limit}
        if include_nsfw:
            params["include_over_18"] = "on"
        if after:
            params["after"] = after
        data = await self._subreddits_feed("/subreddits/search.rss", params)
        db.upsert_subreddits(data["rows"], source="organic")
        return {"subreddits": data["rows"], "after": data["after"]}

    async def subreddit_listing(self, which: str, after: str | None, limit: int) -> dict:
        """which: popular | new"""
        params = {"limit": limit}
        if after:
            params["after"] = after
        return await self._subreddits_feed(f"/subreddits/{which}.rss", params)


client = RedditClient()
