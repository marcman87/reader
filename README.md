# Reader

Self-hosted, read-only reader for Reddit and 4chan. FastAPI + React + SQLite, single container.
Text threads, images, galleries, and video (v.redd.it DASH with audio, 4chan webm) render in-app;
all media is proxied through the backend so nothing loads directly from Reddit/4chan in your browser.

## Reddit via RSS (no API credentials)

Reddit content comes from the **public Atom feeds** (`*.rss` on `www.reddit.com`) — the
officially supported, credential-free read surface. No Reddit account, app registration,
or OAuth is involved. Feeds are IP rate-limited, so the backend enforces a global
throttle (~1 request / 15 s), caches every feed for 5 minutes, serves stale copies when
rate-limited, and backs off for a minute after any 429.

What RSS does not carry, and how the app degrades:

- **Scores & comment counts** — not in feeds; hidden in the UI.
- **Comment threading & sorting** — feeds are flat and fixed-order; comments render as a
  flat list (up to ~the feed cap per thread).
- **Per-post NSFW flags** — filtering falls back to *subreddit-level* flags from the local
  directory (populate it via Arctic Shift import for good coverage). Posts in unknown
  subreddits count as SFW.
- **Galleries** — items aren't enumerable; gallery posts render as links.
- **v.redd.it video still works** — DASH manifests don't need auth and stream through the
  existing proxy, as do images and thumbnails.

Everything remains read-only and nothing is stored beyond the subreddit directory.

## Setup

1. `docker compose up -d --build` — that's it; `.env` is optional (see `.env.example`).
2. Open http://localhost:8320 — or publish over Tailscale:

   ```
   tailscale serve --bg --https=8320 http://localhost:8320
   ```

## The NSFW switch

Top-right, three positions, persisted per browser: **SFW** / **NSFW** / **ALL**.
Applies everywhere — directory, listings, search, and 4chan board list (worksafe flag).
Filtering is enforced server-side for listings/search and client-side for the directory query.

## Populating the subreddit directory

There is no "list all subreddits" API — Reddit listings cap at ~1,000 rows. The directory
(SQLite, `./data/reader.db`) is built in layers; buttons for the first three are on the
Directory page:

| Layer | What it does | Coverage | Time |
|---|---|---|---|
| **Seed** | paginates `/subreddits/{popular,new}.rss` | ~2K largest subs | ~10 min |
| **Prefix crawl** | sweeps `/subreddits/search.rss` across a–z, 0–9 | ~10K+ names | hours |
| **Arctic Shift import** | bulk dump of all known subreddits | millions | minutes |
| **Organic** | every listing/search you browse upserts what it saw | grows with use | automatic |

Since the RSS switch, crawls ride the same ~4 requests/minute budget as browsing, so they
are slow and the RSS entries carry **no subscriber counts or NSFW flags**. The Arctic
Shift import is the recommended way to populate the directory — it also supplies the
NSFW flags that listing/search filtering relies on.

### Arctic Shift import (near-complete coverage)

Arctic Shift (https://github.com/ArthurHeitmann/arctic_shift) is the successor to Pushshift's
public dumps and publishes periodic subreddit dumps (name, title, subscribers, NSFW flag) as
`.jsonl`/`.zst`. Download the latest subreddits dump via their download links, drop it in
`./data/`, then:

```
docker compose exec reader python scripts/import_arctic_shift.py /data/<dumpfile>.jsonl.zst
```

Existing rows are enriched, never blanked. Millions of rows import in a few minutes.

## Search

- **Reddit**: full search page — posts (sort: relevance/hot/top/new/comments; time window;
  optional single-subreddit scope) and subreddit search, all over the search RSS feeds.
  NSFW tri-state applies (subreddit-level, from the local directory).
- **4chan**: no official search API exists. Each board page has a catalog filter
  (matches subject + comment text across the full catalog).

## Notes and limits

- Read-only by design: no posting, voting, or account features.
- Reddit rate budget: unauthenticated RSS is throttled per IP; the client spaces requests
  ~15 s apart, caches feeds for 5 minutes, and cools down for a minute after any 429.
  A 429 error in the UI just means "wait a minute and retry".
- Comment threads are flat (RSS has no reply nesting) and capped at what the feed returns.
- 4chan API is throttled to 1 request/second per their rules; large catalogs load in one call.
- The media proxy only fetches from an allowlist (i.redd.it, v.redd.it, preview.redd.it,
  i.4cdn.org, i.imgur.com, thumbs) and passes Range headers through, so video seeking works.
- DB and media are not cached to disk beyond the directory; media streams through on demand.

## Ports / paths

- App: `8320`
- SQLite: `./data/reader.db` (bind-mounted)
- Backend API: `/api/*` (health check at `/api/health` — shows the Reddit mode and
  directory row counts)
