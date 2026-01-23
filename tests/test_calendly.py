"""Tests for the Calendly API client."""

import re

import pytest
from pytest_httpx import HTTPXMock

from src.calendly import CalendlyClient


@pytest.fixture
def client():
    """Create a Calendly client with a test token."""
    return CalendlyClient(api_token="test-token")


@pytest.fixture
def mock_user_response():
    """Mock response for /users/me endpoint."""
    return {
        "resource": {
            "uri": "https://api.calendly.com/users/test-user-123",
            "name": "Acme Dental",
            "email": "test@acme-dental.com",
            "current_organization": "https://api.calendly.com/organizations/test-org-123",
            "scheduling_url": "https://calendly.com/acme-dental",
            "timezone": "Europe/London",
        }
    }


@pytest.fixture
def mock_event_types_response():
    """Mock response for /event_types endpoint."""
    return {
        "collection": [
            {
                "uri": "https://api.calendly.com/event_types/test-event-123",
                "name": "Dental Check Up",
                "duration": 30,
                "scheduling_url": "https://calendly.com/acme-dental/30min",
            }
        ],
        "pagination": {"count": 1, "next_page": None},
    }


@pytest.fixture
def mock_available_times_response():
    """Mock response for /event_type_available_times endpoint."""
    return {
        "collection": [
            {
                "start_time": "2026-01-24T09:00:00Z",
                "scheduling_url": "https://calendly.com/acme-dental/30min/2026-01-24T09:00:00Z",
                "invitees_remaining": 1,
                "status": "available",
            },
            {
                "start_time": "2026-01-24T09:30:00Z",
                "scheduling_url": "https://calendly.com/acme-dental/30min/2026-01-24T09:30:00Z",
                "invitees_remaining": 1,
                "status": "available",
            },
            {
                "start_time": "2026-01-24T10:00:00Z",
                "scheduling_url": "https://calendly.com/acme-dental/30min/2026-01-24T10:00:00Z",
                "invitees_remaining": 1,
                "status": "available",
            },
        ]
    }


@pytest.fixture
def mock_scheduled_events_response():
    """Mock response for /scheduled_events endpoint."""
    return {
        "collection": [
            {
                "uri": "https://api.calendly.com/scheduled_events/event-123",
                "name": "Dental Check Up",
                "status": "active",
                "start_time": "2026-01-25T10:00:00Z",
                "end_time": "2026-01-25T10:30:00Z",
            }
        ],
        "pagination": {"count": 1, "next_page": None},
    }


@pytest.fixture
def mock_scheduling_link_response():
    """Mock response for /scheduling_links endpoint."""
    return {
        "resource": {
            "booking_url": "https://calendly.com/d/abc-123/dental-check-up",
            "owner": "https://api.calendly.com/event_types/test-event-123",
            "owner_type": "EventType",
        }
    }


class TestCalendlyClient:
    """Tests for CalendlyClient."""

    def test_init_with_token(self):
        """Test client initialization with explicit token."""
        client = CalendlyClient(api_token="my-token")
        assert client.api_token == "my-token"
        assert "Bearer my-token" in client.headers["Authorization"]

    def test_init_without_token_raises(self, monkeypatch):
        """Test client raises error when no token provided."""
        monkeypatch.delenv("CALENDLY_API_TOKEN", raising=False)
        with pytest.raises(ValueError, match="CALENDLY_API_TOKEN is required"):
            CalendlyClient(api_token=None)

    def test_get_current_user(self, client, httpx_mock: HTTPXMock, mock_user_response):
        """Test fetching current user info."""
        httpx_mock.add_response(
            url="https://api.calendly.com/users/me",
            json=mock_user_response,
        )

        user = client.get_current_user()

        assert user["name"] == "Acme Dental"
        assert user["email"] == "test@acme-dental.com"
        assert client._user_uri == "https://api.calendly.com/users/test-user-123"

    def test_get_event_types(self, client, httpx_mock: HTTPXMock, mock_user_response, mock_event_types_response):
        """Test fetching event types."""
        httpx_mock.add_response(
            url="https://api.calendly.com/users/me",
            json=mock_user_response,
        )
        httpx_mock.add_response(
            url=re.compile(r"https://api\.calendly\.com/event_types.*"),
            json=mock_event_types_response,
        )

        event_types = client.get_event_types()

        assert len(event_types) == 1
        assert event_types[0]["name"] == "Dental Check Up"
        assert event_types[0]["duration"] == 30

    def test_get_available_times(
        self,
        client,
        httpx_mock: HTTPXMock,
        mock_user_response,
        mock_event_types_response,
        mock_available_times_response,
    ):
        """Test fetching available time slots."""
        httpx_mock.add_response(
            url="https://api.calendly.com/users/me",
            json=mock_user_response,
        )
        httpx_mock.add_response(
            url=re.compile(r"https://api\.calendly\.com/event_types\?.*"),
            json=mock_event_types_response,
        )
        httpx_mock.add_response(
            url=re.compile(r"https://api\.calendly\.com/event_type_available_times.*"),
            json=mock_available_times_response,
        )

        slots = client.get_available_times()

        assert len(slots) == 3
        assert slots[0]["start_time"] == "2026-01-24T09:00:00Z"
        assert "scheduling_url" in slots[0]

    def test_format_available_slots(
        self,
        client,
        httpx_mock: HTTPXMock,
        mock_user_response,
        mock_event_types_response,
        mock_available_times_response,
    ):
        """Test formatting slots for display."""
        httpx_mock.add_response(
            url="https://api.calendly.com/users/me",
            json=mock_user_response,
        )
        httpx_mock.add_response(
            url=re.compile(r"https://api\.calendly\.com/event_types\?.*"),
            json=mock_event_types_response,
        )
        httpx_mock.add_response(
            url=re.compile(r"https://api\.calendly\.com/event_type_available_times.*"),
            json=mock_available_times_response,
        )

        formatted = client.format_available_slots(max_slots=2)

        assert len(formatted) == 2
        assert "date" in formatted[0]
        assert "time" in formatted[0]
        assert "booking_url" in formatted[0]
        assert formatted[0]["time"] == "09:00 AM"

    def test_get_scheduled_events(
        self, client, httpx_mock: HTTPXMock, mock_user_response, mock_scheduled_events_response
    ):
        """Test fetching scheduled events."""
        httpx_mock.add_response(
            url="https://api.calendly.com/users/me",
            json=mock_user_response,
        )
        httpx_mock.add_response(
            url=re.compile(r"https://api\.calendly\.com/scheduled_events\?.*"),
            json=mock_scheduled_events_response,
        )

        events = client.get_scheduled_events(email="test@example.com")

        assert len(events) == 1
        assert events[0]["status"] == "active"

    def test_create_scheduling_link(
        self,
        client,
        httpx_mock: HTTPXMock,
        mock_user_response,
        mock_event_types_response,
        mock_scheduling_link_response,
    ):
        """Test creating a single-use scheduling link."""
        httpx_mock.add_response(
            url="https://api.calendly.com/users/me",
            json=mock_user_response,
        )
        httpx_mock.add_response(
            url=re.compile(r"https://api\.calendly\.com/event_types\?.*"),
            json=mock_event_types_response,
        )
        httpx_mock.add_response(
            url="https://api.calendly.com/scheduling_links",
            method="POST",
            json=mock_scheduling_link_response,
        )

        link = client.create_scheduling_link()

        assert "booking_url" in link
        assert "calendly.com" in link["booking_url"]

    def test_cancel_event(self, client, httpx_mock: HTTPXMock):
        """Test cancelling an event."""
        httpx_mock.add_response(
            url="https://api.calendly.com/scheduled_events/event-123/cancellation",
            method="POST",
            json={"resource": {"canceled_by": "user"}},
        )

        result = client.cancel_event("event-123", reason="No longer needed")

        assert result["canceled_by"] == "user"

    def test_get_booking_url_for_slot(self, client):
        """Test extracting booking URL from a slot."""
        slot = {
            "start_time": "2026-01-24T09:00:00Z",
            "scheduling_url": "https://calendly.com/acme/30min/2026-01-24T09:00:00Z",
        }

        url = client.get_booking_url_for_slot(slot)

        assert url == "https://calendly.com/acme/30min/2026-01-24T09:00:00Z"
