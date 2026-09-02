import secrets
import string
from django.db import models
from django.contrib.auth.models import User


def room_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(5))
        if not Room.objects.filter(code=code).exists():
            return code


class Room(models.Model):
    ROOM_TYPES = (("private", "Private anonymous room"), ("public", "Public community room"))
    code = models.CharField(max_length=5, unique=True, default=room_code)
    title = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=240, blank=True)
    room_type = models.CharField(max_length=10, choices=ROOM_TYPES, default="private")
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title or self.code


class Message(models.Model):
    TYPES = (("chat", "Chat"), ("system", "System"))
    room = models.ForeignKey(Room, related_name="messages", on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="community_messages")
    anonymous_name = models.CharField(max_length=50)
    session_id = models.CharField(max_length=64, blank=True)
    message = models.CharField(max_length=500)
    message_type = models.CharField(max_length=10, choices=TYPES, default="chat")
    is_ai = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class MessageReaction(models.Model):
    TYPES = (("helpful", "Helpful"), ("interested", "I want this"))
    message = models.ForeignKey(Message, related_name="reactions", on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="community_reactions")
    reaction_type = models.CharField(max_length=12, choices=TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["message", "user", "reaction_type"], name="unique_message_user_reaction")]


class MessageReport(models.Model):
    message = models.ForeignKey(Message, related_name="reports", on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="community_reports")
    reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["message", "user"], name="unique_message_user_report")]

