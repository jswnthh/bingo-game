import random
import secrets

from django.db import transaction

from .models import Card, CardSquare, Phrase, Room

# Avoid ambiguous characters: 0/O, 1/I/L
ROOM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 6
GRID_SIZE = 5
FREE_POSITION = CardSquare.FREE_POSITION

WIN_LINES = []
for _row in range(GRID_SIZE):
    WIN_LINES.append([_row * GRID_SIZE + _col for _col in range(GRID_SIZE)])
    WIN_LINES.append([_col * GRID_SIZE + _row for _col in range(GRID_SIZE)])
WIN_LINES.append([0, 6, 12, 18, 24])
WIN_LINES.append([4, 8, 12, 16, 20])


def normalize_code(code: str) -> str:
    return code.strip().upper()


def generate_room_code() -> str:
    while True:
        code = "".join(
            secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH)
        )
        if not Room.objects.filter(code=code).exists():
            return code


def create_card_for_player(player) -> Card:
    phrases = list(player.room.phrases.all())
    if len(phrases) < 24:
        raise ValueError("Room needs at least 24 phrases to build a card.")

    chosen = random.sample(phrases, 24)
    other_positions = [pos for pos in range(25) if pos != FREE_POSITION]
    random.shuffle(other_positions)

    with transaction.atomic():
        card = Card.objects.create(player=player)
        CardSquare.objects.create(
            card=card, phrase=None, position=FREE_POSITION, marked=True
        )
        CardSquare.objects.bulk_create(
            [
                CardSquare(
                    card=card,
                    phrase=phrase,
                    position=position,
                    marked=False,
                )
                for phrase, position in zip(chosen, other_positions)
            ]
        )
    return card


def squares_by_position(card, *, fresh=False) -> dict[int, CardSquare]:
    if fresh:
        squares = CardSquare.objects.filter(card_id=card.pk)
    else:
        squares = card.squares.all()
    return {square.position: square for square in squares}


def completed_line_indices(card, *, fresh=False) -> list[int]:
    by_pos = squares_by_position(card, fresh=fresh)
    return completed_lines_for_squares(by_pos.values())


def completed_lines_for_squares(squares):
    by_pos = {square.position: square for square in squares}
    completed = []
    for index, line in enumerate(WIN_LINES):
        if all(by_pos[pos].marked for pos in line):
            completed.append(index)
    return completed


def card_has_bingo(card, *, fresh=False) -> bool:
    return bool(completed_line_indices(card, fresh=fresh))


def highlighted_positions(card, *, fresh=False) -> set[int]:
    positions = set()
    for line_index in completed_line_indices(card, fresh=fresh):
        positions.update(WIN_LINES[line_index])
    return positions


def new_completed_lines(card, *, before_indices, fresh=True) -> list[int]:
    after = set(completed_line_indices(card, fresh=fresh))
    before = set(before_indices)
    return sorted(after - before)


def card_marked_count(card) -> int:
    return sum(1 for square in card.squares.all() if square.marked and square.phrase_id)


def room_scoreboard_rows(room, current_player_id=None) -> list[dict]:
    rows = []
    players = room.players.select_related("card").prefetch_related("card__squares").order_by(
        "created_at"
    )

    for player in players:
        row = {
            "id": player.id,
            "nickname": player.nickname,
            "marked": 0,
            "lines": 0,
            "bingo": False,
            "is_you": player.id == current_player_id,
        }
        if hasattr(player, "card"):
            card = player.card
            row["marked"] = card_marked_count(card)
            row["lines"] = len(completed_line_indices(card))
            row["bingo"] = row["lines"] > 0
        rows.append(row)

    rows.sort(key=lambda item: (-item["lines"], -item["marked"], item["nickname"].lower()))
    return rows


def room_event_history(room, after=None):
    # Read the watermark first; events committed later are picked up next time.
    latest = room.bingo_events.order_by("-id").values_list("id", flat=True).first() or 0
    if after is None:
        return {"events": [], "event_cursor": latest, "has_more_events": False}
    events = list(room.bingo_events.filter(id__gt=after, id__lte=latest).order_by("id")[:100])
    cursor = events[-1].pk if events else latest
    return {
        "events": [event.payload() for event in events],
        "event_cursor": cursor,
        "has_more_events": cursor < latest,
    }
