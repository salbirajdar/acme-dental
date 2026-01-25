"""Webhook handlers for Calendly events.

This module handles incoming webhooks from Calendly to keep
the scheduling cache in sync with real-time booking events.

Calendly Webhook Events:
- invitee.created: Someone booked an appointment
- invitee.canceled: Someone cancelled an appointment
- invitee_no_show: Invitee marked as no-show

Setup:
1. Create a webhook subscription in Calendly dashboard
2. Point it to: https://your-domain.com/webhooks/calendly
3. Select events: invitee.created, invitee.canceled
"""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from src.cache import get_scheduling_cache
from src.logging_config import get_logger

logger = get_logger("webhooks")


@dataclass
class WebhookEvent:
    """Parsed Calendly webhook event."""

    event_type: str
    event_uri: str
    invitee_email: str | None
    invitee_name: str | None
    scheduled_time: str | None
    payload: dict[str, Any]


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    webhook_signing_key: str,
) -> bool:
    """Verify the Calendly webhook signature.

    Args:
        payload: Raw request body bytes
        signature: The Calendly-Webhook-Signature header value
        webhook_signing_key: Your Calendly webhook signing key

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature or not webhook_signing_key:
        logger.warning("Missing signature or signing key")
        return False

    try:
        # Calendly uses HMAC-SHA256
        expected = hmac.new(
            webhook_signing_key.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Signature format: "v1,<timestamp>,<signature>"
        parts = signature.split(",")
        if len(parts) >= 3:
            actual_signature = parts[2]
        else:
            actual_signature = signature

        is_valid = hmac.compare_digest(expected, actual_signature)
        if not is_valid:
            logger.warning("Webhook signature verification failed")
        return is_valid
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False


def parse_webhook_event(payload: dict[str, Any]) -> WebhookEvent:
    """Parse a Calendly webhook payload into a WebhookEvent.

    Args:
        payload: The JSON payload from Calendly

    Returns:
        Parsed WebhookEvent object
    """
    event_type = payload.get("event", "unknown")
    event_payload = payload.get("payload", {})

    # Extract invitee info
    invitee = event_payload.get("invitee", {})
    event_info = event_payload.get("event", {})

    return WebhookEvent(
        event_type=event_type,
        event_uri=event_info.get("uri", ""),
        invitee_email=invitee.get("email"),
        invitee_name=invitee.get("name"),
        scheduled_time=event_info.get("start_time"),
        payload=payload,
    )


def handle_webhook_event(payload: dict[str, Any]) -> dict[str, str]:
    """Handle an incoming Calendly webhook event.

    This function:
    1. Parses the webhook payload
    2. Invalidates relevant cache entries
    3. Returns a status response

    Args:
        payload: The JSON payload from Calendly webhook

    Returns:
        Response dict with status and message
    """
    event = parse_webhook_event(payload)
    logger.info(f"Received webhook: {event.event_type} for {event.invitee_email}")

    cache = get_scheduling_cache()

    if event.event_type == "invitee.created":
        # New booking - invalidate availability cache
        cache.invalidate_availability()

        # Also invalidate bookings cache for this email
        if event.invitee_email:
            cache.invalidate_bookings(event.invitee_email)

        logger.info(f"Booking created: {event.invitee_name} ({event.invitee_email}) at {event.scheduled_time}")
        return {
            "status": "processed",
            "message": f"Booking created for {event.invitee_email}",
            "action": "cache_invalidated",
        }

    elif event.event_type == "invitee.canceled":
        # Cancellation - invalidate both caches
        cache.invalidate_availability()

        if event.invitee_email:
            cache.invalidate_bookings(event.invitee_email)

        logger.info(f"Booking cancelled: {event.invitee_name} ({event.invitee_email}) for {event.scheduled_time}")
        return {
            "status": "processed",
            "message": f"Cancellation processed for {event.invitee_email}",
            "action": "cache_invalidated",
        }

    elif event.event_type == "invitee_no_show":
        # No-show - just log, no cache action needed
        logger.info(f"No-show recorded: {event.invitee_email}")
        return {
            "status": "processed",
            "message": "No-show event recorded",
            "action": "logged",
        }

    else:
        logger.warning(f"Unknown webhook event type: {event.event_type}")
        return {
            "status": "ignored",
            "message": f"Unknown event type: {event.event_type}",
            "action": "none",
        }


def handle_webhook_ping() -> dict[str, str]:
    """Handle a webhook ping/test request from Calendly.

    Calendly sends a ping when you first set up a webhook to verify
    your endpoint is working.

    Returns:
        Success response
    """
    logger.info("Webhook ping received")
    return {
        "status": "ok",
        "message": "Webhook endpoint is active",
    }
