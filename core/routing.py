from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/room/(?P<room_code>[A-Za-z0-9]{6})/$", consumers.RoomConsumer.as_asgi()),
]
