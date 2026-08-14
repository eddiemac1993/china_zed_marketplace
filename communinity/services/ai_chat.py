import os
import random
import threading
import requests
from django.conf import settings
from django.core.cache import cache

# deliberately outside the human name pool in views.py, so an automated
# participant can never appear under the same name as a real one
AI_NAMES = ["Chatty Robot", "Curious Android", "Witty Circuit"]

FALLBACKS = [
    "This room got quiet 👀", "Random question: what's everyone doing right now?",
    "😂", "Someone say something controversial.",
    "Okay, important question: nshima or rice?", "Who's still awake?",
    "Rate your day from 1–10.", "This chat needs some energy 😂",
]


def ai_enabled():
    return getattr(settings, "COMMUNINITY_AI_ENABLED", True)


def should_reply(room, human_count):
    if not ai_enabled() or human_count < 3 or cache.get(f"communinity-ai:{room.pk}"):
        return False
    return random.random() < 0.18


def generate_reply(room):
    fallback = random.choice(FALLBACKS)
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return fallback
    recent = list(room.messages.filter(message_type="chat").values_list("anonymous_name", "message").order_by("-id")[:12])[::-1]
    context = "\n".join(f"{name}: {text}" for name, text in recent)
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": os.getenv("COMMUNINITY_AI_MODEL", "gpt-4o-mini"), "max_tokens": 60,
                  "temperature": .9, "messages": [
                    {"role": "system", "content": "Act like a casual anonymous chat participant. Reply briefly, playfully and safely. Never claim to be human. No essays."},
                    {"role": "user", "content": context or "Start a fun conversation."}]}, timeout=8,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()[:500] or fallback
    except Exception:
        return fallback


def _write_reply(room_pk):
    from django.db import connection
    from communinity.models import Message, Room
    try:
        room = Room.objects.filter(pk=room_pk).first()
        if room is not None:
            Message.objects.create(room=room, anonymous_name=random.choice(AI_NAMES),
                                   message=generate_reply(room), is_ai=True)
    finally:
        connection.close()


def maybe_add_ai_message(room, human_count):
    if not should_reply(room, human_count):
        return None
    cache.set(f"communinity-ai:{room.pk}", True, 120)
    # generating a reply can take seconds; the sender must never wait on it
    threading.Thread(target=_write_reply, args=(room.pk,), daemon=True).start()
    return None

