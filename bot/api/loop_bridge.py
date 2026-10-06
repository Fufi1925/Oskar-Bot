"""Keep the complete API middleware stack on one loop, with server-owned I/O."""
import asyncio
from starlette.types import ASGIApp, Scope, Receive, Send


class BotLoopMiddleware:
    def __init__(self, app: ASGIApp, loop_provider):
        self.app = app
        self.loop_provider = loop_provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        server_loop = asyncio.get_running_loop()
        bot_loop = self.loop_provider()
        if (scope['type'] != 'http' or bot_loop is None or
                bot_loop.is_closed() or not bot_loop.is_running() or
                bot_loop is server_loop):
            await self.app(scope, receive, send)
            return

        # Only socket I/O crosses loops. call_next, task groups, events and
        # streaming/background work all stay together on the bot loop.
        async def server_receive():
            return await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(receive(), server_loop))

        async def server_send(message):
            await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(send(message), server_loop))

        pending = asyncio.run_coroutine_threadsafe(
            self.app(scope, server_receive, server_send), bot_loop)
        try:
            await asyncio.wrap_future(pending)
        finally:
            if not pending.done():
                pending.cancel()
