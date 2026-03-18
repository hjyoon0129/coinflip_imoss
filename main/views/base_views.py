import hashlib
import hmac
import json
import uuid
from datetime import date, timedelta
from urllib import error as urlerror
from urllib import request as urlrequest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction, models
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from ..models import (
    DailyUsage,
    LemonSubscription,
    LeaderboardEntry,
    UserTurnBonus,
    GlobalTurnEvent,
)


FREE_DAILY_LIMIT = 3
PRO_DAILY_LIMIT = 10
PRO_PLUS_DAILY_LIMIT = 30

LEMON_API_BASE = "https://api.lemonsqueezy.com/v1"
GUEST_COOKIE_NAME = "guest_id"


# ========= guest helpers =========
def ensure_guest_id(request) -> str:
    gid = getattr(request, "guest_id", None)
    if gid:
        return str(gid).strip()

    gid = request.COOKIES.get(GUEST_COOKIE_NAME, "")
    gid = str(gid).strip()
    if gid:
        return gid

    return uuid.uuid4().hex


def attach_guest_cookie_if_needed(request, response, gid: str):
    if request.user.is_authenticated:
        return response

    existing = request.COOKIES.get(GUEST_COOKIE_NAME, "")
    if not existing:
        response.set_cookie(
            GUEST_COOKIE_NAME,
            gid,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax",
        )
    return response


# ========= nickname / user helpers =========
def get_user_display_name(user) -> str:
    if not user:
        return "Unknown"

    try:
        profile = user.profile
        nickname = str(getattr(profile, "nickname", "") or "").strip()
        if nickname:
            return nickname
    except ObjectDoesNotExist:
        pass
    except AttributeError:
        pass

    username = str(getattr(user, "username", "") or "").strip()
    if username:
        return username

    email = str(getattr(user, "email", "") or "").strip()
    if email and "@" in email:
        return email.split("@", 1)[0]

    user_id = getattr(user, "id", None)
    if user_id:
        return f"user{user_id}"

    return "Unknown"


def get_user_login_id(user) -> str:
    if not user:
        return ""

    email = str(getattr(user, "email", "") or "").strip()
    if email:
        return email

    username = str(getattr(user, "username", "") or "").strip()
    if username:
        return username

    return ""


def get_user_provider(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return "guest"

    try:
        if user.socialaccount_set.filter(provider="google").exists():
            return "google"
    except Exception:
        pass

    return "local"


def user_needs_nickname(user) -> bool:
    if not user or not user.is_authenticated:
        return False

    try:
        profile = user.profile
        return not bool((profile.nickname or "").strip())
    except ObjectDoesNotExist:
        return True
    except AttributeError:
        return True


# ========= subscription / quota helpers =========
def _get_or_create_subscription_for_user(user):
    sub, _ = LemonSubscription.objects.get_or_create(user=user)
    return sub


def get_used_plays(request, today: date) -> int:
    if request.user.is_authenticated:
        row = DailyUsage.objects.filter(user=request.user, date=today).first()
    else:
        gid = ensure_guest_id(request)
        row = DailyUsage.objects.filter(guest_id=gid, date=today).first()
    return int(row.plays) if row else 0


def inc_used_plays_atomic(request, today: date) -> int:
    if request.user.is_authenticated:
        with transaction.atomic():
            obj, _ = DailyUsage.objects.select_for_update().get_or_create(
                user=request.user,
                date=today,
                defaults={"plays": 0, "guest_id": None},
            )
            obj.plays = int(obj.plays or 0) + 1
            obj.save(update_fields=["plays"])
            return int(obj.plays)

    gid = ensure_guest_id(request)
    with transaction.atomic():
        obj, _ = DailyUsage.objects.select_for_update().get_or_create(
            guest_id=gid,
            date=today,
            defaults={"plays": 0, "user": None},
        )
        obj.plays = int(obj.plays or 0) + 1
        obj.save(update_fields=["plays"])
        return int(obj.plays)


def get_subscription_plan(sub) -> str:
    """
    return: free / pro / pro_plus
    """
    if not sub:
        return "free"

    try:
        is_active = bool(sub.is_active())
    except Exception:
        is_active = False

    if not is_active:
        return "free"

    variant_id = str(getattr(sub, "variant_id", "") or "").strip()

    pro_variant_id = str(getattr(settings, "LEMON_SQUEEZY_PRO_VARIANT_ID", "") or "").strip()
    pro_plus_variant_id = str(getattr(settings, "LEMON_SQUEEZY_PRO_PLUS_VARIANT_ID", "") or "").strip()

    if variant_id and pro_plus_variant_id and variant_id == pro_plus_variant_id:
        return "pro_plus"

    if variant_id and pro_variant_id and variant_id == pro_variant_id:
        return "pro"

    legacy_variant_id = str(getattr(settings, "LEMON_SQUEEZY_VARIANT_ID", "") or "").strip()
    if variant_id and legacy_variant_id and variant_id == legacy_variant_id:
        return "pro"

    return "pro"


def get_base_daily_limit(*, plan: str) -> int:
    if plan == "pro_plus":
        return PRO_PLUS_DAILY_LIMIT
    if plan == "pro":
        return PRO_DAILY_LIMIT
    return FREE_DAILY_LIMIT


def get_user_turn_bonus_sum(user) -> int:
    if not user or not getattr(user, "is_authenticated", False):
        return 0

    now = timezone.now()

    qs = UserTurnBonus.objects.filter(
        user=user,
        is_active=True,
    ).filter(
        models.Q(start_at__isnull=True) | models.Q(start_at__lte=now)
    ).filter(
        models.Q(end_at__isnull=True) | models.Q(end_at__gte=now)
    )

    total = 0
    for row in qs.only("bonus_turns"):
        total += max(0, int(row.bonus_turns or 0))
    return total


def get_global_event_bonus_sum(*, is_authed: bool, is_paid: bool) -> int:
    now = timezone.now()

    qs = GlobalTurnEvent.objects.filter(
        is_active=True,
    ).filter(
        models.Q(start_at__isnull=True) | models.Q(start_at__lte=now)
    ).filter(
        models.Q(end_at__isnull=True) | models.Q(end_at__gte=now)
    )

    total = 0
    for row in qs.only("bonus_turns", "members_only", "paid_only"):
        if row.members_only and not is_authed:
            continue
        if row.paid_only and not is_paid:
            continue
        total += max(0, int(row.bonus_turns or 0))
    return total


def get_daily_limit_components(request) -> dict:
    is_authed = request.user.is_authenticated

    is_paid = False
    admin_unlocked = False
    subscription_extra = 0
    plan = "free"

    if is_authed:
        sub = _get_or_create_subscription_for_user(request.user)
        admin_unlocked = bool(getattr(sub, "admin_unlocked", False))
        subscription_extra = int(getattr(sub, "extra_daily_quota", 0) or 0)

        try:
            is_paid = bool(sub.is_active())
        except Exception:
            is_paid = False

        plan = get_subscription_plan(sub)

    base_limit = get_base_daily_limit(plan=plan)

    if admin_unlocked:
        final_limit = 10_000_000
        return {
            "is_authed": is_authed,
            "is_paid": is_paid,
            "plan": plan,
            "admin_unlocked": True,
            "base_limit": int(base_limit),
            "subscription_extra": int(subscription_extra),
            "user_bonus": 0,
            "global_event_bonus": 0,
            "daily_limit": int(final_limit),
        }

    user_bonus = get_user_turn_bonus_sum(request.user) if is_authed else 0
    global_event_bonus = get_global_event_bonus_sum(
        is_authed=is_authed,
        is_paid=is_paid,
    )

    final_limit = (
        int(base_limit)
        + max(0, int(subscription_extra))
        + max(0, int(user_bonus))
        + max(0, int(global_event_bonus))
    )

    return {
        "is_authed": is_authed,
        "is_paid": is_paid,
        "plan": plan,
        "admin_unlocked": False,
        "base_limit": int(base_limit),
        "subscription_extra": int(subscription_extra),
        "user_bonus": int(user_bonus),
        "global_event_bonus": int(global_event_bonus),
        "daily_limit": int(final_limit),
    }


def build_game_ctx(request) -> dict:
    today = timezone.localdate()
    limit_info = get_daily_limit_components(request)

    used = get_used_plays(request, today)
    limit = int(limit_info["daily_limit"])
    remaining = max(0, limit - used)

    return {
        "is_authed": limit_info["is_authed"],
        "is_paid": limit_info["is_paid"],
        "plan": limit_info["plan"],
        "daily_limit": int(limit),
        "daily_used": int(used),
        "daily_remaining": int(remaining),
        "can_play": bool(limit_info["admin_unlocked"] or remaining > 0),
        "admin_unlocked": bool(limit_info["admin_unlocked"]),
        "base_limit": int(limit_info["base_limit"]),
        "extra_daily_quota": int(limit_info["subscription_extra"]),
        "user_bonus_turns": int(limit_info["user_bonus"]),
        "global_event_bonus_turns": int(limit_info["global_event_bonus"]),
        "needs_nickname": user_needs_nickname(request.user),
        "display_name": get_user_display_name(request.user) if limit_info["is_authed"] else "",
        "lemon_checkout_enabled": bool(
            getattr(settings, "LEMON_SQUEEZY_API_KEY", "")
            and getattr(settings, "LEMON_SQUEEZY_STORE_ID", "")
            and (
                getattr(settings, "LEMON_SQUEEZY_PRO_VARIANT_ID", "")
                or getattr(settings, "LEMON_SQUEEZY_PRO_PLUS_VARIANT_ID", "")
                or getattr(settings, "LEMON_SQUEEZY_VARIANT_ID", "")
            )
        ),
    }


# ========= date / leaderboard helpers =========
def week_start_local(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _week_range(d: date):
    ws = week_start_local(d)
    we = ws + timedelta(days=7)
    return ws, we


def get_tier_by_capital(final_capital: float) -> str:
    c = float(final_capital or 0)

    if c >= 60000:
        return "CHALLENGER"
    if c >= 30000:
        return "MASTER"
    if c >= 15000:
        return "DIAMOND"
    if c >= 7000:
        return "PLATINUM"
    if c >= 3000:
        return "GOLD"
    if c >= 1500:
        return "SILVER"
    return "BRONZE"


def _get_weekly_latest_row_for_update(user, ws: date, we: date):
    return (
        LeaderboardEntry.objects
        .select_for_update()
        .filter(user=user, created_at__date__gte=ws, created_at__date__lt=we)
        .order_by("-created_at", "-id")
        .first()
    )


def _weekly_latest_per_user(limit=None):
    today = timezone.localdate()
    ws, we = _week_range(today)

    qs = (
        LeaderboardEntry.objects
        .select_related("user")
        .filter(created_at__date__gte=ws, created_at__date__lt=we)
        .order_by("-created_at", "-id")
    )

    latest_map = {}
    for e in qs:
        if e.user_id not in latest_map:
            latest_map[e.user_id] = e

    latest_entries = list(latest_map.values())
    latest_entries.sort(
        key=lambda x: (
            float(x.final_capital or 0),
            -(x.created_at.timestamp() if x.created_at else 0),
        ),
        reverse=True,
    )

    if limit is not None:
        latest_entries = latest_entries[:limit]

    return ws, latest_entries


# ========= Lemon Squeezy helpers =========
def _lemon_headers() -> dict:
    api_key = getattr(settings, "LEMON_SQUEEZY_API_KEY", "")
    return {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {api_key}",
    }


def _lemon_api_request(path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    url = f"{LEMON_API_BASE}{path}"
    body = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urlrequest.Request(
        url=url,
        data=body,
        method=method,
        headers=_lemon_headers(),
    )

    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"message": raw or str(e)}
        raise RuntimeError(parsed)
    except Exception as e:
        raise RuntimeError(str(e))


def _parse_ls_datetime(value):
    if not value:
        return None
    try:
        return timezone.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _verify_lemon_signature(raw_body: bytes, signature_hex: str, secret: str) -> bool:
    if not raw_body or not signature_hex or not secret:
        return False

    digest = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(digest, signature_hex)


def _resolve_user_for_webhook(payload: dict):
    meta = payload.get("meta") or {}
    custom_data = meta.get("custom_data") or {}
    user_id = custom_data.get("user_id")

    UserModel = get_user_model()

    if user_id:
        try:
            return UserModel.objects.filter(id=int(user_id)).first()
        except Exception:
            pass

    attrs = (payload.get("data") or {}).get("attributes") or {}
    email = (attrs.get("user_email") or "").strip()
    if email:
        return UserModel.objects.filter(email__iexact=email).first()

    return None


def _save_subscription_from_webhook(*, user, payload: dict):
    if not user:
        return

    attrs = (payload.get("data") or {}).get("attributes") or {}
    sub_id = str((payload.get("data") or {}).get("id") or "").strip()
    customer_id = str(attrs.get("customer_id") or "").strip()
    status = str(attrs.get("status") or "").strip().lower()

    renews_at = _parse_ls_datetime(attrs.get("renews_at"))
    ends_at = _parse_ls_datetime(attrs.get("ends_at"))
    trial_ends_at = _parse_ls_datetime(attrs.get("trial_ends_at"))

    variant_id = ""
    variant_rel = (((payload.get("data") or {}).get("relationships") or {}).get("variant") or {}).get("data") or {}
    if variant_rel:
        variant_id = str(variant_rel.get("id") or "").strip()

    rec = _get_or_create_subscription_for_user(user)
    rec.customer_id = customer_id or getattr(rec, "customer_id", "")
    rec.subscription_id = sub_id or getattr(rec, "subscription_id", "")
    rec.status = status or getattr(rec, "status", "")
    rec.current_period_end = renews_at or trial_ends_at or ends_at

    if hasattr(rec, "variant_id"):
        rec.variant_id = variant_id or getattr(rec, "variant_id", "")

    update_fields = [
        "customer_id",
        "subscription_id",
        "status",
        "current_period_end",
    ]
    if hasattr(rec, "variant_id"):
        update_fields.append("variant_id")

    rec.save(update_fields=update_fields)


# ========= pages =========
def home(request):
    ctx = build_game_ctx(request)
    resp = render(request, "main/question_list.html", ctx)

    if not request.user.is_authenticated:
        resp = attach_guest_cookie_if_needed(request, resp, ensure_guest_id(request))
    return resp


def index(request):
    return home(request)


@login_required
def subscribe(request):
    return redirect("main:coinflip")


def coinflip_page(request):
    ctx = build_game_ctx(request)
    resp = render(request, "main/question_list.html", ctx)

    if not request.user.is_authenticated:
        resp = attach_guest_cookie_if_needed(request, resp, ensure_guest_id(request))
    return resp


# ========= quota APIs =========
def api_can_play(request):
    ctx = build_game_ctx(request)
    resp = JsonResponse({
        "ok": bool(ctx["can_play"]),
        "used": ctx["daily_used"],
        "limit": ctx["daily_limit"],
        "remaining": ctx["daily_remaining"],
        "is_paid": ctx["is_paid"],
        "plan": ctx["plan"],
        "is_authed": ctx["is_authed"],
        "admin_unlocked": ctx["admin_unlocked"],
        "base_limit": ctx["base_limit"],
        "extra_daily_quota": ctx["extra_daily_quota"],
        "user_bonus_turns": ctx["user_bonus_turns"],
        "global_event_bonus_turns": ctx["global_event_bonus_turns"],
    })
    if not request.user.is_authenticated:
        resp = attach_guest_cookie_if_needed(request, resp, ensure_guest_id(request))
    return resp


def api_consume_play(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    today = timezone.localdate()
    ctx = build_game_ctx(request)

    used = int(ctx["daily_used"])
    limit = int(ctx["daily_limit"])

    if used >= limit:
        resp = JsonResponse(
            {
                "ok": False,
                "reason": "daily_limit",
                "used": used,
                "limit": limit,
                "remaining": 0,
            },
            status=403,
        )
        if not request.user.is_authenticated:
            resp = attach_guest_cookie_if_needed(request, resp, ensure_guest_id(request))
        return resp

    new_used = inc_used_plays_atomic(request, today)
    remaining = max(0, limit - new_used)

    resp = JsonResponse({
        "ok": True,
        "used": new_used,
        "limit": limit,
        "remaining": remaining,
    })
    if not request.user.is_authenticated:
        resp = attach_guest_cookie_if_needed(request, resp, ensure_guest_id(request))
    return resp


# ========= leaderboard =========
@login_required
def api_submit_score(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("bad json")

    final_capital = float(payload.get("final_capital", 0) or 0)
    turns_used = int(payload.get("turns_used", 0) or 0)
    max_lev = int(payload.get("max_lev", 0) or 0)
    max_bet_pct = int(payload.get("max_bet_pct", 0) or 0)
    event_turns = int(payload.get("event_turns", 0) or 0)
    dangerous = int(payload.get("dangerous_exposures", 0) or 0)
    timeouts = int(payload.get("timeouts", 0) or 0)

    nickname_snapshot = get_user_display_name(request.user)
    login_id_snapshot = get_user_login_id(request.user)
    provider_snapshot = get_user_provider(request.user)

    today = timezone.localdate()
    ws, we = _week_range(today)

    with transaction.atomic():
        cur = _get_weekly_latest_row_for_update(request.user, ws, we)

        if cur is None:
            saved = LeaderboardEntry.objects.create(
                user=request.user,
                nickname_snapshot=nickname_snapshot,
                login_id_snapshot=login_id_snapshot,
                provider_snapshot=provider_snapshot,
                final_capital=final_capital,
                score_asset=0,
                score_risk=0,
                score_total=0,
                turns_used=turns_used,
                max_lev=max_lev,
                max_bet_pct=max_bet_pct,
                event_turns=event_turns,
                dangerous_exposures=dangerous,
                timeouts=timeouts,
            )
        else:
            cur.nickname_snapshot = nickname_snapshot
            cur.login_id_snapshot = login_id_snapshot
            cur.provider_snapshot = provider_snapshot
            cur.final_capital = final_capital
            cur.score_asset = 0
            cur.score_risk = 0
            cur.score_total = 0
            cur.turns_used = turns_used
            cur.max_lev = max_lev
            cur.max_bet_pct = max_bet_pct
            cur.event_turns = event_turns
            cur.dangerous_exposures = dangerous
            cur.timeouts = timeouts
            cur.save(update_fields=[
                "nickname_snapshot",
                "login_id_snapshot",
                "provider_snapshot",
                "final_capital",
                "score_asset",
                "score_risk",
                "score_total",
                "turns_used",
                "max_lev",
                "max_bet_pct",
                "event_turns",
                "dangerous_exposures",
                "timeouts",
            ])
            saved = cur

    return JsonResponse({
        "ok": True,
        "week_start": str(ws),
        "final_capital": float(saved.final_capital),
        "tier": get_tier_by_capital(saved.final_capital),
        "nickname": saved.nickname_snapshot,
        "login_id": saved.login_id_snapshot,
        "provider": saved.provider_snapshot,
    })


def api_leaderboard_weekly_best(request):
    limit = int(request.GET.get("limit", 50))
    limit = max(1, min(200, limit))

    ws, latest_entries = _weekly_latest_per_user(limit=limit)
    me = request.user if request.user.is_authenticated else None

    rows = []
    for idx, e in enumerate(latest_entries, start=1):
        rows.append({
            "rank": idx,
            "username": e.nickname_snapshot or get_user_display_name(e.user),
            "login_id": e.login_id_snapshot or get_user_login_id(e.user),
            "provider": e.provider_snapshot or get_user_provider(e.user),
            "tier": get_tier_by_capital(e.final_capital),
            "final_capital": float(e.final_capital),
            "created_at": e.created_at.isoformat() if getattr(e, "created_at", None) else None,
            "is_me": bool(me and e.user_id == me.id),
        })

    return JsonResponse({
        "ok": True,
        "week_start": str(ws),
        "results": rows,
    })


@login_required
def api_my_rank_weekly_best(request):
    ws, latest_entries = _weekly_latest_per_user(limit=None)

    my_rank = None
    my_best = None

    for i, e in enumerate(latest_entries, start=1):
        if e.user_id == request.user.id:
            my_rank = i
            my_best = e
            break

    if not my_best:
        return JsonResponse({
            "ok": True,
            "week_start": str(ws),
            "has_score": False,
            "my_rank": None,
            "total_players": len(latest_entries),
            "my_best": None,
        })

    return JsonResponse({
        "ok": True,
        "week_start": str(ws),
        "has_score": True,
        "my_rank": my_rank,
        "total_players": len(latest_entries),
        "my_best": {
            "nickname": my_best.nickname_snapshot or get_user_display_name(request.user),
            "login_id": my_best.login_id_snapshot or get_user_login_id(request.user),
            "provider": my_best.provider_snapshot or get_user_provider(request.user),
            "tier": get_tier_by_capital(my_best.final_capital),
            "final_capital": float(my_best.final_capital),
            "created_at": my_best.created_at.isoformat() if getattr(my_best, "created_at", None) else None,
        },
    })


def api_leaderboard(request):
    return api_leaderboard_weekly_best(request)


# ========= Lemon Squeezy checkout =========
@login_required
def api_create_checkout_session(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    api_key = getattr(settings, "LEMON_SQUEEZY_API_KEY", "")
    store_id = getattr(settings, "LEMON_SQUEEZY_STORE_ID", "")
    site_url = getattr(settings, "SITE_URL", "")

    if not api_key:
        return HttpResponseBadRequest("missing LEMON_SQUEEZY_API_KEY")
    if not store_id:
        return HttpResponseBadRequest("missing LEMON_SQUEEZY_STORE_ID")

    try:
        payload_in = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        payload_in = {}

    plan = str(payload_in.get("plan", "pro") or "pro").strip().lower()

    if plan == "pro_plus":
        variant_id = getattr(settings, "LEMON_SQUEEZY_PRO_PLUS_VARIANT_ID", "")
    else:
        plan = "pro"
        variant_id = getattr(settings, "LEMON_SQUEEZY_PRO_VARIANT_ID", "")

    if not variant_id:
        return HttpResponseBadRequest(f"missing variant id for plan={plan}")

    attributes = {
        "checkout_data": {
            "email": request.user.email or "",
            "name": request.user.get_username() or "",
            "custom": {
                "user_id": request.user.id,
                "plan": plan,
            },
        },
        "product_options": {
            "receipt_button_text": "Back to CoinFlip",
        },
    }

    if site_url:
        attributes["product_options"]["redirect_url"] = f"{site_url}/main/coinflip/?paid=1&plan={plan}"

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": attributes,
            "relationships": {
                "store": {
                    "data": {
                        "type": "stores",
                        "id": str(store_id),
                    }
                },
                "variant": {
                    "data": {
                        "type": "variants",
                        "id": str(variant_id),
                    }
                },
            },
        }
    }

    try:
        res = _lemon_api_request("/checkouts", method="POST", payload=payload)
        checkout_url = (((res.get("data") or {}).get("attributes") or {}).get("url") or "").strip()

        if not checkout_url:
            return JsonResponse({"ok": False, "reason": "checkout_url_missing"}, status=500)

        return JsonResponse({"ok": True, "url": checkout_url, "plan": plan})
    except Exception as e:
        return JsonResponse(
            {"ok": False, "reason": "lemon_checkout_failed", "detail": str(e)},
            status=500,
        )


# ========= admin =========
@login_required
def api_adjust_capital(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    if not request.user.is_superuser:
        return JsonResponse({"ok": False, "reason": "forbidden"}, status=403)

    user_id = request.POST.get("user_id")
    try:
        capital = float(request.POST.get("capital", 0) or 0)
    except Exception:
        return JsonResponse({"ok": False, "reason": "invalid_capital"}, status=400)

    if not user_id:
        return JsonResponse({"ok": False, "reason": "missing_user_id"}, status=400)

    today = timezone.localdate()
    ws, we = _week_range(today)

    row = (
        LeaderboardEntry.objects
        .filter(user_id=user_id, created_at__date__gte=ws, created_at__date__lt=we)
        .order_by("-created_at", "-id")
        .first()
    )

    if not row:
        return JsonResponse({"ok": False, "reason": "no_current_week_row"}, status=404)

    row.final_capital = capital
    row.score_asset = 0
    row.score_risk = 0
    row.score_total = 0
    row.save(update_fields=["final_capital", "score_asset", "score_risk", "score_total"])

    return JsonResponse({
        "ok": True,
        "user_id": row.user_id,
        "final_capital": float(row.final_capital),
        "tier": get_tier_by_capital(row.final_capital),
    })


# ========= Lemon Squeezy webhook =========
@csrf_exempt
def lemon_webhook(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    secret = getattr(settings, "LEMON_SQUEEZY_WEBHOOK_SECRET", "")
    signature = request.META.get("HTTP_X_SIGNATURE", "")
    raw_body = request.body

    if not _verify_lemon_signature(raw_body, signature, secret):
        return HttpResponse(status=400)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return HttpResponse(status=400)

    event_name = (
        request.META.get("HTTP_X_EVENT_NAME")
        or (payload.get("meta") or {}).get("event_name")
        or ""
    ).strip()

    user = _resolve_user_for_webhook(payload)

    if event_name in {
        "subscription_created",
        "subscription_updated",
        "subscription_resumed",
        "subscription_unpaused",
        "subscription_payment_success",
        "subscription_payment_recovered",
        "subscription_paused",
        "subscription_payment_failed",
        "subscription_cancelled",
        "subscription_expired",
    }:
        _save_subscription_from_webhook(user=user, payload=payload)

    return HttpResponse(status=200)