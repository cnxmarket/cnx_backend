# marketdata/views_profile.py
from rest_framework import generics, permissions, views, status
from rest_framework.response import Response
from .serializers_profile import MeSerializer, ChangePasswordSerializer

class MeView(generics.RetrieveUpdateAPIView):
    """
    GET /api/me/        -> profile payload
    PATCH /api/me/      -> update first_name, last_name (later: avatar via separate endpoint)
    """
    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    # If later you want to accept avatar in multipart, switch parsers and update the profile model accordingly.


class ChangePasswordView(views.APIView):
    """
    POST /api/me/change_password/ {old_password, new_password}
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = ChangePasswordSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)
