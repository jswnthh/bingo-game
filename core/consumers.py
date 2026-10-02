import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .models import Room
from .realtime import room_group_name, scoreboard_payload
from .services import normalize_code


class RoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        raw_code = self.scope["url_route"]["kwargs"]["room_code"]
        self.room_code = normalize_code(raw_code)
        self.group_name = room_group_name(self.room_code)

        room = await self.get_room(self.room_code)
        if not room:
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        players = await self.get_scoreboard(room)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "score_update",
                    "players": players,
                }
            )
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def room_message(self, event):
        payload = {
            key: value
            for key, value in event.items()
            if key not in ("type", "event_type")
        }
        payload["type"] = event["event_type"]
        await self.send(text_data=json.dumps(payload))

    async def receive(self, text_data=None, bytes_data=None):
        if text_data == '{"type":"ping"}':
            await self.send(text_data='{"type":"pong"}')

    @database_sync_to_async
    def get_room(self, code):
        return Room.objects.filter(code=code).first()

    @database_sync_to_async
    def get_scoreboard(self, room):
        return scoreboard_payload(room, current_player_id=None)
