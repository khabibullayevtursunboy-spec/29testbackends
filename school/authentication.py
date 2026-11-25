from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import User
class SchoolJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        uid=validated_token.get('uid')
        try:return User.objects.get(id=uid,is_active=True)
        except User.DoesNotExist:raise AuthenticationFailed('Foydalanuvchi topilmadi yoki bloklangan.')
