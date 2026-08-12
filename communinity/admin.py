from django.contrib import admin
from .models import Message, Room

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("code", "created_at", "last_activity", "is_active")
    list_filter = ("is_active",)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("room", "anonymous_name", "message_type", "is_ai", "created_at")
    search_fields = ("message", "anonymous_name", "room__code")

