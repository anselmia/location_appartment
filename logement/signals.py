# signals.py
import logging
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Reservation
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


@receiver(pre_save, sender=Reservation)
def send_sms_on_refund(sender, instance, **kwargs):
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

    if not previous.refunded and instance.refunded:
        logger.info(f"Reservation {instance.pk} remboursée, envoi des SMS...")
        msg = (
            f"Réservation {instance.code} du {instance.start} au {instance.end} remboursée (Montant: {instance.refund_amount} €)"
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
def send_sms_on_transfer(sender, instance, **kwargs):
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

    if not previous.transferred and instance.transferred:
        logger.info(f"Reservation {instance.pk} argent transferré, envoi des SMS...")
        msg = (
            f"Réservation {instance.code}, argent transferré au propriétaire (Montant: {instance.transferred_amount} €)"
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
        if not previous.admin_transferred and instance.admin_transferred:
            logger.info(f"Reservation {instance.pk} argent transferré à l'admin, envoi des SMS...")
            msg = (
                f"Réservation {instance.code}, argent transferré (Montant: {instance.admin_transferred_amount} €)"
                f"pour le logement {instance.logement}."
            )
            phone = getattr(admin, "phone", None)
            if phone and is_valid_number(phone):
                send_sms(phone, msg)
                logger.info(f"SMS envoyé à l'administrateur {admin} : {phone}")
            else:
                logger.warning(f"Aucun téléphone valide pour l'admin du logement {instance.logement}")
