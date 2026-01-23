"""Main entry point for the Acme Dental AI Agent."""

import uuid

from dotenv import load_dotenv

from src.agent import create_acme_dental_agent, get_agent_response
from src.logging_config import get_logger, setup_logging


def main():
    """Run the Acme Dental AI Agent in CLI mode."""
    load_dotenv()

    # Set up logging (use LOG_LEVEL env var, default to INFO)
    setup_logging()
    logger = get_logger("main")
    logger.info("Starting Acme Dental AI Agent")

    print("\n" + "=" * 60)
    print("Welcome to Acme Dental Clinic!")
    print("=" * 60)
    print("\nI'm your AI assistant. I can help you with:")
    print("  • Booking a dental check-up appointment")
    print("  • Rescheduling or cancelling existing appointments")
    print("  • Answering questions about our services")
    print("\nType 'exit', 'quit', or 'q' to end the session.")
    print("-" * 60 + "\n")

    # Create the agent
    logger.info("Initializing agent...")
    agent = create_acme_dental_agent()

    # Generate a unique thread ID for this conversation
    thread_id = str(uuid.uuid4())
    logger.info(f"Session started with thread_id: {thread_id}")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                logger.info("User ended session")
                print("\nThank you for visiting Acme Dental. Goodbye!")
                break

            # Get response from the agent
            response = get_agent_response(agent, user_input, thread_id)
            print(f"\nAgent: {response}\n")

        except KeyboardInterrupt:
            print("\n\nSession interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
