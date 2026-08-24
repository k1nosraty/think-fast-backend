"""ASGI entrypoint for HTTP and the empty T1 WebSocket boundary."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from apps.realtime.routing import websocket_urlpatterns

django_asgi_application = get_asgi_application()
application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
