"""Tests for the LangGraph agent and its tools."""

from unittest.mock import patch

from src.agent import (
    SYSTEM_PROMPT,
    TOOLS,
    answer_faq,
    cancel_booking,
    check_availability,
    find_booking,
    get_booking_link,
    get_reschedule_options,
)


class TestCheckAvailability:
    """Tests for the check_availability tool."""

    def test_returns_formatted_slots(self):
        """Test that available slots are returned in a readable format."""
        mock_slots = [
            {
                "date": "Monday, January 26, 2026",
                "time": "09:00 AM",
                "iso_time": "2026-01-26T09:00:00Z",
                "booking_url": "https://calendly.com/test",
            },
            {
                "date": "Monday, January 26, 2026",
                "time": "09:30 AM",
                "iso_time": "2026-01-26T09:30:00Z",
                "booking_url": "https://calendly.com/test2",
            },
        ]

        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_availability.return_value = mock_slots

            result = check_availability.invoke({"time_preference": "all"})

            assert "Available appointment slots" in result
            assert "Monday, January 26, 2026" in result
            assert "09:00 AM" in result
            assert "09:30 AM" in result

    def test_filters_morning_slots(self):
        """Test that morning preference filters to AM slots only."""
        # Cache returns filtered results based on time_preference
        mock_slots = [
            {
                "date": "Monday, January 26, 2026",
                "time": "09:00 AM",
                "iso_time": "2026-01-26T09:00:00Z",
                "booking_url": "https://calendly.com/test",
            },
        ]

        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_availability.return_value = mock_slots

            result = check_availability.invoke({"time_preference": "morning"})

            assert "09:00 AM" in result
            assert "02:00 PM" not in result

    def test_handles_no_slots(self):
        """Test handling when no slots are available."""
        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_availability.return_value = []

            result = check_availability.invoke({"time_preference": "all"})

            assert "No available slots" in result

    def test_handles_api_error(self):
        """Test graceful handling of API errors."""
        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_availability.side_effect = Exception("API Error")

            result = check_availability.invoke({"time_preference": "all"})

            assert "Sorry" in result
            assert "Error" in result


class TestGetBookingLink:
    """Tests for the get_booking_link tool."""

    def test_returns_booking_details(self):
        """Test that booking link is returned with correct details."""
        mock_formatted = [
            {
                "date": "Monday, January 26, 2026",
                "time": "09:00 AM",
                "iso_time": "2026-01-26T09:00:00Z",
                "booking_url": "https://calendly.com/book/123",
            },
            {
                "date": "Monday, January 26, 2026",
                "time": "09:30 AM",
                "iso_time": "2026-01-26T09:30:00Z",
                "booking_url": "https://calendly.com/book/456",
            },
        ]

        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_availability.return_value = mock_formatted

            result = get_booking_link.invoke(
                {
                    "selected_date": "Monday, January 26, 2026",
                    "selected_time": "09:00 AM",
                    "patient_name": "John Doe",
                    "patient_email": "john@example.com",
                }
            )

            assert "John Doe" in result
            assert "john@example.com" in result
            assert "https://calendly.com/book/123" in result
            assert "Monday, January 26, 2026" in result

    def test_partial_date_match(self):
        """Test that partial date matches work (e.g., just 'Monday')."""
        mock_formatted = [
            {
                "date": "Monday, January 26, 2026",
                "time": "02:30 PM",
                "iso_time": "2026-01-26T14:30:00Z",
                "booking_url": "https://calendly.com/book/789",
            },
        ]

        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_availability.return_value = mock_formatted

            result = get_booking_link.invoke(
                {
                    "selected_date": "Monday",
                    "selected_time": "2:30 PM",
                    "patient_name": "Jane Doe",
                    "patient_email": "jane@example.com",
                }
            )

            assert "Jane Doe" in result
            assert "Monday, January 26, 2026" in result

    def test_no_matching_slot(self):
        """Test handling when no matching slot is found."""
        mock_formatted = [
            {
                "date": "Monday, January 26, 2026",
                "time": "09:00 AM",
                "iso_time": "2026-01-26T09:00:00Z",
                "booking_url": "https://calendly.com/book/123",
            },
        ]

        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_availability.return_value = mock_formatted

            result = get_booking_link.invoke(
                {
                    "selected_date": "Friday",
                    "selected_time": "5:00 PM",
                    "patient_name": "John Doe",
                    "patient_email": "john@example.com",
                }
            )

            assert "couldn't find" in result.lower()


class TestFindBooking:
    """Tests for the find_booking tool."""

    def test_finds_existing_booking(self):
        """Test finding an existing booking by email."""
        mock_events = [
            {
                "name": "Dental Check-up",
                "start_time": "2026-01-26T09:00:00Z",
                "status": "active",
                "uri": "https://api.calendly.com/scheduled_events/abc123",
            }
        ]

        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_bookings.return_value = mock_events

            result = find_booking.invoke({"patient_email": "john@example.com"})

            assert "Found 1 appointment" in result
            assert "Dental Check-up" in result
            assert "active" in result

    def test_no_booking_found(self):
        """Test handling when no booking is found."""
        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_bookings.return_value = []

            result = find_booking.invoke({"patient_email": "unknown@example.com"})

            assert "No upcoming appointments found" in result
            assert "unknown@example.com" in result


class TestCancelBooking:
    """Tests for the cancel_booking tool."""

    def test_successful_cancellation(self):
        """Test successful booking cancellation."""
        with patch("src.agent.get_calendly_client") as mock_client:
            mock_client.return_value.cancel_event.return_value = {"status": "cancelled"}

            result = cancel_booking.invoke({"event_id": "abc123", "reason": "No longer needed"})

            assert "cancelled successfully" in result

    def test_cancellation_error(self):
        """Test handling of cancellation error."""
        with patch("src.agent.get_calendly_client") as mock_client:
            mock_client.return_value.cancel_event.side_effect = Exception("Not found")

            result = cancel_booking.invoke({"event_id": "invalid", "reason": "Test"})

            assert "Sorry" in result
            assert "Error" in result


class TestGetRescheduleOptions:
    """Tests for the get_reschedule_options tool."""

    def test_returns_reschedule_slots(self):
        """Test that reschedule options are returned."""
        mock_slots = [
            {
                "date": "Tuesday, January 27, 2026",
                "time": "10:00 AM",
                "iso_time": "2026-01-27T10:00:00Z",
                "booking_url": "https://calendly.com/test",
            },
        ]

        with patch("src.agent.get_scheduling_cache") as mock_cache:
            mock_cache.return_value.get_availability.return_value = mock_slots

            result = get_reschedule_options.invoke({"event_id": "abc123"})

            assert "Available slots for rescheduling" in result
            assert "Tuesday, January 27, 2026" in result
            assert "abc123" in result


class TestAnswerFaq:
    """Tests for the answer_faq tool."""

    def test_finds_answer_from_knowledge_base(self):
        """Test that FAQ answers are found from knowledge base."""
        result = answer_faq.invoke({"question": "How much does a check-up cost?"})

        assert "€60" in result

    def test_returns_clinic_info_for_unknown_question(self):
        """Test fallback to clinic info for unknown questions."""
        result = answer_faq.invoke({"question": "xyz123 unknown question abc456"})

        # Should return general clinic info
        assert "Dental Check-up" in result or "€60" in result


class TestToolsConfiguration:
    """Tests for the tools configuration."""

    def test_all_tools_defined(self):
        """Test that all required tools are defined."""
        tool_names = [tool.name for tool in TOOLS]

        assert "check_availability" in tool_names
        assert "get_booking_link" in tool_names
        assert "find_booking" in tool_names
        assert "cancel_booking" in tool_names
        assert "get_reschedule_options" in tool_names
        assert "answer_faq" in tool_names

    def test_tools_have_descriptions(self):
        """Test that all tools have descriptions."""
        for tool in TOOLS:
            assert tool.description, f"Tool {tool.name} missing description"


class TestSystemPrompt:
    """Tests for the system prompt configuration."""

    def test_prompt_contains_key_instructions(self):
        """Test that system prompt contains essential instructions."""
        assert "Acme Dental" in SYSTEM_PROMPT
        assert "booking" in SYSTEM_PROMPT.lower()
        assert "reschedul" in SYSTEM_PROMPT.lower()
        assert "cancel" in SYSTEM_PROMPT.lower()
        assert "€60" in SYSTEM_PROMPT

    def test_prompt_includes_clinic_details(self):
        """Test that system prompt includes clinic information."""
        assert "30 minutes" in SYSTEM_PROMPT
        assert "24 hours" in SYSTEM_PROMPT
