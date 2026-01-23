"""Knowledge base for Acme Dental FAQs."""

from pathlib import Path

# FAQ content extracted from KNOWLEDGE_BASE.md
FAQ_DATA = {
    "services": {
        "keywords": ["service", "offer", "provide", "do you do", "what do you"],
        "answer": (
            "Acme Dental currently offers routine dental check-ups only. "
            "A check-up includes an oral examination and general assessment of your dental health."
        ),
    },
    "duration": {
        "keywords": ["how long", "duration", "minutes", "time", "length"],
        "answer": "Each dental check-up appointment is 30 minutes.",
    },
    "dentist": {
        "keywords": ["dentist", "doctor", "who", "staff", "specific dentist"],
        "answer": (
            "Acme Dental has one dentist, and all check-ups are completed by that dentist. "
            "Every booking is automatically scheduled with them."
        ),
    },
    "emergency": {
        "keywords": ["emergency", "urgent", "pain", "swelling", "bleeding"],
        "answer": (
            "Acme Dental is focused on routine check-ups only and does not offer emergency "
            "dental treatment. If you have severe pain, swelling, or bleeding, please contact "
            "emergency dental services in your area."
        ),
    },
    "booking_process": {
        "keywords": ["how to book", "book appointment", "make appointment", "schedule"],
        "answer": (
            "You can book directly through this chat assistant. I will show available times, "
            "help you choose a slot, ask for your name and email, and confirm your booking instantly."
        ),
    },
    "account": {
        "keywords": ["account", "sign up", "register", "login"],
        "answer": ("No account is required. We only need your full name and email address to book an appointment."),
    },
    "walk_in": {
        "keywords": ["walk-in", "walkin", "walk in", "without appointment", "drop in"],
        "answer": "At the moment, we do not accept walk-ins. All visits must be booked in advance.",
    },
    "reschedule": {
        "keywords": ["reschedule", "change time", "move appointment", "different time"],
        "answer": (
            "Yes, you can reschedule anytime. Just tell me 'I need to reschedule my check-up' "
            "and I'll find your booking and offer new available time slots."
        ),
    },
    "cancel": {
        "keywords": ["cancel", "cancellation"],
        "answer": (
            "You can cancel by telling me 'Cancel my appointment'. Once confirmed, "
            "I'll process the cancellation and send you a confirmation."
        ),
    },
    "confirmation": {
        "keywords": ["confirmation", "confirm", "email confirmation", "receipt"],
        "answer": (
            "Yes, after booking you'll receive a confirmation with the date, time, "
            "and appointment duration (30 minutes)."
        ),
    },
    "no_confirmation": {
        "keywords": ["didn't receive", "no email", "missing confirmation", "didn't get"],
        "answer": (
            "First, check your spam/junk folder. If you still don't see it, tell me "
            "'I didn't get my confirmation email' and I'll help verify your booking details."
        ),
    },
    "book_for_others": {
        "keywords": ["someone else", "book for", "on behalf", "another person", "family"],
        "answer": (
            "Yes, you can book on behalf of someone else. Just provide their full name and email address when asked."
        ),
    },
    "what_to_bring": {
        "keywords": ["bring", "need to bring", "prepare", "documents"],
        "answer": (
            "Please bring: a valid photo ID, any relevant medical information (if applicable), "
            "and your insurance details (if you have them)."
        ),
    },
    "arrival_time": {
        "keywords": ["arrive", "early", "when should i", "how early"],
        "answer": "We recommend arriving 5-10 minutes early so you have time to settle in.",
    },
    "late": {
        "keywords": ["late", "running late", "delayed"],
        "answer": (
            "If you're running late, please message us as soon as possible. We'll do our best "
            "to accommodate you, but the appointment may need to be rescheduled if we can't "
            "complete the check-up within the 30-minute slot."
        ),
    },
    "privacy": {
        "keywords": ["privacy", "data", "personal information", "secure", "security"],
        "answer": (
            "We only collect the minimum details needed to manage your appointment "
            "(name and email) and use them solely for scheduling and confirmations."
        ),
    },
    "price": {
        "keywords": ["price", "cost", "how much", "fee", "charge", "€", "euro"],
        "answer": (
            "A standard dental check-up at Acme Dental costs €60. This includes a full oral "
            "examination, gum health check, a review of any concerns you mention, "
            "and basic recommendations for next steps."
        ),
    },
    "included": {
        "keywords": ["include", "what's included", "covered", "part of"],
        "answer": (
            "The €60 check-up includes: a full oral examination, gum health check, "
            "a review of any concerns you mention, and basic recommendations for next steps "
            "(if needed). X-rays are NOT included."
        ),
    },
    "xray": {
        "keywords": ["x-ray", "xray", "x ray", "radiograph"],
        "answer": (
            "No, Acme Dental check-ups do not include X-rays. If X-rays are required, "
            "the dentist will explain next steps and options."
        ),
    },
    "discounts": {
        "keywords": ["discount", "student", "senior", "reduced", "cheaper"],
        "answer": (
            "Yes, we offer: Student discount: €50 check-up (valid student ID required), "
            "and Senior discount (65+): €50 check-up. Discounts cannot be combined."
        ),
    },
    "payment": {
        "keywords": ["pay", "payment", "card", "cash", "contactless"],
        "answer": "You can pay in-clinic by card, contactless payment, or cash (exact amount preferred).",
    },
    "deposit": {
        "keywords": ["deposit", "upfront", "advance payment"],
        "answer": (
            "No deposit is required for routine check-ups. You only need your name and email to confirm the booking."
        ),
    },
    "cancellation_policy": {
        "keywords": ["cancellation policy", "cancel fee", "cancellation fee", "24 hours"],
        "answer": (
            "You can cancel or reschedule free of charge up to 24 hours before your appointment. "
            "Cancellations made less than 24 hours in advance may incur a €20 late cancellation fee."
        ),
    },
    "no_show": {
        "keywords": ["miss", "no-show", "no show", "didn't attend", "forgot"],
        "answer": (
            "If you don't attend without notice (no-show), a €20 no-show fee may apply. "
            "You can still rebook through the assistant afterwards."
        ),
    },
    "insurance": {
        "keywords": ["insurance", "claim", "coverage", "insurer"],
        "answer": (
            "Acme Dental can provide a receipt for your visit, which you may be able to claim "
            "through your insurance provider. We do not process insurance claims directly."
        ),
    },
    "invoice": {
        "keywords": ["invoice", "receipt", "proof"],
        "answer": (
            "Yes, we provide receipts for all appointments. If you need an invoice with "
            "specific details, please ask at reception during your visit."
        ),
    },
    "location": {
        "keywords": ["where", "location", "address", "find you"],
        "answer": (
            "Acme Dental is located at Acme Dental Lane. The exact address will be in your booking confirmation."
        ),
    },
}


def search_knowledge_base(query: str) -> str | None:
    """Search the knowledge base for an answer to the query.

    Args:
        query: The user's question

    Returns:
        The answer if found, None otherwise
    """
    query_lower = query.lower()

    # Score each FAQ entry based on keyword matches
    best_match = None
    best_score = 0

    for _topic, data in FAQ_DATA.items():
        score = sum(1 for keyword in data["keywords"] if keyword in query_lower)
        if score > best_score:
            best_score = score
            best_match = data["answer"]

    return best_match if best_score > 0 else None


def get_full_knowledge_base() -> str:
    """Get the full knowledge base as a formatted string.

    Returns:
        Formatted string containing all FAQ information
    """
    kb_path = Path(__file__).parent.parent / "KNOWLEDGE_BASE.md"
    if kb_path.exists():
        return kb_path.read_text()

    # Fallback to compiled FAQ data
    sections = []
    for topic, data in FAQ_DATA.items():
        sections.append(f"**{topic.replace('_', ' ').title()}**: {data['answer']}")
    return "\n\n".join(sections)


def get_clinic_info() -> dict:
    """Get basic clinic information.

    Returns:
        Dictionary with clinic details
    """
    return {
        "name": "Acme Dental",
        "service": "Dental Check-up",
        "duration": "30 minutes",
        "price": "€60",
        "student_price": "€50",
        "senior_price": "€50",
        "location": "Acme Dental Lane",
        "cancellation_notice": "24 hours",
        "late_cancel_fee": "€20",
        "no_show_fee": "€20",
    }
