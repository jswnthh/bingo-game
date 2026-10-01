# Generated manually for MVP bootstrap

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Room",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.CharField(db_index=True, max_length=6, unique=True)),
                ("title", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Player",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nickname", models.CharField(max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="players",
                        to="core.room",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.CreateModel(
            name="Phrase",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("text", models.CharField(max_length=200)),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="phrases",
                        to="core.room",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Card",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "player",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="card",
                        to="core.player",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CardSquare",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("position", models.PositiveSmallIntegerField()),
                ("marked", models.BooleanField(default=False)),
                (
                    "card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="squares",
                        to="core.card",
                    ),
                ),
                (
                    "phrase",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="card_squares",
                        to="core.phrase",
                    ),
                ),
            ],
            options={
                "ordering": ["position"],
            },
        ),
        migrations.AddConstraint(
            model_name="phrase",
            constraint=models.UniqueConstraint(
                fields=("room", "text"), name="unique_phrase_per_room"
            ),
        ),
        migrations.AddConstraint(
            model_name="cardsquare",
            constraint=models.UniqueConstraint(
                fields=("card", "position"), name="unique_square_position"
            ),
        ),
    ]
