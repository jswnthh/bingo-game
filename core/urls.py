from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.create_room, name="create_room"),
    path("join/", views.join_room, name="join_room"),
    path("watch/", views.watch_room, name="watch_room"),
    path("room/<str:code>/", views.room_lobby, name="room_lobby"),
    path("room/<str:code>/watch/", views.room_audience, name="room_audience"),
    path("room/<str:code>/play/", views.room_play, name="room_play"),
    path(
        "room/<str:code>/mark/<int:square_id>/",
        views.toggle_mark,
        name="toggle_mark",
    ),
    path("room/<str:code>/scores/", views.room_scores, name="room_scores"),
]
