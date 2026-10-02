from django.db import models


class Room(models.Model):
    code = models.CharField(max_length=6, unique=True, db_index=True)
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.code})"


class Phrase(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="phrases")
    text = models.CharField(max_length=200)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["room", "text"], name="unique_phrase_per_room"),
        ]

    def __str__(self):
        return self.text


class Player(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="players")
    nickname = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.nickname


class Card(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE, related_name="card")

    def __str__(self):
        return f"Card for {self.player}"


class CardSquare(models.Model):
    FREE_POSITION = 12

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="squares")
    phrase = models.ForeignKey(
        Phrase, on_delete=models.CASCADE, null=True, blank=True, related_name="card_squares"
    )
    position = models.PositiveSmallIntegerField()
    marked = models.BooleanField(default=False)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["card", "position"], name="unique_square_position"),
        ]

    @property
    def is_free(self):
        return self.phrase_id is None


class BingoEvent(models.Model):
    """Durable announcements so clients can catch up after losing a connection."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="bingo_events")
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    nickname = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["room", "id"], name="bingo_event_room_id")]

    def payload(self):
        return {"event_id": self.pk, "player_id": self.player_id, "player": self.nickname}
