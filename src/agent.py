"""LangGraph AI Agent for the Acme Dental Clinic."""

import os
from typing import Annotated

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.calendly import get_calendly_client
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
2. Use check_availability to show available slots
3. Once they choose a time, collect their name and email
4. Use get_booking_link to provide them with a booking link for their selected slot
5. Confirm the booking details

Always be helpful and guide patients through the process step by step."""


@tool
def check_availability(
    days_ahead: Annotated[int, "Number of days ahead to check (1-14, default 7)"] = 7,
) -> str:
    """Check available appointment slots for dental check-ups.

    Use this tool when a patient wants to book an appointment or see available times.
    Returns a list of available time slots with dates and times.
    """
    logger.info(f"Tool: check_availability called (days_ahead={days_ahead})")
    try:
        client = get_calendly_client()
        slots = client.format_available_slots(max_slots=10)

        if not slots:
            logger.warning("No available slots found")
            return "No available slots found in the next 7 days. Please try again later."

        result = "Available appointment slots:\n\n"
        for i, slot in enumerate(slots, 1):
            result += f"{i}. {slot['date']} at {slot['time']}\n"

        result += "\nPlease let me know which slot works best for you!"
        logger.info(f"Returned {len(slots)} available slots")
        return result
    except Exception as e:
        logger.error(f"Error checking availability: {e}")
        return f"Sorry, I couldn't check availability right now. Error: {e}"


@tool
def get_booking_link(
    slot_number: Annotated[int, "The slot number the patient selected (1-10)"],
    patient_name: Annotated[str, "The patient's full name"],
    patient_email: Annotated[str, "The patient's email address"],
) -> str:
    """Get a booking link for a specific time slot.

    Use this tool after the patient has:
    1. Selected a time slot from the available options
    2. Provided their full name
    3. Provided their email address

    Returns a booking link the patient can use to complete their appointment.
    """
    logger.info(f"Tool: get_booking_link called (slot={slot_number}, name={patient_name}, email={patient_email})")
    try:
        client = get_calendly_client()
        slots = client.get_available_times()

        if slot_number < 1 or slot_number > len(slots):
            logger.warning(f"Invalid slot number: {slot_number}")
            return f"Invalid slot number. Please choose a number between 1 and {min(10, len(slots))}."

        selected_slot = slots[slot_number - 1]
        booking_url = client.get_booking_url_for_slot(selected_slot)
        logger.info(f"Generated booking link for slot {slot_number}")

        # Format the time for confirmation
        formatted = client.format_available_slots([selected_slot])[0]

        return f"""Booking details confirmed:
- Patient: {patient_name}
- Email: {patient_email}
- Date: {formatted["date"]}
- Time: {formatted["time"]}
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
        client = get_calendly_client()
        events = client.get_scheduled_events(email=patient_email)

        if not events:
            logger.info(f"No bookings found for {patient_email}")
            return (
                f"No upcoming appointments found for {patient_email}. "
                "Please check if this is the email you used when booking."
            )

        result = f"Found {len(events)} appointment(s) for {patient_email}:\n\n"
        for i, event in enumerate(events, 1):
            start_time = event.get("start_time", "Unknown")
            result += f"{i}. {event.get('name', 'Dental Check-up')} - {start_time}\n"
            result += f"   Status: {event.get('status', 'active')}\n"
            result += f"   Event ID: {event.get('uri', '').split('/')[-1]}\n\n"

        logger.info(f"Found {len(events)} booking(s) for {patient_email}")
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

        logger.info(f"Successfully cancelled event {event_id}")
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
        client = get_calendly_client()
        slots = client.format_available_slots(max_slots=10)

        if not slots:
            logger.warning("No slots available for rescheduling")
            return "No available slots found for rescheduling. Please try again later."

        result = f"Available slots for rescheduling (Event ID: {event_id}):\n\n"
        for i, slot in enumerate(slots, 1):
            result += f"{i}. {slot['date']} at {slot['time']}\n"

        result += "\nPlease tell me which slot you'd like to reschedule to."
        result += "\nNote: Rescheduling less than 24 hours before your appointment may incur a fee."
        logger.info(f"Returned {len(slots)} reschedule options")
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
