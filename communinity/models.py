import secrets
import string
from django.db import models


def room_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(5))
        if not Room.objects.filter(code=code).exists():
            return code


class Room(models.Model):
    code = models.CharField(max_length=5, unique=True, default=room_code)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class Message(models.Model):
    TYPES = (("chat", "Chat"), ("system", "System"))
    room = models.ForeignKey(Room, related_name="messages", on_delete=models.CASCADE)
    anonymous_name = models.CharField(max_length=50)
    session_id = models.CharField(max_length=64, blank=True)
    message = models.CharField(max_length=500)
    message_type = models.CharField(max_length=10, choices=TYPES, default="chat")
    is_ai = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

