"""Scheduling cache for Acme Dental AI Agent.

This module provides a caching layer between the agent and Calendly API
to reduce latency and improve reliability during conversations.
"""

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from src.logging_config import get_logger

logger = get_logger("cache")


@dataclass
class CacheEntry:
    """A cached entry with expiration tracking."""

    data: Any
    cached_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: int = 120  # 2 minutes default

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        age = (datetime.now(UTC) - self.cached_at).total_seconds()
        return age > self.ttl_seconds

    def age_seconds(self) -> float:
        """Get the age of this cache entry in seconds."""
        return (datetime.now(UTC) - self.cached_at).total_seconds()


class SchedulingCache:
    """Cache for Calendly scheduling data with background sync.

    This cache provides:
    - Background sync every N minutes to keep availability fresh
    - Session-level caching to avoid re-fetching during a conversation
    - Webhook integration to invalidate cache on booking events
    - Graceful fallback to live API if cache is empty/stale

    Usage:
        cache = SchedulingCache()
        cache.start()  # Start background sync

        # Get availability (from cache or API)
        slots = cache.get_availability()

        # Invalidate on webhook
        cache.invalidate_availability()

        cache.stop()  # Stop background sync
    """

    def __init__(
        self,
        sync_interval_minutes: int = 2,
        availability_ttl_seconds: int = 180,  # 3 minutes
        bookings_ttl_seconds: int = 300,  # 5 minutes
    ):
        """Initialize the scheduling cache.

        Args:
            sync_interval_minutes: How often to sync availability in background
            availability_ttl_seconds: TTL for availability cache entries
            bookings_ttl_seconds: TTL for bookings cache entries
        """
        self.sync_interval_minutes = sync_interval_minutes
        self.availability_ttl = availability_ttl_seconds
        self.bookings_ttl = bookings_ttl_seconds

        # Cache storage
        self._availability_cache: CacheEntry | None = None
        self._bookings_cache: dict[str, CacheEntry] = {}  # email -> bookings
        self._session_cache: dict[str, dict] = {}  # thread_id -> session data

        # Thread safety
        self._lock = threading.RLock()

        # Background scheduler
        self._scheduler: BackgroundScheduler | None = None
        self._calendly_client = None

        # Stats
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "sync_count": 0,
            "last_sync": None,
            "webhook_invalidations": 0,
        }

        logger.info(
            f"SchedulingCache initialized (sync_interval={sync_interval_minutes}min, "
            f"availability_ttl={availability_ttl_seconds}s, bookings_ttl={bookings_ttl_seconds}s)"
        )

    def _get_calendly_client(self):
        """Lazy-load the Calendly client to avoid circular imports."""
        if self._calendly_client is None:
            from src.calendly import get_calendly_client

            self._calendly_client = get_calendly_client()
        return self._calendly_client

    def start(self) -> None:
        """Start the background sync scheduler."""
        if self._scheduler is not None:
            logger.warning("Scheduler already running")
            return

        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            self._sync_availability,
            "interval",
            minutes=self.sync_interval_minutes,
            id="availability_sync",
            next_run_time=datetime.now(),  # Run immediately on start
        )
        self._scheduler.start()
        logger.info(f"Background sync started (every {self.sync_interval_minutes} minutes)")

    def stop(self) -> None:
        """Stop the background sync scheduler."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("Background sync stopped")

    def _sync_availability(self) -> None:
        """Background job to sync availability from Calendly."""
        logger.debug("Running background availability sync")
        try:
            client = self._get_calendly_client()
            slots = client.format_available_slots(max_slots=100)

            with self._lock:
                self._availability_cache = CacheEntry(
                    data=slots,
                    ttl_seconds=self.availability_ttl,
                )
                self._stats["sync_count"] += 1
                self._stats["last_sync"] = datetime.now(UTC).isoformat()

            logger.info(f"Synced {len(slots)} availability slots from Calendly")
        except Exception as e:
            logger.error(f"Background sync failed: {e}")

    def get_availability(
        self,
        time_preference: str = "all",
        force_refresh: bool = False,
    ) -> list[dict[str, str]]:
        """Get available appointment slots.

        Args:
            time_preference: Filter by 'morning', 'afternoon', or 'all'
            force_refresh: Force a fresh fetch from Calendly API

        Returns:
            List of formatted availability slots
        """
        with self._lock:
            # Check cache first
            if not force_refresh and self._availability_cache and not self._availability_cache.is_expired():
                self._stats["cache_hits"] += 1
                age = self._availability_cache.age_seconds()
                logger.debug(f"Cache HIT for availability (age={age:.1f}s)")
                slots = self._availability_cache.data
            else:
                # Cache miss or expired - fetch from API
                self._stats["cache_misses"] += 1
                logger.debug("Cache MISS for availability - fetching from Calendly")

                try:
                    client = self._get_calendly_client()
                    slots = client.format_available_slots(max_slots=100)

                    # Update cache
                    self._availability_cache = CacheEntry(
                        data=slots,
                        ttl_seconds=self.availability_ttl,
                    )
                    logger.info(f"Fetched and cached {len(slots)} slots")
                except Exception as e:
                    logger.error(f"Failed to fetch availability: {e}")
                    # Return stale cache if available
                    if self._availability_cache:
                        logger.warning("Returning stale cache due to API error")
                        slots = self._availability_cache.data
                    else:
                        raise

        # Filter by time preference
        if time_preference == "morning":
            slots = [s for s in slots if "AM" in s.get("time", "")]
        elif time_preference == "afternoon":
            slots = [s for s in slots if "PM" in s.get("time", "")]

        return slots

    def get_bookings(self, email: str, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Get bookings for a patient by email.

        Args:
            email: Patient's email address
            force_refresh: Force a fresh fetch from Calendly API

        Returns:
            List of scheduled events for the email
        """
        email_lower = email.lower()

        with self._lock:
            cached = self._bookings_cache.get(email_lower)

            if not force_refresh and cached and not cached.is_expired():
                self._stats["cache_hits"] += 1
                logger.debug(f"Cache HIT for bookings ({email_lower})")
                return cached.data

            # Cache miss - fetch from API
            self._stats["cache_misses"] += 1
            logger.debug(f"Cache MISS for bookings ({email_lower})")

            try:
                client = self._get_calendly_client()
                events = client.get_scheduled_events(email=email)

                # Update cache
                self._bookings_cache[email_lower] = CacheEntry(
                    data=events,
                    ttl_seconds=self.bookings_ttl,
                )
                return events
            except Exception as e:
                logger.error(f"Failed to fetch bookings for {email}: {e}")
                if cached:
                    logger.warning("Returning stale cache due to API error")
                    return cached.data
                raise

    def invalidate_availability(self) -> None:
        """Invalidate the availability cache (e.g., on webhook)."""
        with self._lock:
            self._availability_cache = None
            self._stats["webhook_invalidations"] += 1
            logger.info("Availability cache invalidated")

    def invalidate_bookings(self, email: str | None = None) -> None:
        """Invalidate bookings cache.

        Args:
            email: Specific email to invalidate, or None for all
        """
        with self._lock:
            if email:
                self._bookings_cache.pop(email.lower(), None)
                logger.info(f"Bookings cache invalidated for {email}")
            else:
                self._bookings_cache.clear()
                logger.info("All bookings cache invalidated")
            self._stats["webhook_invalidations"] += 1

    # Session-level caching for conversation context
    def get_session_data(self, thread_id: str) -> dict:
        """Get session-specific cached data.

        Args:
            thread_id: The conversation thread ID

        Returns:
            Session data dictionary
        """
        with self._lock:
            if thread_id not in self._session_cache:
                self._session_cache[thread_id] = {
                    "created_at": datetime.now(UTC).isoformat(),
                    "availability_snapshot": None,
                    "selected_slot": None,
                    "patient_info": {},
                }
            return self._session_cache[thread_id]

    def set_session_availability(self, thread_id: str, slots: list[dict]) -> None:
        """Cache availability for a specific session.

        This prevents re-fetching during the same conversation.
        """
        with self._lock:
            session = self.get_session_data(thread_id)
            session["availability_snapshot"] = slots
            session["snapshot_time"] = datetime.now(UTC).isoformat()
            logger.debug(f"Session {thread_id[:8]}... cached {len(slots)} slots")

    def get_session_availability(self, thread_id: str) -> list[dict] | None:
        """Get cached availability for a session if still valid."""
        with self._lock:
            session = self._session_cache.get(thread_id, {})
            return session.get("availability_snapshot")

    def clear_session(self, thread_id: str) -> None:
        """Clear session data when conversation ends."""
        with self._lock:
            self._session_cache.pop(thread_id, None)
            logger.debug(f"Session {thread_id[:8]}... cleared")

    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["cache_hits"] + self._stats["cache_misses"]
            hit_rate = (self._stats["cache_hits"] / total * 100) if total > 0 else 0
            return {
                **self._stats,
                "total_requests": total,
                "hit_rate_percent": round(hit_rate, 1),
                "availability_cached": self._availability_cache is not None,
                "bookings_cached_count": len(self._bookings_cache),
                "active_sessions": len(self._session_cache),
            }


# Global cache instance
_cache: SchedulingCache | None = None


def get_scheduling_cache() -> SchedulingCache:
    """Get or create the global scheduling cache instance."""
    global _cache
    if _cache is None:
        _cache = SchedulingCache()
    return _cache


def start_cache() -> SchedulingCache:
    """Initialize and start the scheduling cache."""
    cache = get_scheduling_cache()
    cache.start()
    return cache


def stop_cache() -> None:
    """Stop the scheduling cache."""
    global _cache
    if _cache is not None:
        _cache.stop()
