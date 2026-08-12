# reader — Claude Code guide

This is **reader**, a self-hosted, read-only Reddit / 4chan client. It is one service
in Marcus's personal "AgentOS" stack and the one component that is publicly reachable,
so treat this repo as **public**: never put infrastructure details, server addresses,
internal hostnames, tokens, or other services' information in it.

## Stack conventions
- FastAPI + SQLAlchemy + SQLite + React (Vite) + Docker Compose (matches Marcus's
  other services).
- Reddit content comes from the public RSS/Atom feeds — **no API credentials**
  (Reddit declined the Data API application, July 2026). Respect the throttle/cache
  logic in `backend/app/reddit.py`; unauthenticated feeds 429 aggressively.
- `.env` is optional (UA/DB-path overrides only) — still gitignored, never commit.
  The tracked template is `.env.example`. The SQLite DB (`data/reader.db`) is gitignored.

## Develop & deploy
- Develop here on the laptop with Claude Code; commit and `git push`
  (origin: github.com/marcman87/reader).
- The server pulls this repo and runs `docker compose up -d --build`. Nothing about the
  server's network or the other services belongs in this file.

## Marcus's working preferences
Direct and concise; show assumptions on any numeric work; push back on flawed
reasoning; ask in plain chat when genuinely ambiguous.
