import tempfile
import pytest

import pytest
from django.utils import timezone
from datetime import timedelta
from django.contrib.sessions.models import Session
from administration.models import SiteVisit
from accounts.models import CustomUser
from administration.services.logs import parse_log_file
from administration.services.traffic import (
    get_traffic_dashboard_data,
    get_online_users,
    get_connected_users,
    get_online_visitors,
    get_traffic_data,
    get_visits_count,
    get_unique_visitors_count,
    get_recent_logs,
    clear_user_cache,
    clear_inactive_sessions,
)
from django.core.cache import cache
import uuid

LOG_LINES = """
[2024-01-01 12:00:00,123] INFO my.logger (utils.func:10) First info message
[2024-01-01 12:01:00,123] ERROR my.logger (utils.other:11) Something went wrong
[2024-01-01 12:02:00,123] WARNING other.logger (utils.alert:12) Be cautious
[2024-01-01 12:03:00,123] DEBUG my.logger (utils.debug:13) Debugging info
invalid line here
[2024-01-01 12:04:00,123] INFO my.logger (utils.final:14) Final info
""".strip()


@pytest.fixture
def log_file_path():
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as f:
        f.write(LOG_LINES)
        f.flush()
        yield f.name


def test_parse_log_file_no_file():
    logs, loggers = parse_log_file("nonexistent.log")
    assert logs == []
    assert loggers == set()


def test_parse_log_file_all(log_file_path):
    logs, loggers = parse_log_file(log_file_path)
    assert len(logs) == 5  # one line is invalid
    assert "my.logger" in loggers
    assert "other.logger" in loggers
    assert logs[0]["message"] == "Final info"  # Reversed


def test_parse_log_file_level_filter(log_file_path):
    logs, _ = parse_log_file(log_file_path, level="ERROR")
    assert len(logs) == 1
    assert logs[0]["level"] == "ERROR"


def test_parse_log_file_logger_filter(log_file_path):
    logs, _ = parse_log_file(log_file_path, logger_filter="other.logger")
    assert len(logs) == 1
    assert logs[0]["logger"] == "other.logger"


def test_parse_log_file_query_filter(log_file_path):
    logs, _ = parse_log_file(log_file_path, query="final")
    assert len(logs) == 1
    assert "final" in logs[0]["message"].lower()


def test_parse_log_file_combined_filters(log_file_path):
    logs, _ = parse_log_file(log_file_path, level="INFO", logger_filter="my.logger", query="first")
    assert len(logs) == 1
    assert logs[0]["message"] == "First info message"


def test_parse_log_file_invalid_line_ignored(log_file_path):
    logs, _ = parse_log_file(log_file_path)
    assert not any("invalid line" in log["message"] for log in logs)


@pytest.mark.django_db
def test_get_traffic_dashboard_data():
    SiteVisit.objects.create(
        ip_address="127.0.0.1",
        user_agent="test-agent",
        path="/test",
        timestamp=timezone.now(),
    )
    data = get_traffic_dashboard_data("day")
    assert "labels" in data
    assert "data" in data
    assert "total_visits" in data
    assert "unique_visitors" in data
    assert isinstance(data["recent_logs"], list)


@pytest.mark.django_db
def test_get_online_users():
    user = CustomUser.objects.create(username="user1", last_activity=timezone.now())
    count = get_online_users()
    assert count >= 1


@pytest.mark.django_db
def test_get_connected_users():
    user = CustomUser.objects.create(username="user2")
    count = get_connected_users()
    assert isinstance(count, int)


@pytest.mark.django_db
def test_get_online_visitors():
    session = Session.objects.create(
        session_key=str(uuid.uuid4()),
        expire_date=timezone.now() + timedelta(minutes=10),
        session_data="non-authenticated",
    )
    count = get_online_visitors()
    assert isinstance(count, int)


@pytest.mark.django_db
def test_get_traffic_data():
    SiteVisit.objects.create(
        ip_address="127.0.0.2",
        user_agent="test",
        path="/",
        timestamp=timezone.now(),
    )
    labels, data = get_traffic_data("day")
    assert isinstance(labels, list)
    assert isinstance(data, list)


@pytest.mark.django_db
def test_get_visits_count():
    now = timezone.now()
    SiteVisit.objects.create(
        ip_address="127.0.0.3",
        user_agent="test",
        path="/",
        timestamp=now,
    )
    count = get_visits_count(30)
    assert count >= 1


@pytest.mark.django_db
def test_get_unique_visitors_count():
    now = timezone.now()
    SiteVisit.objects.create(
        ip_address="127.0.0.4",
        user_agent="test",
        path="/",
        timestamp=now,
    )
    count = get_unique_visitors_count(30)
    assert count >= 1


@pytest.mark.django_db
def test_get_recent_logs():
    SiteVisit.objects.create(
        ip_address="127.0.0.5",
        user_agent="test",
        path="/",
        timestamp=timezone.now(),
    )
    logs = get_recent_logs(5)
    assert isinstance(logs, list)
    assert len(logs) > 0


def test_clear_user_cache():
    cache.set("user_99_data", "abc123")
    assert cache.get("user_99_data") == "abc123"
    clear_user_cache(99)
    assert cache.get("user_99_data") is None


@pytest.mark.django_db
def test_clear_inactive_sessions():
    session = Session.objects.create(
        session_key=str(uuid.uuid4()),
        expire_date=timezone.now() - timedelta(minutes=60),
        session_data="...",
    )
    clear_inactive_sessions()
    assert not Session.objects.filter(pk=session.pk)
