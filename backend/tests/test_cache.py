"""Tests for the scheduling cache."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from src.cache import CacheEntry, SchedulingCache


class TestCacheEntry:
    """Tests for the CacheEntry class."""

    def test_is_expired_returns_false_when_fresh(self):
        """Test that fresh entries are not expired."""
        entry = CacheEntry(data={"test": "data"}, ttl_seconds=60)
        assert not entry.is_expired()

    def test_is_expired_returns_true_when_old(self):
        """Test that old entries are expired."""
        entry = CacheEntry(
            data={"test": "data"},
            cached_at=datetime.now(UTC) - timedelta(seconds=120),
            ttl_seconds=60,
        )
        assert entry.is_expired()

    def test_age_seconds(self):
        """Test age calculation."""
        entry = CacheEntry(
            data={"test": "data"},
            cached_at=datetime.now(UTC) - timedelta(seconds=30),
        )
        age = entry.age_seconds()
        assert 29 <= age <= 31  # Allow small timing variance


class TestSchedulingCache:
    """Tests for the SchedulingCache class."""

    def test_init_sets_defaults(self):
        """Test that initialization sets default values."""
        cache = SchedulingCache()
        assert cache.sync_interval_minutes == 2
        assert cache.availability_ttl == 180
        assert cache.bookings_ttl == 300

    def test_init_accepts_custom_values(self):
        """Test that initialization accepts custom values."""
        cache = SchedulingCache(
            sync_interval_minutes=5,
            availability_ttl_seconds=300,
            bookings_ttl_seconds=600,
        )
        assert cache.sync_interval_minutes == 5
        assert cache.availability_ttl == 300
        assert cache.bookings_ttl == 600

    def test_get_availability_returns_cached_data(self):
        """Test that cached availability is returned."""
        cache = SchedulingCache()
        mock_slots = [{"date": "Monday", "time": "09:00 AM"}]

        # Manually set cache
        cache._availability_cache = CacheEntry(data=mock_slots)

        result = cache.get_availability()
        assert result == mock_slots
        assert cache._stats["cache_hits"] == 1

    def test_get_availability_fetches_on_miss(self):
        """Test that availability is fetched on cache miss."""
        cache = SchedulingCache()
        mock_slots = [{"date": "Monday", "time": "09:00 AM"}]

        with patch.object(cache, "_get_calendly_client") as mock_client:
            mock_client.return_value.format_available_slots.return_value = mock_slots

            result = cache.get_availability()

            assert result == mock_slots
            assert cache._stats["cache_misses"] == 1
            assert cache._availability_cache is not None

    def test_get_availability_filters_morning(self):
        """Test that morning filter works."""
        cache = SchedulingCache()
        mock_slots = [
            {"date": "Monday", "time": "09:00 AM"},
            {"date": "Monday", "time": "02:00 PM"},
        ]
        cache._availability_cache = CacheEntry(data=mock_slots)

        result = cache.get_availability(time_preference="morning")
        assert len(result) == 1
        assert result[0]["time"] == "09:00 AM"

    def test_get_availability_filters_afternoon(self):
        """Test that afternoon filter works."""
        cache = SchedulingCache()
        mock_slots = [
            {"date": "Monday", "time": "09:00 AM"},
            {"date": "Monday", "time": "02:00 PM"},
        ]
        cache._availability_cache = CacheEntry(data=mock_slots)

        result = cache.get_availability(time_preference="afternoon")
        assert len(result) == 1
        assert result[0]["time"] == "02:00 PM"

    def test_get_availability_force_refresh(self):
        """Test that force_refresh bypasses cache."""
        cache = SchedulingCache()
        old_slots = [{"date": "Monday", "time": "09:00 AM"}]
        new_slots = [{"date": "Tuesday", "time": "10:00 AM"}]

        cache._availability_cache = CacheEntry(data=old_slots)

        with patch.object(cache, "_get_calendly_client") as mock_client:
            mock_client.return_value.format_available_slots.return_value = new_slots

            result = cache.get_availability(force_refresh=True)

            assert result == new_slots
            assert cache._stats["cache_misses"] == 1

    def test_get_bookings_returns_cached_data(self):
        """Test that cached bookings are returned."""
        cache = SchedulingCache()
        mock_events = [{"name": "Dental Check-up"}]

        cache._bookings_cache["john@example.com"] = CacheEntry(data=mock_events)

        result = cache.get_bookings("john@example.com")
        assert result == mock_events
        assert cache._stats["cache_hits"] == 1

    def test_get_bookings_fetches_on_miss(self):
        """Test that bookings are fetched on cache miss."""
        cache = SchedulingCache()
        mock_events = [{"name": "Dental Check-up"}]

        with patch.object(cache, "_get_calendly_client") as mock_client:
            mock_client.return_value.get_scheduled_events.return_value = mock_events

            result = cache.get_bookings("john@example.com")

            assert result == mock_events
            assert cache._stats["cache_misses"] == 1
            assert "john@example.com" in cache._bookings_cache

    def test_invalidate_availability(self):
        """Test that availability cache is invalidated."""
        cache = SchedulingCache()
        cache._availability_cache = CacheEntry(data=[{"test": "data"}])

        cache.invalidate_availability()

        assert cache._availability_cache is None
        assert cache._stats["webhook_invalidations"] == 1

    def test_invalidate_bookings_specific_email(self):
        """Test that specific email bookings are invalidated."""
        cache = SchedulingCache()
        cache._bookings_cache["john@example.com"] = CacheEntry(data=[])
        cache._bookings_cache["jane@example.com"] = CacheEntry(data=[])

        cache.invalidate_bookings("john@example.com")

        assert "john@example.com" not in cache._bookings_cache
        assert "jane@example.com" in cache._bookings_cache

    def test_invalidate_bookings_all(self):
        """Test that all bookings are invalidated."""
        cache = SchedulingCache()
        cache._bookings_cache["john@example.com"] = CacheEntry(data=[])
        cache._bookings_cache["jane@example.com"] = CacheEntry(data=[])

        cache.invalidate_bookings()

        assert len(cache._bookings_cache) == 0

    def test_session_data(self):
        """Test session data management."""
        cache = SchedulingCache()
        thread_id = "test-thread-123"

        session = cache.get_session_data(thread_id)
        assert "created_at" in session
        assert session["availability_snapshot"] is None

        # Set session availability
        slots = [{"date": "Monday", "time": "09:00 AM"}]
        cache.set_session_availability(thread_id, slots)

        assert cache.get_session_availability(thread_id) == slots

        # Clear session
        cache.clear_session(thread_id)
        assert cache.get_session_availability(thread_id) is None

    def test_get_stats(self):
        """Test stats retrieval."""
        cache = SchedulingCache()

        # Simulate some activity
        cache._stats["cache_hits"] = 10
        cache._stats["cache_misses"] = 5

        stats = cache.get_stats()

        assert stats["cache_hits"] == 10
        assert stats["cache_misses"] == 5
        assert stats["total_requests"] == 15
        assert stats["hit_rate_percent"] == 66.7

    def test_start_and_stop(self):
        """Test starting and stopping the scheduler."""
        cache = SchedulingCache()

        # Mock the sync to avoid actual API calls
        with patch.object(cache, "_sync_availability"):
            cache.start()
            assert cache._scheduler is not None

            cache.stop()
            assert cache._scheduler is None

    def test_graceful_fallback_on_error(self):
        """Test that stale cache is returned on API error."""
        cache = SchedulingCache()
        stale_slots = [{"date": "Monday", "time": "09:00 AM"}]

        # Set expired cache
        cache._availability_cache = CacheEntry(
            data=stale_slots,
            cached_at=datetime.now(UTC) - timedelta(seconds=300),
            ttl_seconds=60,
        )

        with patch.object(cache, "_get_calendly_client") as mock_client:
            mock_client.return_value.format_available_slots.side_effect = Exception("API Error")

            # Should return stale cache instead of raising
            result = cache.get_availability()
            assert result == stale_slots
