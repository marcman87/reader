# Reader

Self-hosted, read-only reader for Reddit and 4chan. FastAPI + React + SQLite, single container.
Text threads, images, galleries, and video (v.redd.it DASH with audio, 4chan webm) render in-app;
all media is proxied through the backend so nothing loads directly from Reddit/4chan in your browser.

## Reddit Data API usage & scope

This is a personal, single-user, non-commercial client. Its entire Reddit API surface is
read-only GETs, throttled well under the free-tier 100 QPM:

- `/r/{sub}/{hot|new|top|rising}` and `/r/{sub}/about` — listings the user browses
- `/r/{sub}/comments/{id}` — threads the user reads
- `/search`, `/r/{sub}/search`, `/subreddits/search|popular|new` — user-initiated search and
  a local navigation index of subreddit names/titles/subscriber counts

There are **no write actions anywhere in the codebase** — no submissions, comments, votes,
messages, or moderation actions. The only POST to Reddit is the standard OAuth token request
(`/api/v1/access_token`); every Data API call goes through `RedditClient.get()`. Post and comment
content is rendered on demand and not stored; media is streamed for display, not archived.
Nothing is redistributed and nothing is used for ML/AI training.

## Setup

1. Register a Reddit script app: https://www.reddit.com/prefs/apps → "create app" → type **script**.
   The client ID is the string under the app name; the secret is labeled.
2. `copy .env.example .env` and fill in the four Reddit values.
   NSFW content requires your Reddit account to have "adult content" enabled in its own settings —
   the app inherits your account's permissions.
3. `docker compose up -d --build`
4. Open http://localhost:8320 — or publish over Tailscale:

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
| **Seed** | paginates `/subreddits/{popular,new,default}` | ~3K largest subs | ~1 min |
| **Prefix crawl** | sweeps `/subreddits/search` across a–z, 0–9 | ~30–60K | ~40 min |
| **Deep crawl** | two-character prefix pairs (1,296 queries) | ~100K+ | hours |
| **Arctic Shift import** | bulk dump of all known subreddits | millions | minutes |
| **Organic** | every listing/search you browse upserts what it saw | grows with use | automatic |

Crawls run in the background throttled to ~60 QPM, under the 100 QPM script-app budget,
so browsing keeps working while a crawl runs.

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
  optional single-subreddit scope) and subreddit search. NSFW tri-state applies.
- **4chan**: no official search API exists. Each board page has a catalog filter
  (matches subject + comment text across the full catalog).

## Notes and limits

- Read-only by design: no posting, voting, or account features.
- Reddit rate budget: 100 QPM for a script app. The crawler uses ~60; normal browsing is light.
- "N more replies" stubs in large comment trees aren't expanded in v1 (morechildren API not wired).
- 4chan API is throttled to 1 request/second per their rules; large catalogs load in one call.
- The media proxy only fetches from an allowlist (i.redd.it, v.redd.it, preview.redd.it,
  i.4cdn.org, i.imgur.com, thumbs) and passes Range headers through, so video seeking works.
- DB and media are not cached to disk beyond the directory; media streams through on demand.

## Ports / paths

- App: `8320`
- SQLite: `./data/reader.db` (bind-mounted)
- Backend API: `/api/*` (health check at `/api/health` — shows whether Reddit creds loaded
  and directory row counts)
