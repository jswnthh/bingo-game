import json

from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import CreateRoomForm, JoinRoomForm, NicknameForm
from .models import BingoEvent, CardSquare, Phrase, Player, Room
from .services import (
    WIN_LINES,
    completed_lines_for_squares,
    room_event_history,
    create_card_for_player,
    generate_room_code,
    highlighted_positions,
    completed_line_indices,
    normalize_code,
    room_scoreboard_rows,
)


def get_player_for_session(request, room):
    player_id = request.session.get("player_id")
    if not player_id:
        return None
    return Player.objects.filter(id=player_id, room=room).select_related("card").first()


def get_room_or_none(code):
    return Room.objects.filter(code=normalize_code(code)).first()


def set_audience_session(request, room):
    request.session["audience_code"] = room.code


def clear_audience_session(request):
    request.session.pop("audience_code", None)


def is_audience_session(request, room):
    return request.session.get("audience_code") == room.code


@require_http_methods(["GET", "POST"])
def index(request):
    if request.method == "POST":
        join_form = JoinRoomForm(request.POST)
        if join_form.is_valid():
            room = join_form.cleaned_data["room"]
            return redirect("room_lobby", code=room.code)
    else:
        join_form = JoinRoomForm()
    return render(request, "index.html", {"join_form": join_form})


@require_http_methods(["GET", "POST"])
def create_room(request):
    if request.method == "POST":
        form = CreateRoomForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                room = Room.objects.create(
                    code=generate_room_code(),
                    title=form.cleaned_data["title"],
                )
                Phrase.objects.bulk_create(
                    [
                        Phrase(room=room, text=text)
                        for text in form.cleaned_data["phrases"]
                    ]
                )
            return redirect("room_lobby", code=room.code)
    else:
        form = CreateRoomForm()
    return render(request, "create.html", {"form": form})


@require_http_methods(["GET", "POST"])
def join_room(request):
    if request.method == "POST":
        form = JoinRoomForm(request.POST)
        if form.is_valid():
            room = form.cleaned_data["room"]
            return redirect("room_lobby", code=room.code)
    else:
        initial = {}
        if request.GET.get("code"):
            initial["code"] = request.GET.get("code")
        form = JoinRoomForm(initial=initial)
    return render(request, "join.html", {"form": form})


@require_http_methods(["GET", "POST"])
def watch_room(request):
    if request.method == "POST":
        form = JoinRoomForm(request.POST)
        if form.is_valid():
            room = form.cleaned_data["room"]
            set_audience_session(request, room)
            return redirect("room_audience", code=room.code)
    else:
        initial = {}
        if request.GET.get("code"):
            initial["code"] = request.GET.get("code")
        form = JoinRoomForm(initial=initial)
    return render(request, "watch.html", {"form": form})


@require_GET
def room_audience(request, code):
    room = get_room_or_none(code)
    if not room:
        return render(
            request,
            "room/not_found.html",
            {"code": normalize_code(code)},
            status=200,
        )

    set_audience_session(request, room)
    share_url = request.build_absolute_uri()

    return render(
        request,
        "room/audience.html",
        {
            "room": room,
            "share_url": share_url,
        },
    )


@require_http_methods(["GET", "POST"])
def room_lobby(request, code):
    room = get_room_or_none(code)
    if not room:
        return render(
            request,
            "room/not_found.html",
            {"code": normalize_code(code)},
            status=200,
        )

    player = get_player_for_session(request, room)
    if player and hasattr(player, "card"):
        return redirect("room_play", code=room.code)

    nickname_form = NicknameForm()
    if request.method == "POST":
        nickname_form = NicknameForm(request.POST)
        if nickname_form.is_valid():
            player = Player.objects.create(
                room=room, nickname=nickname_form.cleaned_data["nickname"]
            )
            create_card_for_player(player)
            request.session["player_id"] = player.id
            clear_audience_session(request)
            from .realtime import broadcast_player_joined

            broadcast_player_joined(room, player.nickname)
            return redirect("room_play", code=room.code)

    share_url = request.build_absolute_uri()
    return render(
        request,
        "room/lobby.html",
        {
            "room": room,
            "share_url": share_url,
            "nickname_form": nickname_form,
            "player_count": room.players.count(),
        },
    )


@require_GET
def room_play(request, code):
    room = get_room_or_none(code)
    if not room:
        return render(
            request,
            "room/not_found.html",
            {"code": normalize_code(code)},
            status=200,
        )

    player = get_player_for_session(request, room)
    if not player or not hasattr(player, "card"):
        return redirect("room_lobby", code=room.code)

    card = player.card
    squares = list(card.squares.select_related("phrase").order_by("position"))
    highlight = highlighted_positions(card)
    show_bingo = request.session.pop("show_bingo", False)
    completed_lines = completed_line_indices(card, fresh=True)

    return render(
        request,
        "room/play.html",
        {
            "room": room,
            "player": player,
            "squares": squares,
            "highlight": highlight,
            "show_bingo": show_bingo,
            "completed_lines_json": json.dumps(completed_lines),
        },
    )


@require_POST
def toggle_mark(request, code, square_id):
    with transaction.atomic():
        # Serialize room mutations, including event IDs, so recovery cursors cannot
        # skip an event from a concurrent transaction that commits later.
        room = get_object_or_404(Room.objects.select_for_update(), code=normalize_code(code))
        player = get_player_for_session(request, room)
        if not player or not hasattr(player, "card"):
            if _wants_json(request):
                return JsonResponse({"error": "Not in room."}, status=403)
            return redirect("room_lobby", code=room.code)

        squares = list(player.card.squares.all())
        square = next((item for item in squares if item.pk == square_id), None)
        if square is None:
            raise Http404
        if square.is_free:
            if _wants_json(request):
                return JsonResponse({"error": "Free square."}, status=400)
            return redirect("room_play", code=room.code)

        lines_before = set(completed_lines_for_squares(squares))
        square.marked = not square.marked
        square.save(update_fields=["marked"])
        lines_after = completed_lines_for_squares(squares)
        new_lines = [index for index in lines_after if index not in lines_before]
        now_bingo = bool(lines_after)
        new_bingo = bool(new_lines) and square.marked
        highlight = sorted({pos for index in lines_after for pos in WIN_LINES[index]})
        event = None
        if new_bingo:
            event = BingoEvent.objects.create(room=room, player=player, nickname=player.nickname)

        from .realtime import broadcast_bingo, broadcast_score_update

        def publish():
            broadcast_score_update(room)
            if event:
                broadcast_bingo(room, event)

        transaction.on_commit(publish)

    if _wants_json(request):
        return JsonResponse(
            {
                "marked": square.marked,
                "square_id": square.id,
                "position": square.position,
                "highlight": highlight,
                "bingo": now_bingo,
                "new_bingo": new_bingo,
                "new_line_indices": new_lines,
            }
        )

    if new_bingo:
        request.session["show_bingo"] = True

    return redirect("room_play", code=room.code)


def _wants_json(request):
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


@never_cache
@require_GET
def room_scores(request, code):
    room = get_room_or_none(code)
    if not room:
        return JsonResponse({"error": "Room not found."}, status=404)

    player = get_player_for_session(request, room)
    current_id = player.id if player else None
    after = request.GET.get("after")
    if after is not None:
        try:
            after = int(after)
            if after < 0 or after > 9223372036854775807:
                raise ValueError
        except ValueError:
            return JsonResponse({"error": "Invalid event cursor."}, status=400)
    history = room_event_history(room, after)
    rows = room_scoreboard_rows(room, current_player_id=current_id)

    return JsonResponse(
        {
            "players": rows,
            "updated_at": timezone.now().isoformat(),
            **history,
        }
    )
