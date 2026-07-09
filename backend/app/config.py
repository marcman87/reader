import os

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD", "")
USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT",
    f"windows:reader.selfhosted:v1.0 (by /u/{REDDIT_USERNAME or 'unknown'})",
)

DB_PATH = os.environ.get("DB_PATH", "/data/reader.db")

# Domains the media proxy will fetch from. Everything else is refused.
PROXY_ALLOWED_HOSTS = {
    "i.redd.it",
    "v.redd.it",
    "preview.redd.it",
    "external-preview.redd.it",
    "b.thumbs.redditmedia.com",
    "a.thumbs.redditmedia.com",
    "styles.redditmedia.com",
    "i.imgur.com",
    "i.4cdn.org",
    "s.4cdn.org",
}
