from django.db import transaction
from django.utils import timezone

from main.models import DailyUsage, LemonSubscription

FREE_DAILY_LIMIT = 3
PAID_DAILY_LIMIT = 10


def _get_guest_key(request) -> str:
    """
    GuestIdMiddleware가 있으면 request.guest_id 사용,
    없으면 세션키 fallback
    """
    guest_id = getattr(request, "guest_id", None)
    if guest_id:
        return str(guest_id)

    if not request.session.session_key:
        request.session.create()

    return request.session.session_key or "anon"


def get_limits_for_request(request):
    """
    return (quota, is_paid, can_override_unlimited)
    """
    user = request.user if request.user.is_authenticated else None

    is_paid = False
    can_override_unlimited = False

    if user:
        try:
            sub = LemonSubscription.objects.get(user=user)
            is_paid = sub.is_active()
            can_override_unlimited = bool(sub.admin_unlocked)
        except LemonSubscription.DoesNotExist:
            is_paid = False
            can_override_unlimited = False

    if can_override_unlimited:
        return (10_000_000, is_paid, True)

    if is_paid:
        return (PAID_DAILY_LIMIT, True, False)

    return (FREE_DAILY_LIMIT, False, False)


def get_usage_today(request):
    today = timezone.localdate()

    if request.user.is_authenticated:
        obj, _ = DailyUsage.objects.get_or_create(
            date=today,
            user=request.user,
            defaults={"plays": 0, "guest_id": None},
        )
    else:
        guest_id = _get_guest_key(request)
        obj, _ = DailyUsage.objects.get_or_create(
            date=today,
            guest_id=guest_id,
            defaults={"plays": 0, "user": None},
        )

    return obj


@transaction.atomic
def consume_one_play(request):
    """
    서버 강제 플레이 차감. 성공 시:
    (ok, quota, remaining, is_paid, is_override)
    """
    quota, is_paid, is_override = get_limits_for_request(request)
    usage = get_usage_today(request)

    if usage.plays >= quota:
        return (False, quota, 0, is_paid, is_override)

    usage.plays += 1
    usage.save(update_fields=["plays"])

    remaining = max(0, quota - usage.plays)
    return (True, quota, remaining, is_paid, is_override)


