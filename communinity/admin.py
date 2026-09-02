from django.contrib import admin
from .models import Message, MessageReaction, MessageReport, Room

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "room_type", "created_at", "last_activity", "is_active")
    list_filter = ("room_type", "is_active")

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("room", "anonymous_name", "message_type", "is_ai", "created_at")
    search_fields = ("message", "anonymous_name", "room__code")

@admin.register(MessageReport)
class MessageReportAdmin(admin.ModelAdmin):
    list_display = ("message", "user", "reason", "resolved", "created_at")
    list_filter = ("resolved", "created_at")

admin.site.register(MessageReaction)

