from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    # Google login (django-allauth)
    path("accounts/", include("allauth.urls")),

    # main
    path("", include("main.urls")),

    # tools / apps
    path("arena/", include("arena.urls")),
    path("common/", include("common.urls")),
    path("user/", include("user.urls")),
]

# media files (development)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)