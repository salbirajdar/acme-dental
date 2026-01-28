"""LangGraph AI Agent for the Acme Dental Clinic."""

import os
import re
from collections import defaultdict
from collections.abc import Generator
from datetime import datetime
from typing import Annotated
from urllib.parse import urlencode

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.cache import get_scheduling_cache
from src.calendly import CLINIC_TIMEZONE, get_calendly_client
from src.knowledge_base import get_clinic_info, search_knowledge_base
from src.logging_config import get_logger

logger = get_logger("agent")

# System prompt for the dental receptionist agent
SYSTEM_PROMPT = """You are a friendly and professional AI receptionist for Acme Dental clinic.

Your role is to help patients with:
1. Booking new dental check-up appointments
2. Rescheduling existing appointments
3. Cancelling appointments
4. Answering questions about the clinic

IMPORTANT GUIDELINES:
- Respond in plain text only - no markdown formatting (no **, no ##, no bullet points with -)
- Do not use emojis
- Be warm, professional, and concise
- Always confirm details before making changes
- For bookings, you MUST collect: full name and email address
- Present available times in a clear, organized way (show 5-10 options)
- When providing booking links, explain that the patient needs to click the link to complete their booking
- If you can't find a patient's booking, ask them to verify their email address
- For FAQs, use the search_knowledge_base tool to find accurate answers

CLINIC DETAILS:
- Service: Dental Check-up (30 minutes)
- Price: €60 (€50 for students/seniors)
- Location: Acme Dental Lane
- Cancellation policy: Free cancellation up to 24 hours before; €20 fee for late cancellations

BOOKING FLOW:
1. Greet the patient and understand their intent
2. Use check_availability to show available slots (grouped by date)
3. Patient selects a date and time naturally (e.g., "Monday at 2:30 PM")
4. Collect their full name and email address
5. Use get_booking_link with the selected date, time, name, and email
6. Confirm the booking details and provide the link

Always be helpful and guide patients through the process step by step."""


@tool
def check_availability(
    time_preference: Annotated[
        str, "Time preference: 'morning' (9am-12pm), 'afternoon' (12pm-5pm), or 'all' (default)"
    ] = "all",
) -> str:
    """Check available appointment slots for dental check-ups.

    Use this tool when a patient wants to book an appointment or see available times.
    Returns a list of available time slots grouped by date.
    Use time_preference to filter: 'morning', 'afternoon', or 'all'.
    """
    logger.info(f"Tool: check_availability called (preference={time_preference})")
    try:
        # Use cache instead of direct Calendly API call
        cache = get_scheduling_cache()
        slots = cache.get_availability(time_preference=time_preference)

        if not slots:
            logger.warning("No available slots found")
            return "No available slots found in the next 7 days. Please try again later."

        # Group slots by date
        by_date: dict[str, list] = defaultdict(list)
        for slot in slots:
            by_date[slot["date"]].append(slot["time"])

        result = "Available appointment slots:\n\n"
        for date, times in list(by_date.items())[:5]:  # Show up to 5 days
            result += f"**{date}:** {', '.join(times)}\n"

        result += "\nJust tell me your preferred date and time (e.g., 'Monday at 2:30 PM')."
        logger.info(f"Returned slots across {len(by_date)} day(s) (from cache)")
        return result
    except Exception as e:
        logger.error(f"Error checking availability: {e}")
        return f"Sorry, I couldn't check availability right now. Error: {e}"


@tool
def get_booking_link(
    selected_date: Annotated[str, "The date the patient selected (e.g., 'Monday, January 27, 2026' or 'Monday')"],
    selected_time: Annotated[str, "The time the patient selected (e.g., '2:30 PM' or '14:30')"],
    patient_name: Annotated[str, "The patient's full name"],
    patient_email: Annotated[str, "The patient's email address"],
) -> str:
    """Get a booking link for a specific time slot.

    Use this tool after the patient has:
    1. Selected a date and time from the available options
    2. Provided their full name
    3. Provided their email address

    Returns a booking link the patient can use to complete their appointment.
    """
    logger.info(
        f"Tool: get_booking_link called (date={selected_date}, time={selected_time}, "
        f"name={patient_name}, email={patient_email})"
    )
    try:
        # Use cache instead of direct Calendly API call
        cache = get_scheduling_cache()
        slots = cache.get_availability()

        if not slots:
            logger.warning("No available slots found")
            return "No available slots found. Please check availability first."

        # Find the matching slot by date and time
        selected_slot = None
        selected_time_normalized = selected_time.upper().replace(" ", "")

        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

        for slot in slots:
            # Check if the date matches (partial match for flexibility)
            date_matches = False
            slot_date_lower = slot["date"].lower()
            selected_date_lower = selected_date.lower()

            # Match by full date string or substring (e.g., "Friday, February 06, 2026")
            if selected_date_lower in slot_date_lower or slot_date_lower in selected_date_lower:
                date_matches = True
            else:
                # Extract day name from selected date and match against slot day name
                selected_day = next((d for d in day_names if d in selected_date_lower), None)
                slot_day = next((d for d in day_names if d in slot_date_lower), None)
                if selected_day and slot_day and selected_day == slot_day:
                    date_matches = True

            if date_matches:
                # Check if the time matches - normalize both to "HH:MMAM/PM" format
                slot_time_normalized = slot["time"].upper().replace(" ", "")

                # Normalize selected time: ensure 2-digit hour (e.g., "2:00PM" -> "02:00PM")
                time_match = re.match(r"(\d{1,2}):?(\d{2})?\s*(AM|PM)?", selected_time_normalized, re.IGNORECASE)
                if time_match:
                    hour = time_match.group(1).zfill(2)
                    minutes = time_match.group(2) or "00"
                    ampm = (time_match.group(3) or "").upper()
                    selected_time_formatted = f"{hour}:{minutes}{ampm}"
                else:
                    selected_time_formatted = selected_time_normalized

                # Compare normalized times
                if selected_time_formatted == slot_time_normalized:
                    selected_slot = slot
                    break
                # Also try without AM/PM if not specified (match any slot at that hour:minute)
                if not time_match or not time_match.group(3):
                    slot_time_no_ampm = slot_time_normalized.replace("AM", "").replace("PM", "")
                    selected_no_ampm = selected_time_formatted.replace("AM", "").replace("PM", "")
                    if selected_no_ampm == slot_time_no_ampm:
                        selected_slot = slot
                        break

        if not selected_slot:
            logger.warning(f"No matching slot found for {selected_date} at {selected_time}")
            available_times = ", ".join([f"{s['date']} at {s['time']}" for s in slots[:5]])
            return (
                f"I couldn't find an available slot for {selected_date} at {selected_time}. "
                f"Please choose from the available times: {available_times}"
            )

        booking_url = selected_slot.get("booking_url", "")
        if not booking_url:
            # Fallback: get URL from raw slot data (direct API call as last resort)
            client = get_calendly_client()
            raw_slots = client.get_available_times()
            for raw_slot in raw_slots:
                formatted = client.format_available_slots([raw_slot])[0]
                if formatted["date"] == selected_slot["date"] and formatted["time"] == selected_slot["time"]:
                    booking_url = client.get_booking_url_for_slot(raw_slot)
                    break

        # Add pre-fill parameters for name and email
        if booking_url:
            prefill_params = urlencode({"name": patient_name, "email": patient_email})
            separator = "&" if "?" in booking_url else "?"
            booking_url = f"{booking_url}{separator}{prefill_params}"

        logger.info(f"Generated booking link for {selected_slot['date']} at {selected_slot['time']}")

        return f"""Booking details confirmed:
- Patient: {patient_name}
- Email: {patient_email}
- Date: {selected_slot["date"]}
- Time: {selected_slot["time"]}
- Duration: 30 minutes
- Service: Dental Check-up

Please click this link to complete your booking:
{booking_url}

You will receive a confirmation email at {patient_email} once the booking is complete."""
    except Exception as e:
        logger.error(f"Error generating booking link: {e}")
        return f"Sorry, I couldn't generate the booking link. Error: {e}"


@tool
def find_booking(
    patient_email: Annotated[str, "The patient's email address to search for"],
) -> str:
    """Find existing appointments for a patient by their email.

    Use this tool when a patient wants to:
    - View their existing appointment
    - Reschedule an appointment
    - Cancel an appointment
    """
    logger.info(f"Tool: find_booking called (email={patient_email})")
    try:
        # Use cache for bookings lookup
        cache = get_scheduling_cache()
        events = cache.get_bookings(patient_email)

        if not events:
            logger.info(f"No bookings found for {patient_email}")
            return (
                f"No upcoming appointments found for {patient_email}. "
                "Please check if this is the email you used when booking."
            )

        result = f"Found {len(events)} appointment(s) for {patient_email}:\n\n"
        for i, event in enumerate(events, 1):
            raw_time = event.get("start_time", "")
            if raw_time:
                utc_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                local_time = utc_time.astimezone(CLINIC_TIMEZONE)
                formatted_time = local_time.strftime("%A, %B %d, %Y at %I:%M %p")
            else:
                formatted_time = "Unknown"
            result += f"{i}. {event.get('name', 'Dental Check-up')} - {formatted_time}\n"
            result += f"   Status: {event.get('status', 'active')}\n"
            result += f"   Event ID: {event.get('uri', '').split('/')[-1]}\n\n"

        logger.info(f"Found {len(events)} booking(s) for {patient_email} (from cache)")
        return result
    except Exception as e:
        logger.error(f"Error finding booking: {e}")
        return f"Sorry, I couldn't search for bookings. Error: {e}"


@tool
def cancel_booking(
    event_id: Annotated[str, "The event ID of the appointment to cancel"],
    reason: Annotated[str, "The reason for cancellation"] = "Cancelled by patient",
) -> str:
    """Cancel an existing appointment.

    Use this tool after:
    1. Finding the patient's booking with find_booking
    2. Confirming they want to cancel

    Note: Cancellations less than 24 hours before the appointment may incur a €20 fee.
    """
    logger.info(f"Tool: cancel_booking called (event_id={event_id}, reason={reason})")
    try:
        client = get_calendly_client()
        client.cancel_event(event_id, reason=reason)

        # Invalidate cache since availability has changed
        cache = get_scheduling_cache()
        cache.invalidate_availability()
        logger.info(f"Successfully cancelled event {event_id}, cache invalidated")

        return """Appointment cancelled successfully.

A confirmation email will be sent shortly.

Remember: If you cancelled less than 24 hours before your appointment, a €20 late cancellation fee may apply.

Would you like to book a new appointment?"""
    except Exception as e:
        logger.error(f"Error cancelling booking: {e}")
        return f"Sorry, I couldn't cancel the appointment. Error: {e}"


@tool
def get_reschedule_options(
    event_id: Annotated[str, "The event ID of the appointment to reschedule"],
) -> str:
    """Get available slots for rescheduling an existing appointment.

    Use this tool after finding the patient's booking and confirming they want to reschedule.
    Shows available time slots they can reschedule to.
    """
    logger.info(f"Tool: get_reschedule_options called (event_id={event_id})")
    try:
        # Use cache for availability
        cache = get_scheduling_cache()
        slots = cache.get_availability()[:10]  # Limit to 10 for reschedule

        if not slots:
            logger.warning("No slots available for rescheduling")
            return "No available slots found for rescheduling. Please try again later."

        result = f"Available slots for rescheduling (Event ID: {event_id}):\n\n"
        for i, slot in enumerate(slots, 1):
            result += f"{i}. {slot['date']} at {slot['time']}\n"

        result += "\nPlease tell me which slot you'd like to reschedule to."
        result += "\nNote: Rescheduling less than 24 hours before your appointment may incur a fee."
        logger.info(f"Returned {len(slots)} reschedule options (from cache)")
        return result
    except Exception as e:
        logger.error(f"Error getting reschedule options: {e}")
        return f"Sorry, I couldn't get rescheduling options. Error: {e}"


@tool
def answer_faq(
    question: Annotated[str, "The patient's question about the clinic"],
) -> str:
    """Answer frequently asked questions about the clinic.

    Use this tool when patients ask about:
    - Prices and payment
    - What to bring
    - Cancellation policy
    - Insurance
    - Services offered
    - Or any other general questions
    """
    logger.info(f"Tool: answer_faq called (question={question[:50]}...)")
    # First try keyword search
    answer = search_knowledge_base(question)

    if answer:
        logger.info("Found answer in knowledge base")
        return answer

    # Fallback to clinic info for basic questions
    logger.info("No specific answer found, returning general clinic info")
    info = get_clinic_info()
    return f"""I don't have a specific answer for that question. Here's some general information:

- Service: {info["service"]} ({info["duration"]})
- Price: {info["price"]} (Students/Seniors: {info["student_price"]})
- Location: {info["location"]}
- Cancellation: Free up to {info["cancellation_notice"]} before; {info["late_cancel_fee"]} late fee

Is there something specific I can help you with?"""


# All tools available to the agent
TOOLS = [
    check_availability,
    get_booking_link,
    find_booking,
    cancel_booking,
    get_reschedule_options,
    answer_faq,
]


def create_acme_dental_agent(model_name: str = "claude-sonnet-4-20250514"):
    """Create the Acme Dental AI agent using LangGraph.

    Args:
        model_name: The Claude model to use

    Returns:
        A LangGraph agent ready to handle dental clinic interactions
    """
    logger.info(f"Creating Acme Dental agent with model: {model_name}")

    # Initialize the LLM
    llm = ChatAnthropic(
        model=model_name,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    # Create memory for conversation persistence
    memory = MemorySaver()

    # Create the ReAct agent with tools
    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
        checkpointer=memory,
        prompt=SYSTEM_PROMPT,
    )

    logger.info(f"Agent created with {len(TOOLS)} tools: {[t.name for t in TOOLS]}")
    return agent


def get_agent_response(agent, user_message: str, thread_id: str = "default") -> str:
    """Get a response from the agent for a user message.

    Args:
        agent: The LangGraph agent
        user_message: The user's input message
        thread_id: Conversation thread ID for memory

    Returns:
        The agent's response as a string
    """
    logger.info(f"Processing message (thread={thread_id}): {user_message[:100]}...")
    config = {"configurable": {"thread_id": thread_id}}

    # Invoke the agent
    result = agent.invoke(
        {"messages": [HumanMessage(content=user_message)]},
        config=config,
    )

    # Extract the last AI message
    messages = result.get("messages", [])
    logger.debug(f"Agent returned {len(messages)} message(s)")

    for message in reversed(messages):
        if isinstance(message, AIMessage):
            response = message.content
            logger.info(f"Response generated ({len(response)} chars)")
            return response

    logger.warning("No AI message found in response")
    return "I'm sorry, I couldn't generate a response. Please try again."


def stream_agent_response(agent, user_message: str, thread_id: str = "default") -> Generator[str, None, None]:
    """Stream a response from the agent for a user message.

    Args:
        agent: The LangGraph agent
        user_message: The user's input message
        thread_id: Conversation thread ID for memory

    Yields:
        Text chunks as they are generated (buffered to word boundaries)
    """
    logger.info(f"Streaming message (thread={thread_id}): {user_message[:100]}...")
    config = {"configurable": {"thread_id": thread_id}}

    # Buffer to accumulate text until word boundary
    buffer = ""

    def flush_buffer_to_word_boundary():
        """Yield complete words from buffer, keep partial word."""
        nonlocal buffer
        if not buffer:
            return None

        # Find last word boundary (space or newline)
        last_boundary = max(buffer.rfind(" "), buffer.rfind("\n"))

        if last_boundary == -1:
            # No boundary found, keep buffering
            return None

        # Yield up to and including the boundary
        to_yield = buffer[: last_boundary + 1]
        buffer = buffer[last_boundary + 1 :]
        return to_yield

    # Stream the agent response
    for chunk in agent.stream(
        {"messages": [HumanMessage(content=user_message)]},
        config=config,
        stream_mode="messages",
    ):
        # chunk is a tuple of (message, metadata)
        if isinstance(chunk, tuple) and len(chunk) >= 1:
            message = chunk[0]
            # Only yield content from AIMessage chunks
            if isinstance(message, AIMessage) and message.content:
                content = message.content
                # Handle both string and list content (Claude can return either)
                if isinstance(content, str):
                    buffer += content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            buffer += block.get("text", "")
                        elif isinstance(block, str):
                            buffer += block

                # Try to yield complete words
                result = flush_buffer_to_word_boundary()
                if result:
                    yield result

    # Yield any remaining content
    if buffer:
        yield buffer

    logger.info("Streaming complete")
