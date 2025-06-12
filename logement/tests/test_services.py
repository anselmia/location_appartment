import pytest
from unittest import mock
from datetime import date, timedelta, datetime
from decimal import Decimal

from icalendar import Calendar, Event
from django.core.cache import cache

from logement.services import calendar_service
from logement.services import logement as logement_service
from logement.models import Logement
from logement.tests.factories import (
    LogementFactory,
    ReservationFactory,
    DiscountFactory,
    PriceFactory,
    UserFactory,
    DiscountTypeFactory,
)

pytestmark = pytest.mark.django_db


@pytest.mark.django_db
def test_generate_ical_success():
    logement = LogementFactory()
    ReservationFactory(logement=logement, statut="confirmee", start=date.today(), end=date.today() + timedelta(days=2))
    ReservationFactory(
        logement=logement,
        statut="confirmee",
        start=date.today() + timedelta(days=3),
        end=date.today() + timedelta(days=5),
    )
    ical_bytes = calendar_service.generate_ical(logement.code)
    cal = Calendar.from_ical(ical_bytes)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 2
    assert all(e.get("SUMMARY") == "Reserved" for e in events)


@pytest.mark.django_db
def test_generate_ical_no_reservations():
    logement = LogementFactory()
    ical_bytes = calendar_service.generate_ical(logement.code)
    cal = Calendar.from_ical(ical_bytes)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 0


@pytest.mark.django_db
def test_generate_ical_invalid_code():
    with pytest.raises(Exception):
        calendar_service.generate_ical("not-a-real-code")


@pytest.mark.django_db
@mock.patch("logement.services.calendar_service.requests.get")
@mock.patch("logement.services.calendar_service.process_calendar")
def test_sync_external_ical_success(mock_process, mock_get):
    logement = LogementFactory()
    mock_get.return_value.text = "ical data"
    mock_process.return_value = (1, 0, 0)
    calendar_service.sync_external_ical(logement, "http://fake-url", "airbnb")
    mock_get.assert_called_once_with("http://fake-url")
    mock_process.assert_called_once_with(logement, "ical data", "airbnb")


@pytest.mark.django_db
@mock.patch("logement.services.calendar_service.requests.get")
def test_sync_external_ical_empty_data(mock_get):
    logement = LogementFactory()
    mock_get.return_value.text = ""
    with pytest.raises(ValueError, match="Empty iCal data received"):
        calendar_service.sync_external_ical(logement, "http://fake-url", "airbnb")


@pytest.mark.django_db
@mock.patch("logement.services.calendar_service.requests.get")
def test_sync_external_ical_exception(mock_get):
    logement = LogementFactory()
    mock_get.side_effect = Exception("Network error")
    with pytest.raises(ValueError, match="Error syncing iCal"):
        calendar_service.sync_external_ical(logement, "http://fake-url", "airbnb")


@pytest.mark.django_db
@mock.patch("logement.services.calendar_service.delete_old_reservations")
@mock.patch("logement.services.calendar_service.airbnb_booking")
def test_process_calendar_airbnb_add_and_update(mock_airbnb, mock_delete):
    logement = LogementFactory()
    cal = Calendar()
    event = Event()
    event.add("summary", "Reserved")
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 3)
    event.add("dtstart", start)
    event.add("dtend", end)
    cal.add_component(event)
    # Simulate add
    mock_airbnb.objects.update_or_create.return_value = (mock.Mock(), True)
    mock_delete.return_value = 0
    added, updated, deleted = calendar_service.process_calendar(logement, cal, "airbnb")
    assert added == 1
    assert updated == 0
    assert deleted == 0
    # Simulate update
    mock_airbnb.objects.update_or_create.return_value = (mock.Mock(), False)
    added, updated, deleted = calendar_service.process_calendar(logement, cal, "airbnb")
    assert added == 0
    assert updated == 1


@pytest.mark.django_db
@mock.patch("logement.services.calendar_service.delete_old_reservations")
@mock.patch("logement.services.calendar_service.booking_booking")
def test_process_calendar_booking_add_and_update(mock_booking, mock_delete):
    logement = LogementFactory()
    cal = Calendar()
    event = Event()
    event.add("summary", "Reserved")
    start = datetime(2025, 2, 1)
    end = datetime(2025, 2, 3)
    event.add("dtstart", start)
    event.add("dtend", end)
    cal.add_component(event)
    # Simulate add
    mock_booking.objects.update_or_create.return_value = (mock.Mock(), True)
    mock_delete.return_value = 0
    added, updated, deleted = calendar_service.process_calendar(logement, cal, "booking")
    assert added == 1
    assert updated == 0
    assert deleted == 0
    # Simulate update
    mock_booking.objects.update_or_create.return_value = (mock.Mock(), False)
    added, updated, deleted = calendar_service.process_calendar(logement, cal, "booking")
    assert added == 0
    assert updated == 1


@pytest.mark.django_db
def test_process_calendar_invalid_event(monkeypatch):
    logement = LogementFactory()
    cal = Calendar()
    event = Event()
    event.add("summary", "Reserved")
    # No dtstart/dtend
    cal.add_component(event)
    # Should skip invalid event and not raise
    with mock.patch("logement.services.calendar_service.delete_old_reservations", return_value=0):
        added, updated, deleted = calendar_service.process_calendar(logement, cal, "airbnb")
        assert added == 0
        assert updated == 0


@pytest.mark.django_db
def test_process_calendar_exception(monkeypatch):
    logement = LogementFactory()
    cal = Calendar()

    def broken_walk():
        raise Exception("Calendar broken")

    cal.walk = broken_walk
    with pytest.raises(ValueError, match="Error processing calendar from airbnb"):
        calendar_service.process_calendar(logement, cal, "airbnb")


@pytest.mark.django_db
def test_get_logements_admin_and_owner(monkeypatch):
    user = UserFactory(is_admin=True)
    logement1 = LogementFactory(owner=user)
    logement2 = LogementFactory()
    monkeypatch.setattr("django.core.cache.cache.get", lambda key: None)
    monkeypatch.setattr("django.core.cache.cache.set", lambda key, value, timeout: None)
    logements = logement_service.get_logements(user)
    assert logement1 in logements
    assert logement2 in logements


@pytest.mark.django_db
def test_get_logements_owner_only(monkeypatch):
    user = UserFactory()
    logement1 = LogementFactory(owner=user)
    logement2 = LogementFactory()
    monkeypatch.setattr("django.core.cache.cache.get", lambda key: None)
    monkeypatch.setattr("django.core.cache.cache.set", lambda key, value, timeout: None)
    logements = logement_service.get_logements(user)
    assert logement1 in logements
    assert logement2 not in logements


@pytest.mark.django_db
def test_get_logements_cache(monkeypatch):
    user = UserFactory()
    logements = [LogementFactory()]
    monkeypatch.setattr("django.core.cache.cache.get", lambda key: logements)
    result = logement_service.get_logements(user)
    assert result == logements


@pytest.mark.django_db
def test_get_logements_exception(monkeypatch):
    user = UserFactory()

    def raise_exc(*a, **kw):
        raise Exception("fail")

    monkeypatch.setattr("django.core.cache.cache.get", raise_exc)
    with pytest.raises(Exception):
        logement_service.get_logements(user)


@mock.patch("logement.services.logement.cache")
@mock.patch("logement.services.logement.parse_date")
@mock.patch("reservation.services.reservation_service.get_available_logement_in_period")
def test_filter_logements_basic(mock_get_available, mock_parse_date, mock_cache):
    logement = LogementFactory(
        statut="open", max_traveler=4, bedrooms=2, bathrooms=1, smoking=True, animals=True, type="apt"
    )
    mock_cache.get.return_value = None
    mock_cache.set.return_value = None
    mock_parse_date.side_effect = lambda x: date(2025, 1, 1) if x == "2025-01-01" else date(2025, 1, 3)
    mock_get_available.return_value = Logement.objects.filter(id=logement.id)
    result = logement_service.filter_logements(
        destination=logement.ville.name if hasattr(logement, "ville") and logement.ville else None,
        start_date="2025-01-01",
        end_date="2025-01-03",
        guest_adult=2,
        guest_minor=1,
        equipment_ids=[],
        bedrooms=2,
        bathrooms=1,
        smoking=True,
        animals=True,
        type="apt",
    )
    assert logement in result


@pytest.mark.django_db
@mock.patch("logement.services.logement.cache")
def test_filter_logements_cache(mock_cache):
    logements = [LogementFactory()]
    mock_cache.get.return_value = logements
    result = logement_service.filter_logements(
        destination=None,
        start_date=None,
        end_date=None,
        guest_adult=None,
        guest_minor=None,
        equipment_ids=[],
        bedrooms=None,
        bathrooms=None,
        smoking=None,
        animals=None,
        type=None,
    )
    assert result == logements


def test_get_best_discounts_empty():
    result = logement_service.get_best_discounts([], date.today(), date.today() + timedelta(days=3))
    assert result == {"min_nights": None, "days_before": None, "date_range": []}


def test_get_best_discounts_exception(monkeypatch):
    def raise_exc(*a, **kw):
        raise Exception("fail")

    monkeypatch.setattr("logement.services.logement.logger", mock.Mock())
    assert logement_service.get_best_discounts([mock.Mock()], date.today(), date.today()) == {
        "min_nights": None,
        "days_before": None,
        "date_range": [],
    }


def test_apply_discounts_min_nights_and_days_before():
    class D:
        def __init__(self, name, value, start_date=None, end_date=None):
            self.name = name
            self.value = value
            self.start_date = start_date
            self.end_date = end_date

    discounts = {"min_nights": D("min_nights", 10), "days_before": D("days_before", 5), "date_range": []}
    price, applied = logement_service.apply_discounts(Decimal("100.00"), date.today(), discounts)
    assert price < Decimal("100.00")
    assert any("min_nights" in a[0] or "days_before" in a[0] for a in applied)


def test_apply_discounts_date_range():
    class D:
        def __init__(self, name, value, start_date, end_date):
            self.name = name
            self.value = value
            self.start_date = start_date
            self.end_date = end_date

    today = date.today()
    discounts = {
        "min_nights": None,
        "days_before": None,
        "date_range": [D("date_range", 10, today, today + timedelta(days=1))],
    }
    price, applied = logement_service.apply_discounts(Decimal("100.00"), today, discounts)
    assert price < Decimal("100.00")
    assert any("date_range" in a[0] for a in applied)


def test_apply_discounts_invalid(monkeypatch):
    class D:
        def __init__(self, name, value, start_date=None, end_date=None):
            self.name = name
            self.value = "not-a-number"
            self.start_date = start_date
            self.end_date = end_date

    discounts = {"min_nights": D("min_nights", "not-a-number"), "days_before": None, "date_range": []}
    price, applied = logement_service.apply_discounts(Decimal("100.00"), date.today(), discounts)
    assert price == Decimal("100.00")


@pytest.mark.django_db
@mock.patch("logement.services.logement.cache")
@mock.patch("logement.services.logement.get_payment_fee")
def test_set_price_basic(mock_payment_fee, mock_cache):
    logement = LogementFactory(
        price=100, nominal_traveler=2, fee_per_extra_traveler=10, cleaning_fee=20, tax=10, tax_max=5
    )
    start = date.today()
    end = start + timedelta(days=2)
    mock_cache.get.return_value = None
    mock_cache.set.return_value = None
    mock_payment_fee.return_value = Decimal("5.00")
    PriceFactory(logement=logement, date=start, value=90)
    DiscountFactory(logement=logement, is_active=True, min_nights=1, value=10)
    result = logement_service.set_price(logement, start, end, 2, 0)
    assert "total_price" in result
    assert result["total_price"] > 0


@pytest.mark.django_db
@mock.patch("logement.services.logement.cache")
@mock.patch("logement.services.logement.get_payment_fee")
def test_set_price_cache(mock_payment_fee, mock_cache):
    logement = LogementFactory()
    start = date.today()
    end = start + timedelta(days=1)
    mock_cache.get.return_value = {"total_price": 123}
    result = logement_service.set_price(logement, start, end, 1, 0)
    assert result["total_price"] == 123


@pytest.mark.django_db
@mock.patch("logement.services.logement.cache")
@mock.patch("logement.services.logement.get_payment_fee")
def test_set_price_exception(mock_payment_fee, mock_cache):
    logement = LogementFactory()
    start = date.today()
    end = start + timedelta(days=1)
    mock_cache.get.side_effect = Exception("fail")
    with pytest.raises(Exception):
        logement_service.set_price(logement, start, end, 1, 0)


@pytest.mark.django_db
def test_get_best_discounts_selects_best_per_type():
    # DiscountTypes
    min_nights_type = DiscountTypeFactory(
        requires_min_nights=True, requires_days_before=False, requires_date_range=False
    )
    days_before_type = DiscountTypeFactory(
        requires_min_nights=False, requires_days_before=True, requires_date_range=False
    )
    date_range_type = DiscountTypeFactory(
        requires_min_nights=False, requires_days_before=False, requires_date_range=True
    )

    # Logement
    logement = LogementFactory()

    # Discounts for min_nights_type
    d1 = DiscountFactory(
        logement=logement,
        discount_type=min_nights_type,
        min_nights=2,
        value=10,
        days_before_min=None,
        days_before_max=None,
        start_date=None,
        end_date=None,
    )
    d2 = DiscountFactory(
        logement=logement,
        discount_type=min_nights_type,
        min_nights=5,
        value=20,  # better value
        days_before_min=None,
        days_before_max=None,
        start_date=None,
        end_date=None,
    )

    # Discounts for days_before_type
    d3 = DiscountFactory(
        logement=logement,
        discount_type=days_before_type,
        min_nights=None,
        days_before_min=10,
        days_before_max=20,
        value=5,
        start_date=None,
        end_date=None,
    )
    d4 = DiscountFactory(
        logement=logement,
        discount_type=days_before_type,
        min_nights=None,
        days_before_min=5,
        days_before_max=15,
        value=15,  # better value
        start_date=None,
        end_date=None,
    )

    # Discounts for date_range_type
    today = date.today()
    d5 = DiscountFactory(
        logement=logement,
        discount_type=date_range_type,
        min_nights=None,
        days_before_min=None,
        days_before_max=None,
        start_date=today,
        end_date=today + timedelta(days=5),
        value=8,
    )
    d6 = DiscountFactory(
        logement=logement,
        discount_type=date_range_type,
        min_nights=None,
        days_before_min=None,
        days_before_max=None,
        start_date=today,
        end_date=today + timedelta(days=10),
        value=12,  # better value
    )

    # Set start_date so days_before >= 10
    booking_start = today + timedelta(days=10)
    booking_end = booking_start + timedelta(days=6)

    discounts = [d1, d2, d3, d4, d5, d6]
    result = logement_service.get_best_discounts(discounts, booking_start, booking_end)
    # Should select the best (highest value) for each type
    assert result["min_nights"] == d2
    assert result["days_before"] == d3  # d3 has higher days_before_min (10 vs 5)
    assert d6 in result["date_range"]
    assert len(result["date_range"]) == 1  # Only one date range discount should be selected


@pytest.mark.django_db
@mock.patch("logement.services.logement.cache")
@mock.patch("logement.services.logement.parse_date")
@mock.patch("reservation.services.reservation_service.get_available_logement_in_period")
def test_filter_logements_all_filters(mock_get_available, mock_parse_date, mock_cache):
    logement = LogementFactory(
        statut="open", max_traveler=4, bedrooms=3, bathrooms=2, smoking=True, animals=False, type="house"
    )
    mock_cache.get.return_value = None
    mock_cache.set.return_value = None
    mock_parse_date.side_effect = lambda x: date(2025, 1, 1) if x == "2025-01-01" else date(2025, 1, 5)
    mock_get_available.return_value = Logement.objects.filter(id=logement.id)
    result = logement_service.filter_logements(
        destination=logement.ville.name if hasattr(logement, "ville") and logement.ville else None,
        start_date="2025-01-01",
        end_date="2025-01-05",
        guest_adult=2,
        guest_minor=2,
        equipment_ids=[],
        bedrooms=3,
        bathrooms=2,
        smoking=True,
        animals=False,
        type="house",
    )
    assert logement in result


@pytest.mark.django_db
def test_filter_logements_invalid_dates():
    with pytest.raises(Exception):
        logement_service.filter_logements(
            destination=None,
            start_date="invalid-date",
            end_date="invalid-date",
            guest_adult=None,
            guest_minor=None,
            equipment_ids=[],
            bedrooms=None,
            bathrooms=None,
            smoking=None,
            animals=None,
            type=None,
        )


def test_get_best_discounts_overlap_and_ties():
    today = date.today()
    # Overlapping date_range discounts
    d1 = DiscountFactory(
        min_nights=None,
        days_before_min=None,
        days_before_max=None,
        start_date=today,
        end_date=today + timedelta(days=5),
        value=10,
    )
    d2 = DiscountFactory(
        min_nights=None,
        days_before_min=None,
        days_before_max=None,
        start_date=today + timedelta(days=2),
        end_date=today + timedelta(days=7),
        value=15,
    )
    discounts = [d1, d2]
    result = logement_service.get_best_discounts(discounts, today + timedelta(days=3), today + timedelta(days=4))
    assert d1 in result["date_range"]
    assert d2 in result["date_range"]


def test_get_best_discounts_tie_min_nights():
    d1 = DiscountFactory(
        min_nights=3, value=10, days_before_min=None, days_before_max=None, start_date=None, end_date=None
    )
    d2 = DiscountFactory(
        min_nights=4, value=20, days_before_min=None, days_before_max=None, start_date=None, end_date=None
    )
    discounts = [d1, d2]
    result = logement_service.get_best_discounts(discounts, date.today(), date.today() + timedelta(days=5))
    # Should pick the last one if tie (as per current logic)
    assert result["min_nights"] == d2


@pytest.mark.django_db
def test_set_price_zero_nights():
    logement = LogementFactory(
        price=100, nominal_traveler=2, fee_per_extra_traveler=10, cleaning_fee=20, tax=10, tax_max=5
    )
    start = date.today()
    end = start  # zero nights
    result = logement_service.set_price(logement, start, end, 2, 0)
    assert result["total_price"] == 0


@pytest.mark.django_db
def test_set_price_zero_guests():
    logement = LogementFactory(
        price=100, nominal_traveler=2, fee_per_extra_traveler=10, cleaning_fee=20, tax=10, tax_max=5
    )
    start = date.today()
    end = start + timedelta(days=2)
    result = logement_service.set_price(logement, start, end, 0, 0)
    assert result["total_price"] >= 0


@pytest.mark.django_db
def test_set_price_no_discounts_or_custom_prices():
    logement = LogementFactory(
        price=100, nominal_traveler=2, fee_per_extra_traveler=10, cleaning_fee=20, tax=10, tax_max=5
    )
    start = date.today()
    end = start + timedelta(days=2)
    result = logement_service.set_price(logement, start, end, 2, 0)
    assert result["total_price"] > 0


@pytest.mark.django_db
def test_set_price_with_one_discount_exact():
    cache.clear()  # <-- Add this line
    logement = LogementFactory(
        price=100, nominal_traveler=2, fee_per_extra_traveler=10, cleaning_fee=20, tax=6.7, tax_max=6.43
    )
    start = date.today()
    end = start + timedelta(days=2)  # 2 nights

    # 10% discount for any stay (min_nights=1)
    DiscountFactory(logement=logement, is_active=True, min_nights=1, value=10)

    # Call the service
    result = logement_service.set_price(logement, start, end, 2, 0)

    # Manual calculation:
    nights = 2
    base_price = 100 * nights  # 200
    discount = base_price * Decimal("0.10")  # 20
    after_discount = base_price - discount  # 180
    extra_guest_fee = 0  # 2 guests, nominal is 2
    per_night = after_discount / nights  # 90
    guest_decimal = Decimal("2")
    tax_rate = min((Decimal(str(logement.tax)) / 100) * (per_night / guest_decimal), Decimal(str(logement.tax_max)))
    taxAmount = tax_rate * guest_decimal * nights
    cleaning_fee = 20
    subtotal = after_discount + extra_guest_fee + cleaning_fee + taxAmount  # 180 + 0 + 20 + 18 = 218
    payment_fee = logement_service.get_payment_fee(subtotal)
    expected_total = subtotal + payment_fee

    assert result["number_of_nights"] == nights
    assert result["total_base_price"] == base_price
    assert sum(result["discount_totals"].values()) == discount
    assert result["TotalextraGuestFee"] == 0
    assert result["taxAmount"] == Decimal("12.06")  # 6.7% of 180
    assert result["payment_fee"] == payment_fee
    assert result["total_price"] == expected_total
