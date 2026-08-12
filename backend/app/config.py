import os

# No Reddit credentials: content comes from public Atom feeds (see reddit.py).
USER_AGENT = os.environ.get(
    "READER_USER_AGENT",
    "reader-selfhosted/2.0 (personal read-only RSS reader)",
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
