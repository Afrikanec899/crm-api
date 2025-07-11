from urllib.parse import parse_qs

from django.db import close_old_connections

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from knox.auth import TokenAuthentication


class TokenAuthMiddleware:
    """
    Custom middleware
    """

    def __init__(self, inner):
        # Store the ASGI application we were passed
        self.inner = inner

    def __call__(self, scope):
        return TokenAuthMiddlewareInstance(scope, self)


class TokenAuthMiddlewareInstance:
    def __init__(self, scope, middleware):
        self.middleware = middleware
        self.scope = dict(scope)
        self.inner = self.middleware.inner

    async def __call__(self, receive, send):
        query = parse_qs(self.scope['query_string'])
        if b'token' in query.keys():
            key = query[b'token'][0]
            user = await self.get_user(key)
            self.scope["user"] = user
        inner = self.inner(self.scope)
        return await inner(receive, send)

    @database_sync_to_async
    def get_user(self, key):
        # Close old database connections to prevent usage of timed out connections
        close_old_connections()

        auth = TokenAuthentication()
        user, _ = auth.authenticate_credentials(key)
        return user


TokenAuthMiddlewareStack = lambda inner: TokenAuthMiddleware(AuthMiddlewareStack(inner))
