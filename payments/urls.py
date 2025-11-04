from django.urls import path
from .views import CryptoMethodListView, CreateUpiRequestView, MyUpiDepositRequestListView

urlpatterns = [
    path("deposit/crypto-methods/", CryptoMethodListView.as_view(), name="crypto-methods"),
    path("deposit/upi/request/", CreateUpiRequestView.as_view(), name="upi-request"),
    path("deposit/upi/requests/", MyUpiDepositRequestListView.as_view(), name="upi-requests-list"),
]
