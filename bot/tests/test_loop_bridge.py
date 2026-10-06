"""Exercise real ASGI request/streaming events with separate server/bot loops."""
import asyncio
import threading
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse
from api.loop_bridge import BotLoopMiddleware


async def check(bot_loop):
    app = FastAPI()
    executed = []

    @app.middleware('http')
    async def passthrough(request, call_next):
        return await call_next(request)

    @app.post('/api/v1/firewall/check')
    async def endpoint(request: Request):
        body = await request.json()
        executed.append(asyncio.get_running_loop())
        return {'allowed': True, 'value': body['value']}

    @app.get('/download')
    async def download():
        async def chunks():
            for part in [b'one', b'two']:
                assert asyncio.get_running_loop() is bot_loop
                await asyncio.sleep(0)
                yield part
        return StreamingResponse(chunks(), headers={'x-test': 'preserved'})

    app.add_middleware(BotLoopMiddleware, loop_provider=lambda: bot_loop)
    server_loop = asyncio.get_running_loop()
    async def server_owned(scope, receive, send):
        async def checked_receive():
            assert asyncio.get_running_loop() is server_loop
            return await receive()
        async def checked_send(message):
            assert asyncio.get_running_loop() is server_loop
            await send(message)
        await app(scope, checked_receive, checked_send)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server_owned), base_url='http://test') as client:
        responses = await asyncio.gather(*[
            client.post('/api/v1/firewall/check', json={'value': i}) for i in range(20)])
        assert [r.json() for r in responses] == [{'allowed': True, 'value': i} for i in range(20)]
        assert all(loop is bot_loop for loop in executed)
        response = await client.get('/download')
        assert response.content == b'onetwo'
        assert response.headers['x-test'] == 'preserved'


async def check_real_app(bot_loop):
    import os
    import tempfile
    os.environ.setdefault('TOKEN', 'offline-test')
    from api import dependencies
    from api.server import create_app
    from utils import firewall
    old_loop = dependencies.get_bot_loop()
    old_path = firewall.DB_PATH
    dependencies.set_bot_loop(bot_loop)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            firewall.DB_PATH = str(Path(tmp) / 'firewall.db')
            app = create_app()
            mounted = next(route.app for route in app.routes if getattr(route, 'path', '') == '/api/v1')
            # Authentication is tested separately; isolate loop transport here.
            from api.server import api_rate_limit
            mounted.dependency_overrides[dependencies.verify_api_key] = lambda: None
            mounted.dependency_overrides[api_rate_limit] = lambda: None
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                for _ in range(5):
                    response = await client.post('/api/v1/firewall/check', json={'ip': '127.0.0.1', 'path': '/dashboard'})
                    assert response.status_code == 200, response.text
                    assert response.json()['allowed'] is True
    finally:
        dependencies.set_bot_loop(old_loop)
        firewall.DB_PATH = old_path


def main():
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    def serve():
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        loop.run_forever()
    thread = threading.Thread(target=serve)
    thread.start()
    ready.wait()
    try:
        asyncio.run(asyncio.wait_for(check(loop), 15))
        asyncio.run(asyncio.wait_for(check_real_app(loop), 20))
        # A fresh server loop against the same bot loop must work as well.
        asyncio.run(asyncio.wait_for(check(loop), 15))
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join()
        loop.close()
    print('Loop bridge: 40 concurrent POSTs and two streaming downloads passed')


if __name__ == '__main__':
    main()
