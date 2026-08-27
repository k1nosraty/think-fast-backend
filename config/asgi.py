"""ASGI entrypoint for HTTP and the empty T1 WebSocket boundary."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

django_asgi_application = get_asgi_application()

# Django's app registry must be initialized before application-owned middleware
# imports models such as AnonymousUser.
from apps.realtime.auth import GuestTokenAuthMiddleware  # noqa: E402
from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AllowedHostsOriginValidator(
            GuestTokenAuthMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)
