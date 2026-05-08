"""URL configuration for the PS module project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ps/api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("ps/api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("ps/api/", include("psmodule.api.urls")),
    path("ps/api/", include("psmodule.department_stock.api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
