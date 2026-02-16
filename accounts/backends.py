from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()

        try:
            user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            if user.role == 'ADMIN':
                return user

            if user.is_approved:
                return user

        return None


class ApprovedUserBackend(ModelBackend):
    def user_can_authenticate(self, user):
        is_active = super().user_can_authenticate(user)
        return is_active and user.is_approved