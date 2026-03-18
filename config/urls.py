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
    path("update/", include("update.urls")),
    path("poketmoncard/", include("poketmoncard.urls")),
    path("pikmin/", include("pikmin.urls")),
    path("editpdf/", include("editpdf.urls")),
    path("spilitpdf/", include("spilitpdf.urls")),
    path("mergepdf/", include("mergepdf.urls")),
    path("pdf/", include("pdf.urls")),
    path("qna/", include("qna.urls")),
    path("humor/", include("humor.urls")),
    path("boardb/", include("boardb.urls")),
    path("boarda/", include("boarda.urls")),
    path("common/", include("common.urls")),
    path("pyxel/", include("pyxel.urls")),
    path("user/", include("user.urls")),
]

# media files (development)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)