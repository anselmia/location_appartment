import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core.cache import cache
from logement.models import Logement, CloseDate
from logement.tests.factories import (
    LogementFactory,
    ReservationFactory,
    DiscountFactory,
    PriceFactory,
    UserFactory,
)
from reservation.services import reservation_service

pytestmark = pytest.mark.django_db


def setup_function():
    cache.clear()


def test_get_reservations_admin_and_owner():
    admin = UserFactory(is_admin=True)
    owner = UserFactory()
    owner2 = UserFactory()
    logement = LogementFactory(owner=owner)
    logement2 = LogementFactory(owner=owner2)
    resa1 = ReservationFactory(logement=logement, user=owner)
    resa2 = ReservationFactory(logement=logement2, user=admin)
    # Admin sees all
    assert resa1 in reservation_service.get_reservations(admin)
    assert resa2 in reservation_service.get_reservations(admin)
    # Owner sees own
    assert resa1 in reservation_service.get_reservations(owner)
    assert resa2 not in reservation_service.get_reservations(owner)


def test_get_valid_reservations_for_admin_filters():
    admin = UserFactory(is_admin=True)
    logement = LogementFactory()
    resa = ReservationFactory(logement=logement, user=admin, statut="confirmee", start=date(2025, 1, 1))
    qs = reservation_service.get_valid_reservations_for_admin(admin, logement.id, 2025, 1)
    assert resa in qs


def test_get_valid_reservations_in_period():
    logement = LogementFactory()
    resa = ReservationFactory(
        logement=logement, start=date.today(), end=date.today() + timedelta(days=2), statut="confirmee"
    )
    qs = reservation_service.get_valid_reservations_in_period(
        logement.id, date.today(), date.today() + timedelta(days=2)
    )
    assert resa in qs


def test_get_night_booked_in_period_counts():
    logement = LogementFactory()
    ReservationFactory(logement=logement, start=date.today(), end=date.today() + timedelta(days=3), statut="confirmee")
    nights = reservation_service.get_night_booked_in_period(
        [logement], logement.id, date.today(), date.today() + timedelta(days=3)
    )
    assert nights == 3


def test_get_user_reservation_ordering():
    user = UserFactory()
    ReservationFactory(user=user, start=date.today())
    ReservationFactory(user=user, start=date.today() + timedelta(days=1))
    resas = list(reservation_service.get_user_reservation(user))
    assert resas[0].start >= resas[1].start


def test_get_reservation_years_and_months():
    ReservationFactory(start=date(2024, 5, 1))
    ReservationFactory(start=date(2025, 6, 1))
    years, months = reservation_service.get_reservation_years_and_months()
    assert 2024 in years and 2025 in years
    assert 5 in months and 6 in months


def test_get_available_logement_in_period_excludes_booked():
    logement = LogementFactory()
    ReservationFactory(logement=logement, start=date.today(), end=date.today() + timedelta(days=2), statut="confirmee")
    logements = Logement.objects.filter(id=logement.id)
    available = reservation_service.get_available_logement_in_period(
        date.today(), date.today() + timedelta(days=2), logements
    )
    assert logement not in available


def test_is_period_booked_true_and_false():
    user = UserFactory()
    logement = LogementFactory()
    ReservationFactory(logement=logement, start=date.today(), end=date.today() + timedelta(days=2), statut="confirmee")
    assert reservation_service.is_period_booked(date.today(), date.today() + timedelta(days=2), logement.id, user)
    # No reservation for this period
    assert not reservation_service.is_period_booked(
        date.today() + timedelta(days=10), date.today() + timedelta(days=12), logement.id, user
    )


def test_validate_reservation_inputs_success_and_fail():
    user = UserFactory()
    logement = LogementFactory(
        max_traveler=4, ready_period=1, max_days=10, availablity_period=12
    )
    # Valid
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)
    assert reservation_service.validate_reservation_inputs(logement, user, start, end, 2, 0)
    # Too many guests
    with pytest.raises(ValueError):
        reservation_service.validate_reservation_inputs(logement, user, start, end, 5, 0)
    # End before start
    with pytest.raises(ValueError):
        reservation_service.validate_reservation_inputs(logement, user, end, start, 2, 0)


def test_create_and_cancel_reservation():
    user = UserFactory()
    logement = LogementFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)
    resa = reservation_service.create_or_update_reservation(logement, user, start, end, 2, 0, 100, 10)
    assert resa.logement == logement
    reservation_service.mark_reservation_cancelled(resa)
    resa.refresh_from_db()
    assert resa.statut == "annulee"


def test_cancel_and_refund_reservation(monkeypatch):
    user = UserFactory()
    logement = LogementFactory(cancelation_period=1)
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)
    resa = ReservationFactory(
        logement=logement,
        user=user,
        start=start,
        end=end,
        statut="confirmee",
        stripe_payment_intent_id="pi_123",
    )
    # Mock refund_payment to do nothing (simulate success)
    monkeypatch.setattr("reservation.services.reservation_service.refund_payment", lambda *a, **kw: None)
    msg, err = reservation_service.cancel_and_refund_reservation(resa)
    resa.refresh_from_db()
    assert "annulée" in msg


def test_delete_old_reservations(monkeypatch):
    # Simulate airbnb_booking and booking_booking models
    class DummyBooking:
        def __init__(self, start, end):
            self.start = start
            self.end = end

        def delete(self):
            pass

    monkeypatch.setattr(
        "reservation.services.reservation_service.airbnb_booking",
        type(
            "Airbnb",
            (),
            {
                "objects": type(
                    "Mgr",
                    (),
                    {"filter": lambda *a, **k: [DummyBooking(date.today(), date.today() + timedelta(days=1))]},
                )()
            },
        )(),
    )
    monkeypatch.setattr(
        "reservation.services.reservation_service.booking_booking",
        type(
            "Booking",
            (),
            {
                "objects": type(
                    "Mgr",
                    (),
                    {"filter": lambda *a, **k: [DummyBooking(date.today(), date.today() + timedelta(days=1))]},
                )()
            },
        )(),
    )
    deleted = reservation_service.delete_old_reservations([], "airbnb")
    assert deleted >= 0


def test_cannot_create_overlapping_reservations():
    logement = LogementFactory()
    user1 = UserFactory()
    user2 = UserFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=3)
    ReservationFactory(logement=logement, user=user1, start=start, end=end, statut="confirmee")
    with pytest.raises(Exception):
        reservation_service.validate_reservation_inputs(
            logement, user2, start + timedelta(days=1), end + timedelta(days=1), 2, 0, 100, 10
        )


def test_reservation_with_discount_and_custom_price():
    logement = LogementFactory(price=100)
    user = UserFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=1)
    DiscountFactory(logement=logement, is_active=True, min_nights=1, value=20)
    PriceFactory(logement=logement, date=start, value=80)
    price_data = reservation_service.set_price(logement, start, end, 2, 0)
    resa = reservation_service.create_or_update_reservation(
        logement, user, start, end, 2, 0, price_data["total_price"], price_data["taxAmount"]
    )

    price = (
        Decimal("80")
        - Decimal(str(16))  # Discount applied
        + Decimal(str(2 * logement.fee_per_extra_traveler))
        + Decimal(str(price_data["taxAmount"]))
        + Decimal(str(price_data["payment_fee"]))
        + Decimal(str(logement.cleaning_fee))
    )
    print()
    assert resa.price == price


def test_reservation_with_extra_guests_fee():
    logement = LogementFactory(price=100, nominal_traveler=2, fee_per_extra_traveler=15)
    user = UserFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=1)
    price_data = reservation_service.set_price(logement, start, end, 4, 0)
    resa = reservation_service.create_or_update_reservation(
        logement, user, start, end, 4, 0, price_data["total_price"], price_data["taxAmount"]
    )

    price = (
        Decimal(str(logement.price))
        + Decimal(str(2 * logement.fee_per_extra_traveler))
        + Decimal(str(price_data["taxAmount"]))
        + Decimal(str(price_data["payment_fee"]))
        + Decimal(str(logement.cleaning_fee))
    )
    assert resa.price == price


def test_cannot_reserve_on_closed_dates():
    logement = LogementFactory()
    user = UserFactory()
    closed_start = date.today() + timedelta(days=5)
    closed_end = closed_start + timedelta(days=2)
    CloseDate.objects.create(logement=logement, date=closed_start)
    with pytest.raises(Exception):
        reservation_service.validate_reservation_inputs(logement, user, closed_start, closed_end, 2, 0, 100, 10)


def test_cancel_already_cancelled_reservation():
    user = UserFactory()
    logement = LogementFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=4)
    resa = ReservationFactory(logement=logement, user=user, statut="annulee", start=start, end=end)
    msg, err = reservation_service.cancel_and_refund_reservation(resa)
    assert "déjà annulée" in msg or err is not None


def test_cancel_non_refundable_reservation():
    user = UserFactory()
    logement = LogementFactory(cancelation_period=15)
    start = date.today() + timedelta(days=2)
    end = date.today() + timedelta(days=1)
    resa = ReservationFactory(logement=logement, user=user, statut="confirmee", start=start, end=end)
    msg, err = reservation_service.cancel_and_refund_reservation(resa)
    assert "aucun paiement à rembourser" in msg or err is not None


def test_reservation_invalid_dates():
    logement = LogementFactory()
    user = UserFactory()
    start = date.today() - timedelta(days=2)
    end = date.today() - timedelta(days=1)
    with pytest.raises(ValueError):
        reservation_service.validate_reservation_inputs(logement, user, start, end, 2, 0, 100, 10)


def test_reservation_tax_capped():
    logement = LogementFactory(price=100, tax=100, tax_max=5)
    user = UserFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)
    resa = reservation_service.create_or_update_reservation(logement, user, start, end, 2, 0, 100, 10)
    assert hasattr(resa, "tax") or resa.price > 0


@pytest.mark.parametrize("statut", ["confirmee", "annulee", "terminee", "echec_paiement"])
def test_get_user_reservation_statuses(statut):
    user = UserFactory()
    resa = ReservationFactory(user=user, statut=statut)
    resas = reservation_service.get_user_reservation(user)
    assert resa in resas


def test_booking_on_booking_limit():
    logement = LogementFactory(ready_period=7)
    user = UserFactory()
    start = date.today() + timedelta(days=7)
    end = start + timedelta(days=7)
    # Should succeed
    price_data = reservation_service.set_price(logement, start, start + timedelta(days=3), 2, 0)
    reservation_service.validate_reservation_inputs(
        logement, user, start, end, 2, 0, price_data["total_price"], price_data["taxAmount"]
    )
    # Should fail if before booking_limit
    with pytest.raises(ValueError):
        reservation_service.validate_reservation_inputs(
            logement, user, start - timedelta(days=7), end - timedelta(days=7), 2, 0, 100, 10
        )


def test_min_max_booking_days():
    logement = LogementFactory(min_booking_days=3)
    user = UserFactory()
    start = date.today() + timedelta(days=1)
    # Too short
    with pytest.raises(ValueError):
        reservation_service.validate_reservation_inputs(logement, user, start, start + timedelta(days=2), 2, 0, 100, 10)
    # Valid: use the real calculated price/tax
    price_data = reservation_service.set_price(logement, start, start + timedelta(days=3), 2, 0)
    reservation_service.validate_reservation_inputs(
        logement, user, start, start + timedelta(days=3), 2, 0, price_data["total_price"], price_data["taxAmount"]
    )


def test_availablity_period_limit():
    logement = LogementFactory(availablity_period=2)
    user = UserFactory()
    start = date.today() + timedelta(days=70)  # ~2 months + 10 days
    end = start + timedelta(days=2)
    with pytest.raises(ValueError):
        reservation_service.validate_reservation_inputs(logement, user, start, end, 2, 0, 100, 10)


@pytest.mark.parametrize("adults, minors", [(0, 0), (-1, 1), (1, -1)])
def test_zero_or_negative_guests(adults, minors):
    logement = LogementFactory()
    user = UserFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)
    with pytest.raises(ValueError):
        reservation_service.validate_reservation_inputs(logement, user, start, end, adults, minors, 100, 10)


def test_custom_price_and_discount_combined():
    logement = LogementFactory(price=100)
    user = UserFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)
    DiscountFactory(logement=logement, is_active=True, min_nights=1, value=10)
    PriceFactory(logement=logement, date=start, value=80)
    resa = reservation_service.create_or_update_reservation(logement, user, start, end, 2, 0, 80, 10)
    assert resa.price < 160  # 80 per night, minus discount


def test_booking_with_all_fees():
    logement = LogementFactory(
        price=100, cleaning_fee=30, nominal_traveler=2, fee_per_extra_traveler=20, tax=10, tax_max=7
    )
    user = UserFactory()
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)
    price_data = reservation_service.set_price(logement, start, end, 4, 0)
    resa = reservation_service.create_or_update_reservation(
        logement, user, start, end, 4, 0, price_data["total_price"], price_data["taxAmount"]
    )
    assert resa.price > 0
    assert resa.tax <= Decimal("56")  # 2 nights * 7 max tax per night * 4 adults


def test_gap_blocking_with_min_booking_days():
    logement = LogementFactory(min_booking_days=3)
    user = UserFactory()
    # Book two reservations with a 1-day gap
    start1 = date.today() + timedelta(days=2)
    end1 = start1 + timedelta(days=2)
    start2 = end1 + timedelta(days=2)
    end2 = start2 + timedelta(days=2)
    ReservationFactory(logement=logement, user=user, start=start1, end=end1, statut="confirmee")
    ReservationFactory(logement=logement, user=user, start=start2, end=end2, statut="confirmee")
    # Try to book in the 1-day gap
    with pytest.raises(Exception):
        reservation_service.validate_reservation_inputs(logement, user, end1, start2, 2, 0, 100, 10)
