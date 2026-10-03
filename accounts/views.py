from rest_framework import generics, permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class MeView(APIView):
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)
