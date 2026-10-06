"""The real proxy must preserve split OAuth/session cookies and Set-Cookie fields."""
import asyncio
import os
import sys
import tempfile
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TOKEN", "offline-test")
import httpx
from starlette.requests import Request
from api import server


async def check():
    app = server.create_app()
    proxy = next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/{path:path}")
    calls = []

    def upstream(request):
        cookies = SimpleCookie()
        cookies.load(request.headers.get("cookie", ""))
        calls.append(request)
        assert cookies["__Host-next-auth.csrf-token"].value == "csrf-test"
        assert cookies["__Secure-next-auth.state"].value == "state-test", "OAuth state cookie was lost"
        assert cookies["__Secure-next-auth.session-token.0"].value == "part-0"
        assert cookies["__Secure-next-auth.session-token.1"].value == "part-1"
        assert request.url.params["state"] == "state-test"
        assert request.headers["x-forwarded-host"] == "universtiy-bot.up.railway.app"
        assert request.headers["x-forwarded-proto"] == "https"
        assert request.headers["x-forwarded-port"] == "443"
        return httpx.Response(302, headers=[
            ("Location", "https://universtiy-bot.up.railway.app/auth/success?next=%2Fdashboard"),
            ("Set-Cookie", "__Secure-next-auth.state=; Path=/; Max-Age=0; Secure; HttpOnly"),
            ("Set-Cookie", "__Secure-next-auth.session-token=session-test; Path=/; Secure; HttpOnly"),
        ])

    original_client = httpx.AsyncClient
    def client(**kwargs):
        return original_client(transport=httpx.MockTransport(upstream), **kwargs)

    parts = [
        "__Host-next-auth.csrf-token=csrf-test",
        "__Secure-next-auth.state=state-test",
        "__Secure-next-auth.session-token.0=part-0",
        "__Secure-next-auth.session-token.1=part-1",
    ]
    for split in [False, True]:
        headers = [
            (b"host", b"universtiy-bot.up.railway.app"),
            (b"x-forwarded-host", b"universtiy-bot.up.railway.app, internal"),
            (b"x-forwarded-proto", b"https, http"),
        ]
        headers.extend((b"cookie", value.encode()) for value in (parts if split else ["; ".join(parts)]))
        request = Request({
            "type": "http", "method": "GET", "path": "/api/auth/callback/discord",
            "query_string": b"code=test-code&state=state-test", "headers": headers,
            "scheme": "http", "server": ("127.0.0.1", 8080), "client": ("127.0.0.1", 1),
        }, receive=lambda: asyncio.sleep(0, result={"type": "http.request", "body": b"", "more_body": False}))
        with patch.object(server.httpx, "AsyncClient", client):
            response = await proxy(request, "api/auth/callback/discord")
        assert response.status_code == 302
        cookies = [value for name, value in response.raw_headers if name.lower() == b"set-cookie"]
        assert len(cookies) == 2, "callback cookie deletion and new session must stay separate"
        assert next(value for name, value in response.raw_headers if name.lower() == b"location").decode().startswith("https://universtiy-bot.up.railway.app/auth/success")
    assert len(calls) == 2


def main():
    previous = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as temp:
            os.chdir(temp)
            asyncio.run(check())
    finally:
        os.chdir(previous)
    print("Dashboard proxy: normal/split state and session cookies, public HTTPS origin and two Set-Cookie fields passed")


if __name__ == "__main__":
    main()
