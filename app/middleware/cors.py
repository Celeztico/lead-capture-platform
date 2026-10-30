from collections.abc import Iterable, Sequence

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class PathScopedCORSMiddleware:
    """Apply a CORSMiddleware instance only to selected path prefixes.

    The public widget endpoints and the management API need different CORS
    policies; a single global CORSMiddleware cannot express both.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        paths: Iterable[str],
        allow_origins: list[str],
        allow_methods: Sequence[str] = ("GET",),
        allow_headers: Sequence[str] = (),
        allow_credentials: bool = False,
        allow_origin_regex: str | None = None,
        expose_headers: Sequence[str] = (),
        max_age: int = 600,
    ) -> None:
        self.app = app
        self.paths = tuple(paths)
        self.cors = CORSMiddleware(
            app,
            allow_origins=allow_origins,
            allow_methods=allow_methods,
            allow_headers=allow_headers,
            allow_credentials=allow_credentials,
            allow_origin_regex=allow_origin_regex,
            expose_headers=expose_headers,
            max_age=max_age,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and str(scope.get("path", "")).startswith(self.paths):
            await self.cors(scope, receive, send)
        else:
            await self.app(scope, receive, send)
