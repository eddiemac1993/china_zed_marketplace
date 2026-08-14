import random
import time
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Message, Room
from .services.ai_chat import maybe_add_ai_message

ADJECTIVES = ["Quiet", "Blue", "Crazy", "Sleepy", "Happy", "Lost", "Purple", "Silent", "Wild", "Brave"]
NOUNS = ["Panda", "Ghost", "Mango", "Lion", "Potato", "Penguin", "Monkey", "Goat", "Banana", "Otter"]


def _session_token(request):
    # first-time visitors have no session_key yet, so rate-limit keys built from
    # it would collapse into one shared bucket for every new visitor
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _identity(request, room, change=False):
    if not request.session.session_key:
        request.session.create()
    key = f"communinity_name_{room.code}"
    if change or key not in request.session:
        request.session[key] = f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)}"
    return request.session[key], request.session.session_key


def home(request):
    return render(request, "communinity/home.html")


@require_POST
def create_room(request):
    token = _session_token(request)
    limit = f"communinity-create:{token}"
    if cache.get(limit):
        return render(request, "communinity/home.html", {"error": "Please wait a moment before creating another room."}, status=429)
    room = Room.objects.create()
    cache.set(limit, True, 20)
    return redirect("communinity:room", code=room.code)


@require_POST
def join_room(request):
    code = request.POST.get("code", "").strip().upper()
    if not Room.objects.filter(code=code, is_active=True).exists():
        return render(request, "communinity/home.html", {"error": "That room code was not found."}, status=404)
    return redirect("communinity:room", code=code)


def room(request, code):
    room_obj = get_object_or_404(Room, code=code.upper(), is_active=True)
    name, session_id = _identity(request, room_obj)
    joined_key = f"communinity_joined_{room_obj.code}"
    if not request.session.get(joined_key):
        Message.objects.create(room=room_obj, anonymous_name=name, session_id=session_id,
                               message=f"{name} joined the room 👋", message_type="system")
        request.session[joined_key] = True
    presence = f"communinity-presence:{room_obj.code}"
    users = cache.get(presence, {})
    users[session_id] = time.time()
    cache.set(presence, users, 90)
    return render(request, "communinity/room.html", {"room": room_obj, "anonymous_name": name, "session_id": session_id})


def messages(request, code):
    room_obj = get_object_or_404(Room, code=code.upper(), is_active=True)
    after = request.GET.get("after", "0")
    try: after = int(after)
    except ValueError: after = 0
    _, session_id = _identity(request, room_obj)
    presence = f"communinity-presence:{room_obj.code}"
    users = {k:v for k,v in cache.get(presence, {}).items() if time.time()-v < 45}
    users[session_id] = time.time(); cache.set(presence, users, 90)
    typing_key = f"communinity-typing:{room_obj.code}"
    typers = cache.get(typing_key, {})
    typing_names = [n for sid, (n, ts) in typers.items() if sid != session_id and time.time() - ts < 3]
    rows = room_obj.messages.filter(pk__gt=after).order_by("id")[:100]
    return JsonResponse({"online": len(users), "typing": typing_names, "messages": [{"id":m.id,"name":m.anonymous_name,"text":m.message,"type":m.message_type,"mine":m.session_id==session_id,"ai":m.is_ai,"time":m.created_at.strftime("%H:%M")} for m in rows]})


@require_POST
def typing(request, code):
    room_obj = get_object_or_404(Room, code=code.upper(), is_active=True)
    name, session_id = _identity(request, room_obj)
    key = f"communinity-typing:{room_obj.code}"
    typers = cache.get(key, {})
    typers[session_id] = (name, time.time())
    cache.set(key, typers, 10)
    return JsonResponse({"ok": True})


@require_POST
def send(request, code):
    room_obj = get_object_or_404(Room, code=code.upper(), is_active=True)
    name, session_id = _identity(request, room_obj)
    text = request.POST.get("message", "").strip()
    if not text or len(text) > 500:
        return JsonResponse({"error": "Messages must be between 1 and 500 characters."}, status=400)
    spam_key = f"communinity-send:{room_obj.pk}:{session_id}"
    last = cache.get(spam_key)
    if last and (time.time()-last[0] < 1.2 or last[1] == text):
        return JsonResponse({"error": "Please slow down and avoid repeated messages."}, status=429)
    cache.set(spam_key, (time.time(), text), 30)
    msg = Message.objects.create(room=room_obj, anonymous_name=name, session_id=session_id, message=text)
    Room.objects.filter(pk=room_obj.pk).update(last_activity=timezone.now())
    human_count = room_obj.messages.filter(is_ai=False, message_type="chat").count()
    maybe_add_ai_message(room_obj, human_count)
    return JsonResponse({"ok": True, "message": {
        "id": msg.pk, "name": msg.anonymous_name, "text": msg.message,
        "type": msg.message_type, "mine": True, "ai": False,
        "time": msg.created_at.strftime("%H:%M"),
    }})


@require_POST
def change_name(request, code):
    room_obj = get_object_or_404(Room, code=code.upper(), is_active=True)
    key = f"communinity-name-change:{_session_token(request)}"
    if cache.get(key): return JsonResponse({"error": "You can change your name again later."}, status=429)
    name, _ = _identity(request, room_obj, change=True); cache.set(key, True, 60)
    return JsonResponse({"name": name})


@require_POST
def leave(request, code):
    room_obj = get_object_or_404(Room, code=code.upper(), is_active=True)
    name, session_id = _identity(request, room_obj)
    joined_key = f"communinity_joined_{room_obj.code}"
    if request.session.pop(joined_key, False):
        Message.objects.create(room=room_obj, anonymous_name=name, session_id=session_id,
                               message=f"{name} disappeared into the wilderness.", message_type="system")
    return JsonResponse({"ok": True})
