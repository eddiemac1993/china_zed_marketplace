from django.urls import path
from . import views

urlpatterns = [
    path("", views.events_home, name="events_home"),
    path("register/<int:event_id>/", views.event_register, name="event_register"),
    path("success/", views.event_success, name="event_success"),
    path("submissions/<int:event_id>/", views.event_submissions, name="event_submissions"),
]