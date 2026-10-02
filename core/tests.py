import asyncio
from unittest.mock import AsyncMock, patch

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.db import connection
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

from .consumers import RoomConsumer
from .models import BingoEvent, CardSquare, Phrase, Player, Room
from .realtime import _group_send, room_group_name
from .services import create_card_for_player
from .views import toggle_mark


@override_settings(SECURE_SSL_REDIRECT=False)
class RealtimeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.room = Room.objects.create(code="ABCDEF", title="Test")
        Phrase.objects.bulk_create([Phrase(room=cls.room, text=f"Phrase {i}") for i in range(24)])
        cls.player = Player.objects.create(room=cls.room, nickname="Player")
        cls.card = create_card_for_player(cls.player)

    def mark(self, position):
        square = self.card.squares.get(position=position)
        request = RequestFactory().post("/", HTTP_ACCEPT="application/json")
        request.session = {"player_id": self.player.pk}
        with self.captureOnCommitCallbacks(execute=True):
            return toggle_mark(request, self.room.code, square.pk)

    def event(self):
        return BingoEvent.objects.create(room=self.room, player=self.player, nickname=self.player.nickname)

    def test_normal_mark_reads_card_once_and_broadcasts_once(self):
        with patch("core.realtime._group_send") as send, CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.mark(0).status_code, 200)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1]["event_type"], "score_update")
        # One fixture lookup, one card read and one room scoreboard prefetch.
        reads = [q for q in queries if q["sql"].startswith("SELECT") and 'FROM "core_cardsquare"' in q["sql"]]
        self.assertEqual(len(reads), 3)
        self.assertFalse(BingoEvent.objects.exists())

    def test_winning_mark_persists_event_and_sends_one_scoreboard(self):
        self.card.squares.filter(position__in=[0, 1, 2, 3]).update(marked=True)
        with patch("core.realtime._group_send") as send:
            response = self.mark(4)
        self.assertEqual(response.status_code, 200)
        event = BingoEvent.objects.get()
        messages = [call.args[1] for call in send.call_args_list]
        self.assertEqual([m["event_type"] for m in messages], ["score_update", "bingo"])
        self.assertEqual(messages[1]["event_id"], event.pk)
        self.assertEqual(messages[1]["player_id"], self.player.pk)
        with patch("core.realtime._group_send"):
            self.mark(4)  # Unmarking must not erase the recoverable announcement.
        payload = self.client.get(f"/room/{self.room.code}/scores/?after=0").json()
        self.assertEqual(payload["events"], [event.payload()])
        self.assertEqual(payload["players"][0]["lines"], 0)

    def test_history_baseline_pagination_and_room_isolation(self):
        events = [self.event() for _ in range(101)]
        other = Room.objects.create(code="GHJKLM", title="Other")
        BingoEvent.objects.create(room=other, player=self.player, nickname="Other")
        url = f"/room/{self.room.code}/scores/"
        response = self.client.get(url)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.json()["events"], [])
        self.assertEqual(response.json()["event_cursor"], events[-1].pk)
        first = self.client.get(url, {"after": 0}).json()
        self.assertEqual(len(first["events"]), 100)
        self.assertTrue(first["has_more_events"])
        second = self.client.get(url, {"after": first["event_cursor"]}).json()
        self.assertEqual(second["events"], [events[-1].payload()])
        self.assertFalse(second["has_more_events"])
        self.assertEqual(self.client.get(url, {"after": second["event_cursor"]}).json()["events"], [])

    def test_invalid_event_cursor(self):
        for cursor in ["invalid", "-1", "999999999999999999999999"]:
            self.assertEqual(self.client.get(f"/room/{self.room.code}/scores/", {"after": cursor}).status_code, 400)

    def test_redis_failure_does_not_lose_mark_or_bingo(self):
        self.card.squares.filter(position__in=[0, 1, 2, 3]).update(marked=True)
        layer = AsyncMock()
        layer.group_send.side_effect = ConnectionError("Redis unavailable")
        with patch("core.realtime.get_channel_layer", return_value=layer), self.assertLogs("core.realtime", level="ERROR"):
            self.assertEqual(self.mark(4).status_code, 200)
        self.assertTrue(self.card.squares.get(position=4).marked)
        self.assertEqual(BingoEvent.objects.count(), 1)

    def test_broadcast_timeout_is_recoverable(self):
        with patch("core.realtime.asyncio.wait_for", side_effect=TimeoutError), patch("core.realtime.get_channel_layer") as layer:
            # Avoid creating an unawaited coroutine when mocking wait_for.
            layer.return_value.group_send.return_value = None
            with self.assertLogs("core.realtime", level="ERROR"):
                _group_send(self.room.code, {"type": "room.message"})

    def test_cannot_mark_another_players_card_or_free_square(self):
        other = Player.objects.create(room=self.room, nickname="Other")
        other_card = create_card_for_player(other)
        session = self.client.session
        session["player_id"] = self.player.pk
        session.save()
        square = other_card.squares.get(position=0)
        self.assertEqual(self.client.post(f"/room/{self.room.code}/mark/{square.pk}/", HTTP_ACCEPT="application/json").status_code, 404)
        self.assertEqual(self.mark(CardSquare.FREE_POSITION).status_code, 400)


class WebsocketTests(TransactionTestCase):
    def test_initial_scores_heartbeat_and_remote_bingo(self):
        Room.objects.create(code="ABCDEF", title="Socket test")

        async def scenario():
            socket = WebsocketCommunicator(RoomConsumer.as_asgi(), "/ws/room/ABCDEF/")
            socket.scope["url_route"] = {"kwargs": {"room_code": "ABCDEF"}}
            connected, _ = await socket.connect()
            self.assertTrue(connected)
            self.assertEqual((await socket.receive_json_from())["type"], "score_update")
            await socket.send_to(text_data='{"type":"ping"}')
            self.assertEqual(await socket.receive_json_from(), {"type": "pong"})
            await get_channel_layer().group_send(room_group_name("ABCDEF"), {
                "type": "room.message", "event_type": "bingo", "event_id": 42,
                "player_id": 7, "player": "Remote player",
            })
            event = await socket.receive_json_from()
            self.assertEqual(event["type"], "bingo")
            self.assertEqual(event["event_id"], 42)
            await socket.disconnect()

        asyncio.run(scenario())
