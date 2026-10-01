from django.contrib import admin

from .models import Card, CardSquare, Phrase, Player, Room

admin.site.register(Room)
admin.site.register(Phrase)
admin.site.register(Player)
admin.site.register(Card)
admin.site.register(CardSquare)
