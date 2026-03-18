from django.contrib import admin
from .models import (
    LemonSubscription,
    DailyUsage,
    LeaderboardEntry,
    UserTurnBonus,
    GlobalTurnEvent,
)


@admin.register(LemonSubscription)
class LemonSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "status",
        "current_period_end",
        "admin_unlocked",
        "extra_daily_quota",
    )
    list_filter = (
        "status",
        "admin_unlocked",
    )
    search_fields = (
        "user__username",
        "user__email",
        "customer_id",
        "subscription_id",
    )


@admin.register(DailyUsage)
class DailyUsageAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "guest_id",
        "date",
        "plays",
    )
    list_filter = (
        "date",
    )
    search_fields = (
        "user__username",
        "user__email",
        "guest_id",
    )
    date_hierarchy = "date"


@admin.register(UserTurnBonus)
class UserTurnBonusAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "title",
        "bonus_turns",
        "is_active",
        "start_at",
        "end_at",
        "created_at",
    )
    list_filter = (
        "is_active",
        "start_at",
        "end_at",
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "title",
    )
    autocomplete_fields = ("user",)


@admin.register(GlobalTurnEvent)
class GlobalTurnEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "bonus_turns",
        "is_active",
        "members_only",
        "paid_only",
        "start_at",
        "end_at",
        "created_at",
    )
    list_filter = (
        "is_active",
        "members_only",
        "paid_only",
        "start_at",
        "end_at",
        "created_at",
    )
    search_fields = (
        "title",
    )


@admin.register(LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "nickname_snapshot",
        "final_capital",
        "score_total",
        "turns_used",
        "max_lev",
        "max_bet_pct",
        "created_at",
    )
    list_filter = (
        "created_at",
        "provider_snapshot",
    )
    search_fields = (
        "user__username",
        "user__email",
        "nickname_snapshot",
        "login_id_snapshot",
    )
    date_hierarchy = "created_at"