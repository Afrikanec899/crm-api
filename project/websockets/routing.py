from django.urls import path

from channels.routing import ProtocolTypeRouter, URLRouter

from websockets.middleware import TokenAuthMiddlewareStack

from .consumers import EventsConsumer, MonitConsumer

application = ProtocolTypeRouter(
    {
        "websocket": TokenAuthMiddlewareStack(
            URLRouter(
                [
                    # URLRouter just takes standard Django path() or url() entries.
                    path("ws/", EventsConsumer),
                    path("monit/<int:account_id>/", MonitConsumer),
                ]
            )
        )
    }
)
