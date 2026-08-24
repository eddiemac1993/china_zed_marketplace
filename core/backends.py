from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate legacy usernames and new email-first accounts."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        login = (username or kwargs.get("email") or "").strip()
        if not login or password is None:
            return None

        UserModel = get_user_model()
        try:
            user = UserModel._default_manager.get(
                Q(username__iexact=login) | Q(email__iexact=login)
            )
        except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
