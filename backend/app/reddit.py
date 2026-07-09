"""Reddit OAuth (script app, password grant) client.

All requests go to oauth.reddit.com with a bearer token. Tokens last ~1h and
are re-requested on expiry. raw_json=1 everywhere to avoid HTML entities.
"""
import asyncio
import time

import httpx

from . import config, db

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"


class RedditError(Exception):
    pass


class RedditClient:
    def __init__(self):
        self._token: str | None = None
        self._token_exp: float = 0
        self._lock = asyncio.Lock()
        self._http = httpx.AsyncClient(timeout=30, follow_redirects=True)

    @property
    def configured(self) -> bool:
        return bool(config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET
                    and config.REDDIT_USERNAME and config.REDDIT_PASSWORD)

    async def _ensure_token(self):
        async with self._lock:
            if self._token and time.time() < self._token_exp - 60:
                return
            if not self.configured:
                raise RedditError(
                    "Reddit credentials missing. Set REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD in .env"
                )
            resp = await self._http.post(
                TOKEN_URL,
                auth=(config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET),
                data={
                    "grant_type": "password",
                    "username": config.REDDIT_USERNAME,
                    "password": config.REDDIT_PASSWORD,
                },
                headers={"User-Agent": config.USER_AGENT},
            )
            if resp.status_code != 200:
                raise RedditError(f"OAuth token request failed ({resp.status_code}): {resp.text[:300]}")
            data = resp.json()
            if "access_token" not in data:
                raise RedditError(f"OAuth response missing token: {data}")
            self._token = data["access_token"]
            self._token_exp = time.time() + int(data.get("expires_in", 3600))

    async def get(self, path: str, params: dict | None = None) -> dict:
        await self._ensure_token()
        params = dict(params or {})
        params.setdefault("raw_json", 1)
        resp = await self._http.get(
            f"{API}{path}",
            params=params,
            headers={"Authorization": f"bearer {self._token}", "User-Agent": config.USER_AGENT},
        )
        if resp.status_code == 401:
            self._token = None
            await self._ensure_token()
            resp = await self._http.get(
                f"{API}{path}",
                params=params,
                headers={"Authorization": f"bearer {self._token}", "User-Agent": config.USER_AGENT},
            )
        if resp.status_code == 429:
            raise RedditError("Reddit rate limit hit (429). Back off and retry.")
        if resp.status_code >= 400:
            raise RedditError(f"Reddit API {resp.status_code} on {path}: {resp.text[:300]}")
        return resp.json()

    # ---------- normalization ----------

    @staticmethod
    def normalize_post(d: dict) -> dict:
        """Flatten a t3 post into what the frontend needs, with media typed."""
        from urllib.parse import quote

        def prox(url):
            return f"/api/proxy?url={quote(url, safe='')}" if url else None

        media: dict = {"kind": "link"}
        url = d.get("url_overridden_by_dest") or d.get("url") or ""

        if d.get("is_self"):
            media = {"kind": "self"}
        elif d.get("is_gallery") and d.get("media_metadata"):
            items = []
            order = [i.get("media_id") for i in (d.get("gallery_data") or {}).get("items", [])]
            mm = d["media_metadata"]
            for mid in order or list(mm.keys()):
                m = mm.get(mid) or {}
                s = m.get("s") or {}
                u = s.get("u") or s.get("gif")
                if u:
                    items.append({"url": prox(u), "w": s.get("x"), "h": s.get("y")})
            media = {"kind": "gallery", "items": items}
        elif d.get("is_video") and (d.get("media") or {}).get("reddit_video"):
            rv = d["media"]["reddit_video"]
            vid = ""
            fb = rv.get("fallback_url", "")
            # https://v.redd.it/<id>/DASH_720.mp4?...
            if "v.redd.it/" in fb:
                vid = fb.split("v.redd.it/")[1].split("/")[0]
            media = {
                "kind": "video",
                "video_id": vid,
                "dash": f"/api/vreddit/{vid}/DASHPlaylist.mpd" if vid else None,
                "fallback": prox(fb.split("?")[0]) if fb else None,
                "duration": rv.get("duration"),
                "w": rv.get("width"),
                "h": rv.get("height"),
                "is_gif": rv.get("is_gif", False),
            }
        elif d.get("post_hint") == "image" or url.split("?")[0].lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")
        ):
            media = {"kind": "image", "url": prox(url)}
        elif url.split("?")[0].lower().endswith((".mp4", ".webm")):
            media = {"kind": "rawvideo", "url": prox(url)}

        # preview/thumbnail
        thumb = None
        prev = (d.get("preview") or {}).get("images") or []
        if prev:
            res = prev[0].get("resolutions") or []
            src = res[min(2, len(res) - 1)] if res else prev[0].get("source")
            if src and src.get("url"):
                thumb = prox(src["url"])
        elif d.get("thumbnail", "").startswith("http"):
            thumb = prox(d["thumbnail"])

        return {
            "id": d.get("id"),
            "subreddit": d.get("subreddit"),
            "title": d.get("title"),
            "author": d.get("author"),
            "score": d.get("score"),
            "num_comments": d.get("num_comments"),
            "created_utc": d.get("created_utc"),
            "over_18": bool(d.get("over_18")),
            "spoiler": bool(d.get("spoiler")),
            "stickied": bool(d.get("stickied")),
            "selftext": d.get("selftext") or "",
            "url": url,
            "permalink": d.get("permalink"),
            "link_flair_text": d.get("link_flair_text"),
            "domain": d.get("domain"),
            "thumb": thumb,
            "media": media,
        }

    @staticmethod
    def _apply_nsfw(posts: list[dict], nsfw: str) -> list[dict]:
        if nsfw == "sfw":
            return [p for p in posts if not p["over_18"]]
        if nsfw == "nsfw":
            return [p for p in posts if p["over_18"]]
        return posts

    def _organic_index(self, children: list[dict]):
        rows = [
            {"name": c["data"].get("subreddit"), "over18": c["data"].get("over_18")}
            for c in children
            if c.get("kind") == "t3" and c.get("data", {}).get("subreddit")
        ]
        try:
            db.upsert_subreddits(rows, source="organic")
        except Exception:
            pass  # indexing must never break a read

    # ---------- endpoints ----------

    async def listing(self, subreddit: str | None, sort: str, t: str, after: str | None,
                      limit: int, nsfw: str) -> dict:
        base = f"/r/{subreddit}" if subreddit else ""
        params = {"limit": limit, "t": t}
        if after:
            params["after"] = after
        data = await self.get(f"{base}/{sort}", params)
        children = data.get("data", {}).get("children", [])
        self._organic_index(children)
        posts = [self.normalize_post(c["data"]) for c in children if c.get("kind") == "t3"]
        return {"posts": self._apply_nsfw(posts, nsfw), "after": data.get("data", {}).get("after")}

    async def subreddit_about(self, name: str) -> dict:
        data = await self.get(f"/r/{name}/about")
        d = data.get("data", {})
        row = {
            "name": d.get("display_name"),
            "title": d.get("title"),
            "description": d.get("public_description"),
            "subscribers": d.get("subscribers"),
            "over18": d.get("over18"),
            "icon": d.get("icon_img") or d.get("community_icon", "").split("?")[0],
            "created_utc": d.get("created_utc"),
        }
        db.upsert_subreddits([row], source="organic")
        return row

    async def comments(self, subreddit: str, post_id: str, sort: str, comment: str | None) -> dict:
        params = {"limit": 500, "sort": sort}
        if comment:
            params["comment"] = comment
            params["context"] = 3
        data = await self.get(f"/r/{subreddit}/comments/{post_id}", params)
        post = self.normalize_post(data[0]["data"]["children"][0]["data"])

        def walk(node) -> list[dict]:
            out = []
            for c in node.get("data", {}).get("children", []):
                kind, d = c.get("kind"), c.get("data", {})
                if kind == "t1":
                    out.append({
                        "id": d.get("id"),
                        "author": d.get("author"),
                        "body": d.get("body") or "",
                        "score": d.get("score"),
                        "created_utc": d.get("created_utc"),
                        "stickied": bool(d.get("stickied")),
                        "is_submitter": bool(d.get("is_submitter")),
                        "distinguished": d.get("distinguished"),
                        "replies": walk(d["replies"]) if isinstance(d.get("replies"), dict) else [],
                    })
                elif kind == "more":
                    out.append({
                        "id": d.get("id"), "more": True,
                        "count": d.get("count", 0),
                        "parent_id": d.get("parent_id", ""),
                        "children": d.get("children", []),
                    })
            return out

        return {"post": post, "comments": walk(data[1])}

    async def search(self, q: str, subreddit: str | None, sort: str, t: str,
                     after: str | None, nsfw: str, limit: int) -> dict:
        base = f"/r/{subreddit}/search" if subreddit else "/search"
        params = {"q": q, "sort": sort, "t": t, "limit": limit, "type": "link"}
        if subreddit:
            params["restrict_sr"] = "true"
        if nsfw in ("nsfw", "all"):
            params["include_over_18"] = "on"
        if after:
            params["after"] = after
        data = await self.get(base, params)
        children = data.get("data", {}).get("children", [])
        self._organic_index(children)
        posts = [self.normalize_post(c["data"]) for c in children if c.get("kind") == "t3"]
        return {"posts": self._apply_nsfw(posts, nsfw), "after": data.get("data", {}).get("after")}

    async def search_subreddits(self, q: str, after: str | None, limit: int,
                                include_nsfw: bool = True) -> dict:
        params = {"q": q, "limit": limit}
        if include_nsfw:
            params["include_over_18"] = "on"
        if after:
            params["after"] = after
        data = await self.get("/subreddits/search", params)
        subs, rows = [], []
        for c in data.get("data", {}).get("children", []):
            d = c.get("data", {})
            row = {
                "name": d.get("display_name"),
                "title": d.get("title"),
                "description": d.get("public_description"),
                "subscribers": d.get("subscribers"),
                "over18": d.get("over18"),
                "icon": d.get("icon_img") or (d.get("community_icon") or "").split("?")[0],
                "created_utc": d.get("created_utc"),
            }
            rows.append(row)
            subs.append(row)
        db.upsert_subreddits(rows, source="organic")
        return {"subreddits": subs, "after": data.get("data", {}).get("after")}

    async def subreddit_listing(self, which: str, after: str | None, limit: int) -> dict:
        """which: popular | new | default"""
        params = {"limit": limit}
        if after:
            params["after"] = after
        data = await self.get(f"/subreddits/{which}", params)
        rows = []
        for c in data.get("data", {}).get("children", []):
            d = c.get("data", {})
            rows.append({
                "name": d.get("display_name"),
                "title": d.get("title"),
                "description": d.get("public_description"),
                "subscribers": d.get("subscribers"),
                "over18": d.get("over18"),
                "icon": d.get("icon_img") or (d.get("community_icon") or "").split("?")[0],
                "created_utc": d.get("created_utc"),
            })
        return {"rows": rows, "after": data.get("data", {}).get("after")}


client = RedditClient()
