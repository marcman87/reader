import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, directory
from .fourchan import client as chan
from .proxy import router as proxy_router
from .reddit import RedditError, client as reddit

app = FastAPI(title="Reader", docs_url=None, redoc_url=None)
app.include_router(proxy_router)

NSFW = Query("sfw", pattern="^(sfw|nsfw|all)$")


@app.exception_handler(RedditError)
async def reddit_error_handler(_, exc: RedditError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "reddit_configured": reddit.configured,
        "directory": db.directory_stats(),
    }


# ---------- directory ----------

@app.get("/api/directory")
async def get_directory(q: str = "", nsfw: str = NSFW, limit: int = 50, offset: int = 0):
    rows, total = db.search_directory(q, nsfw, min(limit, 200), offset)
    return {"subreddits": rows, "total": total}

@app.post("/api/directory/crawl")
async def crawl(mode: str = "seed"):
    return directory.start(mode)

@app.get("/api/directory/status")
async def crawl_status():
    return directory.status()


# ---------- reddit ----------

@app.get("/api/reddit/listing")
async def listing(subreddit: str | None = None, sort: str = "hot", t: str = "day",
                  after: str | None = None, limit: int = 50, nsfw: str = NSFW):
    if sort not in ("hot", "new", "top", "rising", "best"):
        raise HTTPException(400, "bad sort")
    return await reddit.listing(subreddit, sort, t, after, min(limit, 100), nsfw)

@app.get("/api/reddit/r/{name}/about")
async def about(name: str):
    return await reddit.subreddit_about(name)

@app.get("/api/reddit/comments/{subreddit}/{post_id}")
async def comments(subreddit: str, post_id: str, sort: str = "confidence",
                   comment: str | None = None):
    return await reddit.comments(subreddit, post_id, sort, comment)

@app.get("/api/reddit/search")
async def search(q: str, subreddit: str | None = None, sort: str = "relevance",
                 t: str = "all", after: str | None = None, nsfw: str = NSFW,
                 limit: int = 50):
    return await reddit.search(q, subreddit, sort, t, after, nsfw, min(limit, 100))

@app.get("/api/reddit/subreddits/search")
async def sr_search(q: str, after: str | None = None, nsfw: str = NSFW, limit: int = 50):
    res = await reddit.search_subreddits(q, after, min(limit, 100),
                                         include_nsfw=(nsfw != "sfw"))
    if nsfw == "sfw":
        res["subreddits"] = [s for s in res["subreddits"] if not s.get("over18")]
    elif nsfw == "nsfw":
        res["subreddits"] = [s for s in res["subreddits"] if s.get("over18")]
    return res


# ---------- 4chan ----------

@app.get("/api/chan/boards")
async def boards(nsfw: str = NSFW):
    bs = await chan.boards()
    if nsfw == "sfw":
        bs = [b for b in bs if b["worksafe"]]
    elif nsfw == "nsfw":
        bs = [b for b in bs if not b["worksafe"]]
    return {"boards": bs}

@app.get("/api/chan/{board}/catalog")
async def catalog(board: str, q: str | None = None):
    return {"threads": await chan.catalog(board, q)}

@app.get("/api/chan/{board}/thread/{no}")
async def chan_thread(board: str, no: int):
    return {"posts": await chan.thread(board, no)}


# ---------- static frontend ----------

STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")
if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = os.path.join(STATIC_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
