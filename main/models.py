from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class LemonSubscription(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="lemon_sub",
    )

    customer_id = models.CharField(max_length=120, blank=True, default="")
    subscription_id = models.CharField(max_length=120, blank=True, default="")

    status = models.CharField(max_length=40, blank=True, default="", db_index=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    # 기존 관리자 해제 / 추가 턴 유지
    admin_unlocked = models.BooleanField(default=False)
    extra_daily_quota = models.IntegerField(default=0)

    def is_active(self):
        if self.admin_unlocked:
            return True

        status = (self.status or "").strip().lower()
        if status not in ("active", "on_trial"):
            return False

        if not self.current_period_end:
            return True

        return self.current_period_end > timezone.now()

    def __str__(self):
        return f"LemonSubscription(user={self.user_id}, status={self.status})"


class DailyUsage(models.Model):
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        db_index=True,
    )
    guest_id = models.CharField(max_length=80, null=True, blank=True, db_index=True)

    date = models.DateField(default=timezone.localdate, db_index=True)
    plays = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(user__isnull=False) & Q(guest_id__isnull=True)) |
                    (Q(user__isnull=True) & Q(guest_id__isnull=False) & ~Q(guest_id=""))
                ),
                name="ck_dailyusage_user_xor_guest",
            ),
            models.UniqueConstraint(
                fields=["user", "date"],
                name="uniq_dailyusage_user_date",
                condition=Q(user__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["guest_id", "date"],
                name="uniq_dailyusage_guest_date",
                condition=Q(user__isnull=True) & Q(guest_id__isnull=False) & ~Q(guest_id=""),
            ),
        ]
        indexes = [
            models.Index(fields=["date", "user"]),
            models.Index(fields=["date", "guest_id"]),
        ]

    def __str__(self):
        who = f"user:{self.user_id}" if self.user_id else f"guest:{self.guest_id}"
        return f"DailyUsage({who}, {self.date}, plays={self.plays})"


class UserTurnBonus(models.Model):
    """
    관리자 개별 지급용.
    예:
    - 특정 유저에게 +3턴
    - 보상 이벤트로 특정 유저만 +5턴
    - 기간 한정 추가 턴
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="turn_bonuses",
        db_index=True,
    )

    title = models.CharField(max_length=120, blank=True, default="")
    bonus_turns = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True, db_index=True)

    start_at = models.DateTimeField(null=True, blank=True, db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "start_at", "end_at"]),
        ]
        ordering = ["-created_at"]

    def is_valid_now(self):
        now = timezone.now()

        if not self.is_active:
            return False
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        return True

    def __str__(self):
        return f"UserTurnBonus(user={self.user_id}, bonus={self.bonus_turns}, active={self.is_active})"


class GlobalTurnEvent(models.Model):
    """
    전체 유저 / 로그인 유저 / 유료 유저 대상 전역 턴 이벤트.
    예:
    - 전체 유저 +2턴
    - 로그인 유저만 +3턴
    - 유료 유저만 +5턴
    """
    title = models.CharField(max_length=120)
    bonus_turns = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True, db_index=True)

    start_at = models.DateTimeField(null=True, blank=True, db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)

    members_only = models.BooleanField(default=False)
    paid_only = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "start_at", "end_at"]),
        ]
        ordering = ["-created_at"]

    def is_valid_now(self):
        now = timezone.now()

        if not self.is_active:
            return False
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        return True

    def applies_to(self, *, is_authed: bool, is_paid: bool):
        if not self.is_valid_now():
            return False

        if self.members_only and not is_authed:
            return False

        if self.paid_only and not is_paid:
            return False

        return True

    def __str__(self):
        return f"GlobalTurnEvent(title={self.title}, bonus={self.bonus_turns}, active={self.is_active})"


class LeaderboardEntry(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="leaderboard_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    final_capital = models.FloatField(default=0)

    score_total = models.IntegerField(default=0, db_index=True)
    score_asset = models.IntegerField(default=0)
    score_risk = models.IntegerField(default=0)

    turns_used = models.IntegerField(default=0)
    max_lev = models.IntegerField(default=1)
    max_bet_pct = models.IntegerField(default=0)
    event_turns = models.IntegerField(default=0)
    dangerous_exposures = models.IntegerField(default=0)
    timeouts = models.IntegerField(default=0)

    nickname_snapshot = models.CharField(max_length=50, blank=True, default="")
    login_id_snapshot = models.CharField(max_length=255, blank=True, default="")
    provider_snapshot = models.CharField(max_length=30, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["score_total", "final_capital", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]
        ordering = ["-score_total", "-final_capital", "-created_at"]

    def __str__(self):
        return f"LeaderboardEntry(user={self.user_id}, cap={self.final_capital})"