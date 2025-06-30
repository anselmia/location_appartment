import logging

from django.db import models
from accounts.models import CustomUser
from datetime import timedelta
from django.utils import timezone

from decimal import Decimal, ROUND_HALF_UP

from logement.models import Logement
from activity.models import Activity
from common.services.helper_fct import generate_unique_code


logger = logging.getLogger(__name__)


class Reservation(models.Model):
    code = models.CharField(max_length=20, unique=True)
    logement = models.ForeignKey(Logement, null=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,  # Make it required
        blank=False,
    )
    start = models.DateField()
    end = models.DateField()
    statut = models.CharField(
        max_length=20,
        choices=[
            ("en_attente", "En attente"),
            ("confirmee", "Confirmée"),
            ("annulee", "Annulée"),
            ("terminee", "Terminée"),
            ("echec_paiement", "Echec du paiement"),
        ],
        default="en_attente",
    )
    guest_adult = models.IntegerField()
    guest_minor = models.IntegerField(default=0)
    date_reservation = models.DateTimeField(default=timezone.now)
    price = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    payment_fee = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    platform_fee = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    admin_fee_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    paid = models.BooleanField(default=False)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_saved_payment_method_id = models.CharField(max_length=255, null=True, blank=True)
    checkout_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    refunded = models.BooleanField(default=False)
    refund_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    stripe_refund_id = models.CharField(max_length=100, blank=True, null=True)
    caution_charged = models.BooleanField(default=False)
    amount_charged = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    stripe_deposit_payment_intent_id = models.CharField(max_length=100, blank=True, null=True)

    stripe_transfer_id = models.CharField(max_length=100, blank=True, null=True)
    transferred = models.BooleanField(default=False)
    transferred_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)

    admin_stripe_transfer_id = models.CharField(max_length=100, blank=True, null=True)
    admin_transferred = models.BooleanField(default=False)
    admin_transferred_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    pre_checkin_email_sent = models.BooleanField(default=False)

    # Ajout pour l'acceptation des CGU
    accepted_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    cgu_version = models.CharField(max_length=20, null=True, blank=True)
    cgv_version = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"{self.code}"

    def save(self, *args, **kwargs):
        from payment.services.payment_service import get_payment_fee, get_platform_fee, get_fee_waiver
        if not self.code:
            # Ensure uniqueness
            for _ in range(10):  # up to 10 retries
                code = generate_unique_code()
                if not Reservation.objects.filter(code=code).exists():
                    self.code = code
                    break
            else:
                raise ValueError("Could not generate a unique reservation code.")

        if not self.payment_fee:
            self.payment_fee = get_payment_fee(self.price)

        if self.platform_fee is None:
            platform_fee = get_platform_fee(self.price)
            self.platform_fee = get_fee_waiver(platform_fee, self.logement.owner)

        if not self.admin_fee_rate:
            self.admin_fee_rate = self.logement.admin_fee
        super().save(*args, **kwargs)

    @property
    def can_cancel(self):
        if self.statut != "confirmee":
            return False
        return True

    @property
    def refundable_period_passed(self):
        cancel_limit = self.start - timedelta(days=self.logement.cancelation_period)
        return timezone.now().date() > cancel_limit

    @property
    def refundable(self):
        if self.refundable_amount == 0:
            return False
        if self.refunded:
            return False
        if self.refundable_period_passed:
            return False
        if self.transferred or self.admin_transferred:
            return False
        return True

    @property
    def refundable_amount(self):
        """
        Calculates the refundable amount to the guest.

        Formula:
        refundable = price - payment_fee - already_refunded
        """
        try:
            price = Decimal(self.price or "0.00")
            payment_fee = Decimal(self.payment_fee or "0.00")
            refund_amount = Decimal(self.refund_amount or "0.00")

            refundable = price - payment_fee - refund_amount
            refundable = max(Decimal("0.00"), refundable)

            return refundable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"❌ Error calculating refundable_amount for reservation {self.id}: {e}")
            return Decimal("0.00")

    @property
    def partial_refundable_amount(self):
        """
        Calculates the partial refundable amount to the guest.

        Formula:
        refundable = price - payment_fee - already_refunded - platform_fee
        """
        try:
            price = Decimal(self.price or "0.00")
            payment_fee = Decimal(self.payment_fee or "0.00")
            refund_amount = Decimal(self.refund_amount or "0.00")
            platform_fee = Decimal(self.platform_fee or "0.00")

            refundable = price - payment_fee - refund_amount - platform_fee
            refundable = max(Decimal("0.00"), refundable)

            return refundable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"❌ Error calculating refundable_amount for reservation {self.id}: {e}")
            return Decimal("0.00")

    @property
    def ended(self):
        return self.statut == "terminee" or (self.statut == "confirmee" and timezone.now().date() > self.end)

    @property
    def ongoing(self):
        today = timezone.now().date()
        return self.statut == "confirmee" and (self.start <= today <= self.end)

    @property
    def coming(self):
        return self.statut == "confirmee" and (timezone.now().date() < self.start)

    @property
    def chargeable_deposit(self):
        caution = Decimal(self.logement.caution or 0)  # Ensure it is treated as a Decimal
        charged = Decimal(self.amount_charged or 0)  # Ensure it is treated as a Decimal
        result = max(Decimal("0"), caution - charged)

        # Round the result to 2 decimal places
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def transferable_amount(self):
        """
        Calculates the amount that can be transferred to the owner.

        Formula:
        transferable = price - platform_fee - refund_amount
        """
        try:

            platform_fee = Decimal(self.platform_fee or 0)
            payment_fee = Decimal(self.payment_fee or 0)
            refund = Decimal(self.refund_amount or 0)
            price = Decimal(self.price or 0)

            # Check if logement or owner has offered fees
            amount = price - platform_fee - refund - payment_fee
            amount = max(Decimal("0"), amount)

            if self.logement.admin:
                admin_rate = Decimal(self.admin_fee_rate or 0)
                admin_fee = admin_rate * amount
                amount -= admin_fee

            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"Error calculating transferable_amount for owner for reservation {self.id}: {e}")
            return Decimal("0.00")

    @property
    def admin_transferable_amount(self):
        """
        Calculates the amount that can be transferred to the admin.
        """
        try:
            if self.logement.admin and self.paid:
                platform_fee = Decimal(self.platform_fee or 0)
                payment_fee = Decimal(self.payment_fee or 0)
                refund = Decimal(self.refund_amount or 0)
                price = Decimal(self.price or 0)

                amount = price - platform_fee - refund - payment_fee
                amount = max(Decimal("0"), amount)

                admin_rate = Decimal(self.admin_fee_rate or 0)
                admin_fee = admin_rate * amount

                return admin_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                return Decimal(0)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"Error calculating transferable_amount for admin for reservation {self.id}: {e}")
            return Decimal("0.00")

    @property
    def total_guest(self) -> int:
        return int(self.guest_adult or 0) + int(self.guest_minor or 0)


class airbnb_booking(models.Model):
    logement = models.ForeignKey(Logement, on_delete=models.CASCADE)
    start = models.DateField()
    end = models.DateField()

    def __str__(self):
        return f"Réservation à {self.logement.name} du {self.start} au {self.end}"


class booking_booking(models.Model):
    logement = models.ForeignKey(Logement, on_delete=models.CASCADE)
    start = models.DateField()
    end = models.DateField()

    def __str__(self):
        return f"Réservation à {self.logement.name} du {self.start} au {self.end}"


class ActivityReservation(models.Model):
    activity = models.ForeignKey(Activity, related_name="reservations", on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="activity_reservations")
    participants = models.PositiveIntegerField(default=1)
    date_reservation = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(
        max_length=20,
        choices=[
            ("en_attente", "En attente"),
            ("confirmee", "Confirmée"),
            ("annulee", "Annulée"),
            ("terminee", "Terminée"),
            ("echec_paiement", "Échec du paiement"),
        ],
        default="pending",
    )
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    price = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    payment_fee = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    platform_fee = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    paid = models.BooleanField(default=False)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_saved_payment_method_id = models.CharField(max_length=255, blank=True, null=True)
    checkout_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    refunded = models.BooleanField(default=False)
    refund_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    stripe_refund_id = models.CharField(max_length=100, blank=True, null=True)
    transferred = models.BooleanField(default=False)
    transferred_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    stripe_transfer_id = models.CharField(max_length=100, blank=True, null=True)
    pre_checkin_email_sent = models.BooleanField(default=False)
    comment = models.TextField(blank=True)

    # Ajout pour l'acceptation des CGU
    accepted_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    cgu_version = models.CharField(max_length=20, null=True, blank=True)
    cgv_version = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.activity} ({self.statut})"

    def save(self, *args, **kwargs):
        from payment.services.payment_service import get_payment_fee, get_platform_fee, get_fee_waiver
        if not self.code:
            # Ensure uniqueness
            for _ in range(10):  # up to 10 retries
                code = generate_unique_code()
                if not ActivityReservation.objects.filter(code=code).exists():
                    self.code = code
                    break
            else:
                raise ValueError("Could not generate a unique reservation code.")

        if not self.payment_fee:
            self.payment_fee = get_payment_fee(self.price)

        if self.platform_fee is None:
            platform_fee = get_platform_fee(self.price)
            self.platform_fee = get_fee_waiver(platform_fee, self.activity.owner)

        super().save(*args, **kwargs)

    @property
    def can_cancel(self):
        if self.statut != "confirmee":
            return False
        return True

    @property
    def refundable_period_passed(self):
        cancel_limit = self.start - timedelta(days=self.activity.cancelation_period)
        return timezone.now() > cancel_limit

    @property
    def refundable(self):
        if self.refundable_amount == 0:
            return False
        if self.refunded:
            return False
        if self.refundable_period_passed:
            return False
        if self.transferred:
            return False
        return True

    @property
    def refundable_amount(self):
        """
        Calculates the refundable amount to the guest.

        Formula:
        refundable = price - payment_fee - already_refunded
        """
        try:
            price = Decimal(self.price or "0.00")
            payment_fee = Decimal(self.payment_fee or "0.00")
            refund_amount = Decimal(self.refund_amount or "0.00")

            refundable = price - payment_fee - refund_amount
            refundable = max(Decimal("0.00"), refundable)

            return refundable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            logger.exception(f"❌ Error calculating refundable_amount for reservation {self.id}: {e}")
            return Decimal("0.00")

    @property
    def partial_refundable_amount(self):
        """
        Calculates the partial refundable amount to the guest.

        Formula:
        refundable = price - payment_fee - already_refunded - platform_fee
        """
        try:
            price = Decimal(self.price or "0.00")
            payment_fee = Decimal(self.payment_fee or "0.00")
            refund_amount = Decimal(self.refund_amount or "0.00")
            platform_fee = Decimal(self.platform_fee or "0.00")

            refundable = price - payment_fee - refund_amount - platform_fee
            refundable = max(Decimal("0.00"), refundable)

            return refundable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"❌ Error calculating refundable_amount for reservation {self.id}: {e}")
            return Decimal("0.00")

    @property
    def ended(self):
        return self.statut == "terminee" or (self.statut == "confirmee" and timezone.now() > self.end)

    @property
    def pending(self):
        return self.statut == "en_attente"

    @property
    def ongoing(self):
        today = timezone.now()
        return self.statut == "confirmee" and (self.start <= today <= self.end)

    @property
    def coming(self):
        return self.statut == "confirmee" and (timezone.now() < self.start)

    @property
    def transferable_amount(self):
        """
        Calculates the amount that can be transferred to the owner.

        Formula:
        transferable = price - platform_fee - refund_amount
        """
        try:

            platform_fee = Decimal(self.platform_fee or 0)
            payment_fee = Decimal(self.payment_fee or 0)
            refund = Decimal(self.refund_amount or 0)
            price = Decimal(self.price or 0)

            # Check if logement or owner has offered fees
            amount = price - platform_fee - refund - payment_fee
            amount = max(Decimal("0"), amount)

            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"Error calculating transferable_amount for owner for reservation {self.id}: {e}")
            return Decimal("0.00")


class ReservationHistory(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="histories")
    details = models.TextField(blank=True)
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action"]

    def __str__(self):
        return f"{self.reservation} - ({self.date_action:%d/%m/%Y %H:%M})"


class ActivityReservationHistory(models.Model):
    reservation = models.ForeignKey(ActivityReservation, on_delete=models.CASCADE, related_name="histories")
    details = models.TextField(blank=True)
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action"]

    def __str__(self):
        return f"{self.reservation} - ({self.date_action:%d/%m/%Y %H:%M})"
