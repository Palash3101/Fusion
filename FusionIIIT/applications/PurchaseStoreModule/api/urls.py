from django.urls import include, path
from rest_framework.routers import DefaultRouter

from psmodule.api.views import IndentViewSet, MeViewSet, StockCheckView

router = DefaultRouter()
router.register(r"indents", IndentViewSet, basename="indent")
router.register(r"me", MeViewSet, basename="me")

urlpatterns = [
    path("", include(router.urls)),
    path("stock/check/<int:item_id>/", StockCheckView.as_view(), name="stock_check"),
]
