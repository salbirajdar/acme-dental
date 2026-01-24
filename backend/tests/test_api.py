"""Tests for the FastAPI endpoints."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set required env vars before importing the API module
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("CALENDLY_API_TOKEN", "test-token")

# Import the module to make it available for patching
import src.api  # noqa: E402


@pytest.fixture
def mock_cache():
    """Create a mock cache instance."""
    cache_instance = MagicMock()
    cache_instance.get_stats.return_value = {
        "cache_hits": 10,
        "cache_misses": 2,
        "hit_rate_percent": 83.3,
    }
    cache_instance.get_availability.return_value = [
        {"date": "Monday, January 27, 2026", "time": "09:00 AM"},
    ]
    cache_instance.get_bookings.return_value = []
    cache_instance._availability_cache = None
    return cache_instance


@pytest.fixture
def client(mock_cache):
    """Create a test client with mocked dependencies."""
    with (
        patch.object(src.api, "start_cache"),
        patch.object(src.api, "stop_cache"),
        patch.object(src.api, "create_acme_dental_agent") as mock_create_agent,
        patch.object(src.api, "get_scheduling_cache") as mock_get_cache,
    ):
        mock_get_cache.return_value = mock_cache
        mock_create_agent.return_value = MagicMock()

        # Set the global _agent to a mock
        src.api._agent = MagicMock()

        with TestClient(src.api.app) as test_client:
            yield test_client, mock_cache


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_returns_api_info(self, client):
        """Test that root endpoint returns API information."""
        test_client, _ = client
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Acme Dental AI Agent"
        assert "endpoints" in data


class TestHealthEndpoint:
    """Tests for the health endpoint."""

    def test_health_returns_status(self, client):
        """Test that health endpoint returns healthy status."""
        test_client, _ = client
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "cache_stats" in data


class TestChatEndpoint:
    """Tests for the chat endpoint."""

    def test_chat_returns_response(self, client):
        """Test that chat endpoint returns agent response."""
        test_client, _ = client
        with patch.object(src.api, "get_agent_response") as mock_response:
            mock_response.return_value = "Hello! How can I help you today?"

            response = test_client.post(
                "/chat",
                json={"message": "Hello", "thread_id": "test-123"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "Hello! How can I help you today?"
            assert data["thread_id"] == "test-123"

    def test_chat_uses_default_thread_id(self, client):
        """Test that chat uses default thread_id if not provided."""
        test_client, _ = client
        with patch.object(src.api, "get_agent_response") as mock_response:
            mock_response.return_value = "Hello!"

            response = test_client.post("/chat", json={"message": "Hello"})

            assert response.status_code == 200
            data = response.json()
            assert data["thread_id"] == "default"

    def test_chat_rejects_empty_message(self, client):
        """Test that empty messages are rejected."""
        test_client, _ = client
        response = test_client.post("/chat", json={"message": ""})

        assert response.status_code == 422  # Validation error

    def test_chat_handles_agent_error(self, client):
        """Test that agent errors are handled gracefully."""
        test_client, _ = client
        with patch.object(src.api, "get_agent_response") as mock_response:
            mock_response.side_effect = Exception("Agent error")

            response = test_client.post("/chat", json={"message": "Hello"})

            assert response.status_code == 500
            assert "Error processing request" in response.json()["detail"]


class TestWebhookEndpoint:
    """Tests for the Calendly webhook endpoint."""

    def test_webhook_handles_ping(self, client):
        """Test that webhook handles ping events."""
        test_client, _ = client
        response = test_client.post(
            "/webhooks/calendly",
            json={"event": "ping"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_webhook_handles_invitee_created(self, client):
        """Test that webhook handles booking events."""
        test_client, _ = client
        with patch.object(src.api, "handle_webhook_event") as mock_handler:
            mock_handler.return_value = {
                "status": "processed",
                "message": "Booking created",
                "action": "cache_invalidated",
            }

            response = test_client.post(
                "/webhooks/calendly",
                json={
                    "event": "invitee.created",
                    "payload": {
                        "invitee": {"email": "test@example.com", "name": "Test User"},
                        "event": {"uri": "test-uri", "start_time": "2026-01-27T09:00:00Z"},
                    },
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "processed"

    def test_webhook_handles_invitee_canceled(self, client):
        """Test that webhook handles cancellation events."""
        test_client, _ = client
        with patch.object(src.api, "handle_webhook_event") as mock_handler:
            mock_handler.return_value = {
                "status": "processed",
                "message": "Cancellation processed",
                "action": "cache_invalidated",
            }

            response = test_client.post(
                "/webhooks/calendly",
                json={
                    "event": "invitee.canceled",
                    "payload": {
                        "invitee": {"email": "test@example.com"},
                        "event": {"uri": "test-uri"},
                    },
                },
            )

            assert response.status_code == 200

    def test_webhook_rejects_invalid_json(self, client):
        """Test that invalid JSON is rejected."""
        test_client, _ = client
        response = test_client.post(
            "/webhooks/calendly",
            content="not json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400


class TestAvailabilityEndpoint:
    """Tests for the availability endpoint."""

    def test_get_availability(self, client):
        """Test getting availability."""
        test_client, _ = client
        response = test_client.get("/availability")

        assert response.status_code == 200
        data = response.json()
        assert "slots" in data
        assert isinstance(data["slots"], list)

    def test_get_availability_with_filter(self, client):
        """Test getting availability with time filter."""
        test_client, mock_cache = client
        response = test_client.get("/availability?time_preference=morning")

        assert response.status_code == 200
        mock_cache.get_availability.assert_called_with(time_preference="morning")


class TestBookingsEndpoint:
    """Tests for the bookings search endpoint."""

    def test_search_bookings(self, client):
        """Test searching bookings by email."""
        test_client, mock_cache = client
        mock_cache.get_bookings.return_value = [
            {"name": "Dental Check-up", "start_time": "2026-01-27T09:00:00Z"}
        ]

        response = test_client.post(
            "/bookings/search",
            json={"email": "test@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["count"] == 1

    def test_search_bookings_invalid_email(self, client):
        """Test that invalid email is rejected."""
        test_client, _ = client
        response = test_client.post(
            "/bookings/search",
            json={"email": "not-an-email"},
        )

        assert response.status_code == 422  # Validation error
