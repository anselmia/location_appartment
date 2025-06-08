# signals.py
import logging

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from reservation.models import Reservation, airbnb_booking, booking_booking

from logement.models import CloseDate, Logement

from administration.models import SiteConfig

from common.services.sms import send_sms, is_valid_number

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Reservation)
def send_sms_on_reservation(sender, instance, **kwargs):
    if not instance.pk:
        return  # Ignorer les nouvelles réservations

    try:
        site_config = SiteConfig.objects.first()
        if not site_config or not site_config.sms:
            logger.debug("SMS désactivé dans la configuration du site.")
            return
    except Exception as e:
        logger.warning(f"[SMS] Erreur de chargement de SiteConfig : {e}")
        return

    try:
        previous = Reservation.objects.get(pk=instance.pk)
    except Reservation.DoesNotExist:
        return

    if previous.statut != "confirmee" and instance.statut == "confirmee":
        logger.info(f"Reservation {instance.pk} : passage en statut 'confirmee', envoi des SMS...")

        msg = (
            f"Nouvelle réservation {instance.code} confirmée du {instance.start} au {instance.end} "
            f"pour le logement {instance.logement}."
        )

        # 🔹 Propriétaire du logement
        owner = getattr(instance.logement, "owner", None)
        if owner:
            phone = getattr(owner, "phone", None)
            if phone and is_valid_number(phone):
                send_sms(phone, msg)
                logger.info(f"SMS envoyé au propriétaire {owner} : {phone}")
            else:
                logger.warning(f"Aucun téléphone valide pour le propriétaire du logement {instance.logement}")

        # 🔹 Admin du logement (optionnel)
        admin = getattr(instance.logement, "admin", None)
        if admin:
            phone = getattr(admin, "phone", None)
            if phone and is_valid_number(phone):
                send_sms(phone, msg)
                logger.info(f"SMS envoyé à l'administrateur {admin} : {phone}")
            else:
                logger.warning(f"Aucun téléphone valide pour l'admin du logement {instance.logement}")


@receiver(pre_save, sender=Reservation)
def send_sms_on_cancel_booking(sender, instance, **kwargs):
    if not instance.pk:
        return  # Ignorer les nouvelles réservations

    try:
        site_config = SiteConfig.objects.first()
        if not site_config or not site_config.sms:
            logger.debug("SMS désactivé dans la configuration du site.")
            return
    except Exception as e:
        logger.warning(f"[SMS] Erreur de chargement de SiteConfig : {e}")
        return

    try:
        previous = Reservation.objects.get(pk=instance.pk)
    except Reservation.DoesNotExist:
        return

    if previous.statut != "annulee" and instance.statut == "annulee":
        logger.info(f"Reservation {instance.pk} : passage en statut 'annulee', envoi des SMS...")
        msg = (
            f"Réservation {instance.code} du {instance.start} au {instance.end} annulée "
            f"pour le logement {instance.logement}."
        )

        # 🔹 Propriétaire du logement
        owner = getattr(instance.logement, "owner", None)
        if owner:
            phone = getattr(owner, "phone", None)
            if phone and is_valid_number(phone):
                send_sms(phone, msg)
                logger.info(f"SMS envoyé au propriétaire {owner} : {phone}")
            else:
                logger.warning(f"Aucun téléphone valide pour le propriétaire du logement {instance.logement}")

        # 🔹 Admin du logement (optionnel)
        admin = getattr(instance.logement, "admin", None)
        if admin:
            phone = getattr(admin, "phone", None)
            if phone and is_valid_number(phone):
                send_sms(phone, msg)
                logger.info(f"SMS envoyé à l'administrateur {admin} : {phone}")
            else:
                logger.warning(f"Aucun téléphone valide pour l'admin du logement {instance.logement}")


@receiver([post_save, post_delete], sender=Reservation)
@receiver([post_save, post_delete], sender=CloseDate)
@receiver([post_save, post_delete], sender=airbnb_booking)
@receiver([post_save, post_delete], sender=booking_booking)
@receiver([post_save, post_delete], sender=Logement)
def clear_reservation_related_cache(sender, instance, **kwargs):
    logement_id = getattr(instance, "logement_id", None)
    if not logement_id and hasattr(instance, "logement"):
        logement_id = instance.logement.id
    elif isinstance(instance, Logement):
        logement_id = instance.id

    user_id = getattr(instance, "user_id", None)
    if not user_id and hasattr(instance, "user"):
        user_id = instance.user.id

    if logement_id:
        keys = [
            f"reservations_{user_id}_{logement_id}",
            f"valid_resa_admin_{user_id}_{logement_id}_*",
            f"nights_booked_{logement_id}_*",
            f"booked_dates_{logement_id}_*",
        ]
    else:
        keys = []

    # Invalider cache ciblé
    for pattern in keys + ["reservation_years_months"]:
        try:
            for key in cache.keys(pattern):
                cache.delete(key)
                logger.debug(f"[CACHE] Cleared key: {key}")
        except Exception as e:
            logger.warning(f"[CACHE] Failed to clear pattern {pattern}: {e}")

    # Invalider les logements disponibles
    try:
        for key in cache.keys("available_logement_*"):
            cache.delete(key)
            logger.debug(f"[CACHE] Cleared availability key: {key}")
    except Exception as e:
        logger.warning(f"[CACHE] Failed to clear available_logement_* keys: {e}")
