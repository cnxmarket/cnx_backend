from django.contrib import admin
from django.urls import path, include
from marketdata.views import (
    health,
    candles,
    symbols,
    PositionsSnapshotView,
    SimFillView,
    ClosePositionView,
    OrderListView,
    FillListView,
    MarginCheckView,
    ExitPositionAPIView,
    CapitalView,
    OrderHistoryView
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from marketdata.views_admintrades import MyAdminTradesViewSet
from marketdata.views_kyc import RegisterView, KYCSubmitView, KYCStatusView, KYCSubmitPublicView
from marketdata.auth_views import KycTokenObtainPairView
from marketdata.auth_views import LogoutView
from marketdata.views_profile import MeView, ChangePasswordView


router = DefaultRouter()
router.register(r"api/admin_trades", MyAdminTradesViewSet, basename="admin_trades")

urlpatterns = [
    path("admin/", admin.site.urls),  # Add Django admin URL here

    path("health", health),
    path("api/candles", candles),
    path("api/orders", OrderListView.as_view()),
    path("api/fills", FillListView.as_view()),
    path('api/orderhistory/', OrderHistoryView.as_view(), name='order-history'),
    path("api/symbols", symbols),
    path('api/capital/', CapitalView.as_view(), name='capital'),
    path("api/positions/snapshot", PositionsSnapshotView.as_view()),
    path("api/sim/fill", SimFillView.as_view()),
    path("api/positions/close", ClosePositionView.as_view()),
    path("api/margin/check", MarginCheckView.as_view(), name="margin-check"),
    path("api/exit_position/", ExitPositionAPIView.as_view(), name='exit_position'),
    # JWT endpoints
    path("api/auth/login/", KycTokenObtainPairView.as_view(), name="login"),
    path("api/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("api/me/", MeView.as_view(), name="me"),
    path("api/me/change_password/", ChangePasswordView.as_view(), name="me-change-password"),

    path("api/auth/register/", RegisterView.as_view()),
    path("api/kyc/submit/", KYCSubmitView.as_view()),
    path("api/kyc/status/", KYCStatusView.as_view()),
    path("api/kyc/submit_public/", KYCSubmitPublicView.as_view()),
    path("api/", include("payments.urls")),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)  + router.urls
