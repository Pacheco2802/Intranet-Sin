from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            return None
        try:
            user = UserModel.objects.get(email__iexact=username)
        except UserModel.DoesNotExist:
            # Roda um hash "dummy" para igualar o tempo de resposta e evitar
            # enumeração de usuários por timing (mesmo comportamento do ModelBackend).
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # E-mails duplicados por diferença de caixa: usa o mais antigo, de forma determinística.
            user = UserModel.objects.filter(email__iexact=username).order_by('pk').first()
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
