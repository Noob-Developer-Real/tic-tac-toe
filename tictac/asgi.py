"""
ASGI config for tictac project.
"""

import os
from django.core.asgi import get_asgi_application
from django.urls import path
from channels.routing import ProtocolTypeRouter, URLRouter
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from channels.auth import AuthMiddlewareStack
from home.consumer import Gameroom

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tictac.settings")


django_asgi_app = ASGIStaticFilesHandler(get_asgi_application())

websocket_urlpatterns = [
    path("ws/game/<room_code>/", Gameroom.as_asgi()),
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    }
)
