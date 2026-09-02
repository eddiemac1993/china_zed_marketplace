from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Message, MessageReport, MessageReaction, Room
from .services.ai_chat import generate_reply

@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class CommuninityTests(TestCase):
    def test_create_join_and_invalid_room(self):
        response=self.client.post(reverse("communinity:create")); self.assertEqual(response.status_code,302)
        room=Room.objects.filter(room_type="private").get(); self.assertEqual(len(room.code),5)
        self.assertEqual(self.client.post(reverse("communinity:join"),{"code":room.code}).status_code,302)
        self.assertEqual(self.client.post(reverse("communinity:join"),{"code":"NOPE1"}).status_code,404)
    def test_name_persists_and_message_validation(self):
        room=Room.objects.create(); url=reverse("communinity:room",args=[room.code])
        self.client.get(url); name=self.client.session[f"communinity_name_{room.code}"]
        self.client.get(url); self.assertEqual(name,self.client.session[f"communinity_name_{room.code}"])
        self.assertEqual(self.client.post(reverse("communinity:send",args=[room.code]),{"message":""}).status_code,400)
        self.assertEqual(self.client.post(reverse("communinity:send",args=[room.code]),{"message":"hello"}).status_code,200)
    @override_settings(COMMUNINITY_AI_ENABLED=False)
    def test_ai_disabled(self):
        room=Room.objects.create(); self.client.get(reverse("communinity:room",args=[room.code]))
        with patch("communinity.views.maybe_add_ai_message") as fn:
            self.client.post(reverse("communinity:send",args=[room.code]),{"message":"hello"}); fn.assert_called_once()

    def test_two_sessions_and_rate_limit(self):
        room=Room.objects.create(); other=self.client_class()
        self.client.get(reverse("communinity:room",args=[room.code])); other.get(reverse("communinity:room",args=[room.code]))
        self.assertNotEqual(self.client.session.session_key, other.session.session_key)
        send_url=reverse("communinity:send",args=[room.code])
        self.assertEqual(self.client.post(send_url,{"message":"one"}).status_code,200)
        self.assertEqual(self.client.post(send_url,{"message":"one"}).status_code,429)

    def test_public_rooms_require_login_and_support_reactions_and_reports(self):
        room=Room.objects.create(code="PUB01",title="Public",room_type="public")
        send_url=reverse("communinity:send",args=[room.code])
        self.assertEqual(self.client.post(send_url,{"message":"hello"}).status_code,403)
        user=User.objects.create_user(username="community-user",password="pass")
        self.client.force_login(user)
        self.assertEqual(self.client.post(send_url,{"message":"hello"}).status_code,200)
        message=Message.objects.get(room=room,message="hello")
        other=User.objects.create_user(username="community-other",password="pass")
        self.client.force_login(other)
        react=reverse("communinity:react",args=[room.code,message.id])
        report=reverse("communinity:report",args=[room.code,message.id])
        self.assertEqual(self.client.post(react,{"reaction":"interested"}).status_code,200)
        self.assertEqual(self.client.post(report,{"reason":"Check this"}).status_code,200)
        self.assertTrue(MessageReaction.objects.filter(message=message,user=other).exists())
        self.assertTrue(MessageReport.objects.filter(message=message,user=other).exists())

    @override_settings(COMMUNINITY_AI_ENABLED=True)
    @patch("communinity.services.ai_chat.requests.post", side_effect=TimeoutError)
    @patch.dict("os.environ", {"OPENAI_API_KEY":"test"})
    def test_ai_api_failure_uses_fallback(self, _request):
        room=Room.objects.create()
        self.assertTrue(generate_reply(room))
