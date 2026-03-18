from django.urls import path

from . import views

app_name = "user"

urlpatterns = [
    path("edit-nickname/", views.edit_nickname, name="edit_nickname"),
    path("save-nickname/", views.save_nickname, name="save_nickname"),

    path("api/me/", views.api_me, name="api_me"),
    path("api/set-nickname/", views.api_set_nickname, name="api_set_nickname"),
]