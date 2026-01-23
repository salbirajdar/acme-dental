"""Calendly API client for Acme Dental."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class CalendlyClient:
    """Client for interacting with the Calendly API."""

    BASE_URL = "https://api.calendly.com"

    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or os.getenv("CALENDLY_API_TOKEN")
        if not self.api_token:
            raise ValueError("CALENDLY_API_TOKEN is required")
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        self._user_uri: str | None = None
        self._organization_uri: str | None = None
        self._event_type_uri: str | None = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make an HTTP request to the Calendly API with retry logic."""
        url = f"{self.BASE_URL}{endpoint}"
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, url, headers=self.headers, **kwargs)
            response.raise_for_status()
            return response.json()

    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        data = self._request("GET", "/users/me")
        self._user_uri = data["resource"]["uri"]
        self._organization_uri = data["resource"]["current_organization"]
        return data["resource"]

    def get_event_types(self) -> list[dict[str, Any]]:
        """Get all event types for the current user."""
        if not self._user_uri:
            self.get_current_user()
        data = self._request("GET", "/event_types", params={"user": self._user_uri})
        if data["collection"]:
            self._event_type_uri = data["collection"][0]["uri"]
        return data["collection"]

    def get_available_times(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get available appointment slots.

        Args:
            start_time: Start of the time range (defaults to 1 hour from now)
            end_time: End of the time range (defaults to 7 days from start)

        Returns:
            List of available time slots with start_time and invitees_remaining
        """
        if not self._event_type_uri:
            self.get_event_types()

        if start_time is None:
            # Start 1 hour from now to ensure it's in the future
            start_time = datetime.now(UTC) + timedelta(hours=1)
        if end_time is None:
            end_time = start_time + timedelta(days=7)

        data = self._request(
            "GET",
            "/event_type_available_times",
            params={
                "event_type": self._event_type_uri,
                "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
                "end_time": end_time.strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
            },
        )
        return data.get("collection", [])

    def create_scheduling_link(self) -> dict[str, Any]:
        """Create a single-use scheduling link.

        Returns:
            Dict with booking_url for the single-use link
        """
        if not self._event_type_uri:
            self.get_event_types()

        payload = {
            "max_event_count": 1,
            "owner": self._event_type_uri,
            "owner_type": "EventType",
        }
        data = self._request("POST", "/scheduling_links", json=payload)
        return data.get("resource", data)

    def get_booking_url_for_slot(self, slot: dict[str, Any]) -> str:
        """Get the direct booking URL for a specific time slot.

        Args:
            slot: A slot from get_available_times()

        Returns:
            Direct URL to book this specific slot
        """
        return slot.get("scheduling_url", "")

    def format_available_slots(
        self,
        slots: list[dict[str, Any]] | None = None,
        max_slots: int = 10,
    ) -> list[dict[str, str]]:
        """Format available slots for display to users.

        Args:
            slots: List of slots (or None to fetch)
            max_slots: Maximum number of slots to return

        Returns:
            List of formatted slot info with date, time, and booking_url
        """
        if slots is None:
            slots = self.get_available_times()

        formatted = []
        for slot in slots[:max_slots]:
            start_time = datetime.fromisoformat(slot["start_time"].replace("Z", "+00:00"))
            formatted.append(
                {
                    "date": start_time.strftime("%A, %B %d, %Y"),
                    "time": start_time.strftime("%I:%M %p"),
                    "iso_time": slot["start_time"],
                    "booking_url": slot.get("scheduling_url", ""),
                }
            )
        return formatted

    def get_scheduled_events(
        self,
        email: str | None = None,
        status: str = "active",
    ) -> list[dict[str, Any]]:
        """Get scheduled events, optionally filtered by invitee email.

        Args:
            email: Filter by invitee email address
            status: Filter by status (active, canceled)

        Returns:
            List of scheduled events
        """
        if not self._user_uri:
            self.get_current_user()

        params = {
            "user": self._user_uri,
            "status": status,
        }
        if email:
            params["invitee_email"] = email

        data = self._request("GET", "/scheduled_events", params=params)
        return data.get("collection", [])

    def get_event_invitees(self, event_uuid: str) -> list[dict[str, Any]]:
        """Get invitees for a specific event.

        Args:
            event_uuid: The UUID of the scheduled event

        Returns:
            List of invitees for the event
        """
        data = self._request("GET", f"/scheduled_events/{event_uuid}/invitees")
        return data.get("collection", [])

    def cancel_event(self, event_uuid: str, reason: str = "Cancelled by user") -> dict[str, Any]:
        """Cancel a scheduled event.

        Args:
            event_uuid: The UUID of the event to cancel
            reason: Cancellation reason

        Returns:
            The cancellation response
        """
        data = self._request(
            "POST",
            f"/scheduled_events/{event_uuid}/cancellation",
            json={"reason": reason},
        )
        return data.get("resource", data)

    def reschedule_event(
        self,
        event_uuid: str,
        new_start_time: str,
    ) -> dict[str, Any]:
        """Reschedule an existing event to a new time.

        Note: Calendly API may require using invitee reschedule endpoint.

        Args:
            event_uuid: The UUID of the event to reschedule
            new_start_time: New ISO format datetime for the appointment

        Returns:
            The rescheduled event or reschedule link
        """
        # Get invitees for this event to get the invitee UUID
        invitees = self.get_event_invitees(event_uuid)
        if not invitees:
            raise ValueError("No invitees found for this event")

        invitee_uuid = invitees[0]["uri"].split("/")[-1]

        # Create reschedule - returns a new booking
        data = self._request(
            "POST",
            f"/scheduled_events/{event_uuid}/invitees/{invitee_uuid}/reschedule",
            json={"start_time": new_start_time},
        )
        return data.get("resource", data)


# Singleton instance for convenience
_client: CalendlyClient | None = None


def get_calendly_client() -> CalendlyClient:
    """Get or create a Calendly client instance."""
    global _client
    if _client is None:
        _client = CalendlyClient()
    return _client
