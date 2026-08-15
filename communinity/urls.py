from django.urls import path
from . import views

app_name = "communinity"
urlpatterns = [
    path("", views.home, name="home"), path("create/", views.create_room, name="create"),
    path("join/", views.join_room, name="join"), path("room/<str:code>/", views.room, name="room"),
    path("room/<str:code>/messages/", views.messages, name="messages"),
    path("room/<str:code>/send/", views.send, name="send"),
    path("room/<str:code>/typing/", views.typing, name="typing"),
    path("room/<str:code>/change-name/", views.change_name, name="change_name"),
    path("room/<str:code>/leave/", views.leave, name="leave"),
]
