from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CacheControlMiddleware:
    """Add Cache-Control to responses under selected paths when absent."""

    def __init__(self, app: ASGIApp, *, paths: Iterable[str], cache_control: str) -> None:
        self.app = app
        self.paths = tuple(paths)
        self.cache_control = cache_control

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith(self.paths):
            await self.app(scope, receive, send)
            return

        async def send_with_cache_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                if not any(k.lower() == b"cache-control" for k, _ in headers):
                    headers.append((b"cache-control", self.cache_control.encode()))
            await send(message)

        await self.app(scope, receive, send_with_cache_header)
