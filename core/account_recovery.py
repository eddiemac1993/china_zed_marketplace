from django.contrib.auth import get_user_model
from django.contrib.auth.views import PasswordResetView
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit


def masked_email(email):
    local, separator, domain = email.strip().rpartition('@')
    if not separator or not local or not domain:
        return None
    return local[0] + '••••@' + domain


class AccountPasswordResetView(PasswordResetView):
    @method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=False))
    def post(self, request, *args, **kwargs):
        if getattr(request, 'limited', False):
            context = self.get_context_data(form=self.form_class())
            context['email_hint_error'] = 'Too many attempts. Please wait a minute and try again.'
            return self.render_to_response(context, status=429)
        if request.POST.get('action') != 'email_hint':
            return super().post(request, *args, **kwargs)
        username = request.POST.get('username', '').strip()
        hint = None
        if username and len(username) <= 150:
            users = list(get_user_model().objects.filter(username__iexact=username, is_active=True)[:2])
            if len(users) == 1 and users[0].has_usable_password():
                hint = masked_email(users[0].email)
        context = self.get_context_data(form=self.form_class())
        context['recovery_username'] = username[:150]
        context['email_hint'] = hint
        if not hint:
            context['email_hint_error'] = 'We could not show an email hint. Check your username or contact support for help recovering your account.'
        return self.render_to_response(context)
