# marketdata/auth_backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class UsernameOrEmailBackend(ModelBackend):
    """
    Authenticate with either username OR email + password.
    Works with the default auth.User (no custom user model needed).
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        # "username" will carry either the username or the email
        identifier = kwargs.get("identifier") or kwargs.get("email") or username
        if not identifier or not password:
            return None

        user = None
        # Try username match first
        try:
            user = User.objects.get(username=identifier)
        except User.DoesNotExist:
            # Fall back to email (case-insensitive)
            try:
                user = User.objects.get(email__iexact=identifier)
            except User.DoesNotExist:
                return None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
