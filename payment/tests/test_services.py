import pytest
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import payment.services.payment_service as payment_service

from payment.tests.factories import UserFactory
from logement.tests.factories import LogementFactory
from reservation.tests.factories import ReservationFactory

pytestmark = pytest.mark.django_db


class DummyRequest:
    def __init__(self):
        self.META = {"HTTP_X_FORWARDED_FOR": "127.0.0.1"}

    def build_absolute_uri(self, url):
        return f"http://testserver{url}"


@pytest.fixture
def user():
    return UserFactory(stripe_customer_id="cus_123")


@pytest.fixture
def logement(user):
    return LogementFactory(owner=user)


@pytest.fixture
def reservation(user, logement):
    return ReservationFactory(
        user=user,
        logement=logement,
        price=Decimal("100.00"),
        statut="en_attente",
        start=date.today() + timedelta(days=20),
        end=date.today() + timedelta(days=22),
        stripe_payment_intent_id="pi_123",
    )


def test_is_stripe_admin(user):
    user.is_admin = True
    assert payment_service.is_stripe_admin(user)
    user.is_admin = False
    user.is_superuser = True
    assert payment_service.is_stripe_admin(user)
    user.is_superuser = False
    user.is_owner = True
    assert payment_service.is_stripe_admin(user)
    user.is_owner = False
    user.is_owner_admin = True
    assert payment_service.is_stripe_admin(user)
    user.is_owner_admin = False
    assert not payment_service.is_stripe_admin(user)


def test_get_payment_fee_and_platform_fee():
    price = Decimal("100.00")
    fee = payment_service.get_payment_fee(price)
    platform_fee = payment_service.get_platform_fee(price)
    assert isinstance(fee, Decimal)
    assert isinstance(platform_fee, Decimal)
    assert fee > 0
    assert platform_fee > 0


def test_get_payment_fee_zero():
    assert payment_service.get_payment_fee(0) >= Decimal("0.00")


def test_get_platform_fee_zero():
    assert payment_service.get_platform_fee(0) == Decimal("0.00")


def test_get_payment_fee_rounding():
    price = Decimal("99.99")
    fee = payment_service.get_payment_fee(price)
    assert fee.quantize(Decimal("0.01")) == fee


def test_get_platform_fee_rounding():
    price = Decimal("99.99")
    fee = payment_service.get_platform_fee(price)
    assert fee.quantize(Decimal("0.01")) == fee


@patch("payment.services.payment_service.stripe.checkout.Session.create")
@patch("payment.services.payment_service.create_stripe_customer_if_not_exists", return_value="cus_123")
def test_create_stripe_checkout_session_with_deposit(mock_customer, mock_stripe, reservation):
    dummy_request = DummyRequest()
    mock_stripe.return_value = MagicMock(id="sess_123", url="http://checkout.url")
    result = payment_service.create_stripe_checkout_session_with_deposit(reservation, dummy_request)
    assert "checkout_session_url" in result
    assert "session_id" in result


@patch("payment.services.payment_service.create_stripe_customer_if_not_exists", return_value=None)
def test_create_stripe_checkout_session_with_deposit_no_customer(mock_customer, reservation):
    dummy_request = DummyRequest()
    with pytest.raises(Exception):
        payment_service.create_stripe_checkout_session_with_deposit(reservation, dummy_request)


def test_create_stripe_checkout_session_with_deposit_invalid_price(reservation):
    dummy_request = DummyRequest()
    reservation.price = Decimal("-10.00")
    with pytest.raises(Exception):
        payment_service.create_stripe_checkout_session_with_deposit(reservation, dummy_request)


@patch(
    "payment.services.payment_service.create_stripe_checkout_session_with_deposit",
    return_value=MagicMock(url="http://checkout.url"),
)
@patch("payment.services.payment_service.send_mail_payment_link")
def test_send_stripe_payment_link(mock_mail, mock_checkout, reservation):
    dummy_request = DummyRequest()
    url = payment_service.send_stripe_payment_link(reservation, dummy_request)
    assert url == "http://checkout.url"
    mock_mail.assert_called_once()


def test_send_stripe_payment_link_no_email(reservation):
    dummy_request = DummyRequest()
    reservation.user.email = None
    with pytest.raises(Exception):
        payment_service.send_stripe_payment_link(reservation, dummy_request)


def test_send_stripe_payment_link_invalid_price(reservation):
    dummy_request = DummyRequest()
    reservation.price = Decimal("0.00")
    with pytest.raises(Exception):
        payment_service.send_stripe_payment_link(reservation, dummy_request)


@patch("payment.services.payment_service.stripe.Customer.retrieve")
def test_is_valid_stripe_customer(mock_retrieve):
    mock_retrieve.return_value = MagicMock(deleted=False)
    assert payment_service.is_valid_stripe_customer("cus_123")
    mock_retrieve.return_value = MagicMock(deleted=True)
    assert not payment_service.is_valid_stripe_customer("cus_123")
    mock_retrieve.side_effect = payment_service.stripe.error.InvalidRequestError("err", "param")
    assert not payment_service.is_valid_stripe_customer("cus_123")


@patch("payment.services.payment_service.stripe.Customer.create")
@patch("payment.services.payment_service.is_valid_stripe_customer", return_value=False)
def test_create_stripe_customer_if_not_exists(mock_valid, mock_create, user):
    dummy_request = DummyRequest()
    mock_create.return_value = MagicMock(id="cus_123")
    customer_id = payment_service.create_stripe_customer_if_not_exists(user, dummy_request)
    assert customer_id == "cus_123"


@patch("payment.services.payment_service.stripe.Customer.create")
@patch("payment.services.payment_service.is_valid_stripe_customer", return_value=False)
def test_create_stripe_customer_no_email(mock_valid, mock_create, user):
    dummy_request = DummyRequest()
    user.email = None
    with pytest.raises(Exception):
        payment_service.create_stripe_customer_if_not_exists(user, dummy_request)


@patch("payment.services.payment_service.stripe.PaymentMethod.retrieve")
@patch("payment.services.payment_service.stripe.PaymentMethod.attach")
@patch("payment.services.payment_service.stripe.PaymentIntent.create")
@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_charge_payment(mock_task, mock_intent, mock_attach, mock_retrieve, reservation):
    mock_retrieve.return_value = MagicMock(customer="cus_123")
    mock_intent.return_value = MagicMock(id="pi_123")
    result = payment_service.charge_deposit("pm_123", 10000, "cus_123", reservation)
    assert result.id == "pi_123"


@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_charge_payment_missing_payment_method(mock_task, reservation):
    with pytest.raises(Exception):
        payment_service.charge_deposit(None, 10000, "cus_123", reservation)


@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_charge_payment_missing_customer(mock_task, reservation):
    with pytest.raises(Exception):
        payment_service.charge_deposit("pm_123", 10000, None, reservation)


@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_charge_payment_already_charged(mock_task, reservation):
    reservation.caution_charged = True
    with pytest.raises(Exception):
        payment_service.charge_deposit("pm_123", 10000, "cus_123", reservation)


@patch("payment.services.payment_service.stripe.Transfer.create")
@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_charge_reservation_owner_and_admin(mock_task, mock_transfer, reservation):
    admin = UserFactory(stripe_account_id="acct_admin")
    owner = UserFactory(stripe_account_id="acct_owner")
    reservation.logement.admin = admin
    reservation.logement.owner = owner
    reservation.admin_transferred = False
    reservation.transferred = False
    payment_service.transfer_funds(reservation)
    assert mock_transfer.called


@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_charge_reservation_missing_admin_account(mock_task, reservation):
    reservation.logement.admin = UserFactory(stripe_account_id=None)
    reservation.admin_transferred = False
    reservation.transferred = False
    payment_service.transfer_funds(reservation)  # Should log error, not raise


@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_charge_reservation_missing_owner_account(mock_task, reservation):
    reservation.logement.owner = UserFactory(stripe_account_id=None)
    reservation.transferred = False
    payment_service.transfer_funds(reservation)  # Should log error, not raise


@patch("payment.services.payment_service.stripe.Refund.create")
@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_refund_payment(mock_task, mock_refund, reservation):
    mock_refund.return_value = MagicMock(id="re_123")
    result = payment_service.refund_payment(reservation, refund="full", amount_cents=5000)
    assert result.id == "re_123"


@patch("payment.services.payment_service.stripe.Refund.create")
@patch("payment.services.payment_service.PaymentTask.objects.get_or_create", return_value=(MagicMock(), True))
def test_refund_payment_already_refunded(mock_task, mock_refund, reservation):
    reservation.refunded = True
    with pytest.raises(Exception):
        payment_service.refund_payment(reservation, refund="full", amount_cents=5000)


@patch(
    "payment.services.payment_service.stripe.checkout.Session.create",
    side_effect=payment_service.stripe.error.StripeError("fail"),
)
@patch("payment.services.payment_service.create_stripe_customer_if_not_exists", return_value="cus_123")
def test_create_stripe_checkout_session_with_deposit_stripe_error(mock_customer, mock_stripe, reservation):
    dummy_request = DummyRequest()
    with pytest.raises(payment_service.stripe.error.StripeError):
        payment_service.create_stripe_checkout_session_with_deposit(reservation, dummy_request)


