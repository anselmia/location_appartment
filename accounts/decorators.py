import logging

from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.core.cache import cache
from functools import wraps

from accounts.models import Conversation

from common.services.network import get_client_ip

logger = logging.getLogger(__name__)


def user_in_conversation(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        conversation_id = kwargs.get("conversation_id")
        conversation = get_object_or_404(Conversation, id=conversation_id)

        user = request.user
        reservation = conversation.reservation

        is_participant = (
            reservation.user == user
            or reservation.logement.owner == user
            or (reservation.logement.admin and reservation.logement.admin == user)
            or user.is_admin
            or user.is_superuser
        )

        if is_participant:
            return view_func(request, *args, **kwargs)

        messages.error(request, "Accès refusé : vous ne participez pas à cette conversation.")
        return redirect("accounts:dashboard")

    return _wrapped_view


def stripe_attempt_limiter(key_template, limit=3, timeout=3600):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            ip = get_client_ip(request)
            key = key_template.format(user_id=user.id)
            attempts = cache.get(key, 0)
            if attempts >= limit:
                logger.warning(f"[Stripe] Limite atteinte | {key} | ip={ip}")
                messages.error(request, "Trop de tentatives. Réessayez plus tard.")
                return redirect("accounts:dashboard")
            cache.set(key, attempts + 1, timeout)
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
