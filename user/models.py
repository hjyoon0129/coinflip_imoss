from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    nickname = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        default="",
    )
    nickname_changed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.nickname or self.user.username

    def has_nickname(self):
        return bool((self.nickname or "").strip())

    def can_change_nickname(self):
        """
        First-time nickname setup: always allowed.
        After that: once every 30 days.
        """
        if not self.has_nickname():
            return True

        if not self.nickname_changed_at:
            return True

        return timezone.now() >= self.nickname_changed_at + timedelta(days=30)

    def next_nickname_change_at(self):
        if not self.nickname_changed_at:
            return None
        return self.nickname_changed_at + timedelta(days=30)

    def days_until_nickname_change(self):
        if self.can_change_nickname():
            return 0

        next_time = self.next_nickname_change_at()
        if not next_time:
            return 0

        delta = next_time - timezone.now()
        return max(1, delta.days + (1 if delta.seconds > 0 else 0))