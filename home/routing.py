from django.urls import path
from .consumer import Gameroom

websocket_urlpatterns = [
    path("ws/game/<room_code>/", Gameroom.as_asgi()),
]
