import os

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .services import normalize_code, room_scoreboard_rows


def room_group_name(room_code: str) -> str:
    return f"bingo_{normalize_code(room_code)}"


def _group_send(room_code: str, message: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(room_group_name(room_code), message)


def scoreboard_payload(room, *, current_player_id=None) -> list[dict]:
    return room_scoreboard_rows(room, current_player_id=current_player_id)


def broadcast_score_update(room) -> None:
    rows = scoreboard_payload(room, current_player_id=None)
    _group_send(
        room.code,
        {
            "type": "room.message",
            "event_type": "score_update",
            "players": rows,
        },
    )


def broadcast_player_joined(room, nickname: str) -> None:
    count = room.players.count()
    _group_send(
        room.code,
        {
            "type": "room.message",
            "event_type": "player_joined",
            "player": nickname,
            "player_count": count,
        },
    )
    broadcast_score_update(room)


def broadcast_bingo(room, nickname: str) -> None:
    _group_send(
        room.code,
        {
            "type": "room.message",
            "event_type": "bingo",
            "player": nickname,
        },
    )
    broadcast_score_update(room)


def channel_layer_backend_hint() -> str:
    if os.environ.get("REDIS_URL"):
        return "redis"
    return "inmemory"
