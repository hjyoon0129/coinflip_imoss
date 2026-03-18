from django.urls import path
from .views import base_views

app_name = "main"

urlpatterns = [
    # home
    path("", base_views.home, name="home"),
    path("subscribe/", base_views.subscribe, name="subscribe"),

    # pages
    path("coinflip/", base_views.coinflip_page, name="coinflip"),

    # usage lock
    path("api/can-play/", base_views.api_can_play, name="api_can_play"),
    path("api/consume-play/", base_views.api_consume_play, name="api_consume_play"),

    # leaderboard
    path("api/leaderboard/", base_views.api_leaderboard, name="api_leaderboard"),
    path(
        "api/leaderboard/weekly-best/",
        base_views.api_leaderboard_weekly_best,
        name="api_leaderboard_weekly_best",
    ),
    path(
        "api/leaderboard/my-rank/",
        base_views.api_my_rank_weekly_best,
        name="api_my_rank_weekly_best",
    ),

    # score submit
    path("api/submit-score/", base_views.api_submit_score, name="api_submit_score"),

    # lemon squeezy
    path(
        "api/lemon/create-checkout-session/",
        base_views.api_create_checkout_session,
        name="lemon_create_checkout",
    ),
    path("lemon/webhook/", base_views.lemon_webhook, name="lemon_webhook"),

    # capital
    path("api/adjust-capital/", base_views.api_adjust_capital, name="api_adjust_capital"),
]