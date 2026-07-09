"""Media proxy.

Two entry points:
  /api/proxy?url=...            generic, allowlisted hosts only, Range passthrough
  /api/vreddit/{vid}/{path}     path-style proxy for v.redd.it so relative segment
                                URLs inside DASH manifests resolve naturally
"""
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .config import PROXY_ALLOWED_HOSTS, USER_AGENT

router = APIRouter()
_http = httpx.AsyncClient(timeout=60, follow_redirects=True)

PASS_REQUEST_HEADERS = ("range", "if-range", "if-none-match", "if-modified-since")
PASS_RESPONSE_HEADERS = (
    "content-type", "content-length", "content-range", "accept-ranges",
    "etag", "last-modified", "cache-control",
)


async def _stream(url: str, request: Request) -> Response:
    headers = {"User-Agent": USER_AGENT}
    for h in PASS_REQUEST_HEADERS:
        if h in request.headers:
            headers[h] = request.headers[h]

    req = _http.build_request("GET", url, headers=headers)
    upstream = await _http.send(req, stream=True)
    if upstream.status_code >= 400:
        await upstream.aclose()
        raise HTTPException(upstream.status_code, f"upstream returned {upstream.status_code}")

    resp_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() in PASS_RESPONSE_HEADERS
    }
    resp_headers.setdefault("Cache-Control", "public, max-age=86400")

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(65536):
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(body(), status_code=upstream.status_code, headers=resp_headers)


@router.get("/api/proxy")
async def proxy(url: str, request: Request):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in PROXY_ALLOWED_HOSTS:
        raise HTTPException(403, f"host not allowed: {parsed.hostname}")
    return await _stream(url, request)


@router.get("/api/vreddit/{video_id}/{path:path}")
async def vreddit(video_id: str, path: str, request: Request):
    if not video_id.isalnum() or ".." in path:
        raise HTTPException(400, "bad path")
    return await _stream(f"https://v.redd.it/{video_id}/{path}", request)
