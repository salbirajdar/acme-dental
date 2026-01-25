"""FastAPI backend for Acme Dental AI Agent."""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sse_starlette.sse import EventSourceResponse

from src.agent import create_acme_dental_agent, get_agent_response, stream_agent_response
from src.cache import get_scheduling_cache, start_cache, stop_cache
from src.logging_config import get_logger, setup_logging
from src.webhooks import handle_webhook_event, handle_webhook_ping, verify_webhook_signature

# Request timeout for LLM calls (seconds)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

# Load environment variables
load_dotenv()

# Set up logging
setup_logging()
logger = get_logger("api")

# Global agent instance (created on startup)
_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    global _agent

    logger.info("Starting Acme Dental API...")

    # Start the scheduling cache with background sync
    logger.info("Starting scheduling cache...")
    start_cache()

    # Create the agent
    logger.info("Initializing AI agent...")
    _agent = create_acme_dental_agent()

    logger.info("Acme Dental API ready!")

    yield

    # Shutdown
    logger.info("Shutting down Acme Dental API...")
    stop_cache()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Acme Dental AI Agent",
    description="AI-powered receptionist for dental appointment booking",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    thread_id: str = Field(
        default="default",
        description="Conversation thread ID for maintaining context",
    )


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    response: str = Field(..., description="Agent's response")
    thread_id: str = Field(..., description="Conversation thread ID")


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    cache_stats: dict[str, Any] | None = None


class WebhookResponse(BaseModel):
    """Response model for webhook endpoint."""

    status: str
    message: str
    action: str | None = None


# API Endpoints
@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Acme Dental AI Agent",
        "version": "1.0.0",
        "endpoints": {
            "chat": "POST /chat",
            "health": "GET /health",
            "webhook": "POST /webhooks/calendly",
        },
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with cache statistics."""
    cache = get_scheduling_cache()
    stats = cache.get_stats()

    return HealthResponse(
        status="healthy",
        cache_stats=stats,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat with the AI dental receptionist.

    Send a message and receive a response from the AI agent.
    Use the same thread_id across messages to maintain conversation context.
    """
    global _agent

    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    logger.info(f"Chat request (thread={request.thread_id}): {request.message[:50]}...")

    try:
        # Run blocking LLM call in thread pool with timeout
        response = await asyncio.wait_for(
            asyncio.to_thread(get_agent_response, _agent, request.message, request.thread_id),
            timeout=REQUEST_TIMEOUT,
        )

        logger.info(f"Chat response generated ({len(response)} chars)")
        return ChatResponse(
            response=response,
            thread_id=request.thread_id,
        )
    except TimeoutError:
        logger.error(f"Chat request timed out after {REQUEST_TIMEOUT}s")
        raise HTTPException(
            status_code=504,
            detail=f"Request timed out after {REQUEST_TIMEOUT} seconds. Please try again.",
        ) from None
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}") from e


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream a chat response from the AI dental receptionist.

    Returns Server-Sent Events (SSE) with response chunks as they are generated.
    Use the same thread_id across messages to maintain conversation context.
    """
    global _agent

    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    logger.info(f"Stream chat request (thread={request.thread_id}): {request.message[:50]}...")

    async def event_generator():
        """Generate SSE events from the agent stream."""
        queue: asyncio.Queue = asyncio.Queue()

        def stream_to_queue():
            """Run the sync generator and push chunks to the queue."""
            try:
                for chunk in stream_agent_response(_agent, request.message, request.thread_id):
                    if chunk:
                        queue.put_nowait(chunk)
                queue.put_nowait(None)  # Signal completion
            except Exception as e:
                queue.put_nowait(e)  # Signal error

        # Start streaming in background thread
        stream_task = asyncio.get_event_loop().run_in_executor(None, stream_to_queue)

        try:
            while True:
                # Wait for chunks with a small timeout to allow checking task status
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue

                if chunk is None:
                    # Streaming complete
                    yield {"event": "done", "data": ""}
                    logger.info("Stream completed successfully")
                    break
                elif isinstance(chunk, Exception):
                    # Error occurred
                    logger.error(f"Error in stream: {chunk}")
                    yield {"event": "error", "data": str(chunk)}
                    break
                else:
                    yield {"event": "message", "data": chunk}
                    # Small delay for natural reading pace (~30 words/sec)
                    await asyncio.sleep(0.20)

            await stream_task
        except Exception as e:
            logger.error(f"Error in stream: {e}")
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@app.post("/webhooks/calendly", response_model=WebhookResponse)
async def calendly_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    calendly_webhook_signature: str | None = Header(None, alias="Calendly-Webhook-Signature"),
):
    """Handle Calendly webhook events.

    This endpoint receives webhook events from Calendly when:
    - A new appointment is booked (invitee.created)
    - An appointment is cancelled (invitee.canceled)

    The webhook invalidates the cache to ensure fresh data.
    """
    # Get raw body for signature verification
    body = await request.body()

    # Get signing key from environment
    signing_key = os.getenv("CALENDLY_WEBHOOK_SIGNING_KEY")

    # Verify signature if signing key is configured
    if signing_key:
        if not calendly_webhook_signature:
            logger.warning("Webhook received without signature")
            raise HTTPException(status_code=401, detail="Missing webhook signature")

        if not verify_webhook_signature(body, calendly_webhook_signature, signing_key):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

    # Check for ping/test event
    if payload.get("event") == "ping" or not payload.get("event"):
        return WebhookResponse(**handle_webhook_ping())

    # Process the webhook event
    logger.info(f"Processing webhook event: {payload.get('event')}")
    result = handle_webhook_event(payload)

    return WebhookResponse(**result)


# Additional utility endpoints
class AvailabilityResponse(BaseModel):
    """Response model for availability endpoint."""

    slots: list[dict[str, str]]
    cached: bool
    cache_age_seconds: float | None


@app.get("/availability", response_model=AvailabilityResponse)
async def get_availability(time_preference: str = "all"):
    """Get available appointment slots.

    This endpoint returns cached availability data.
    Use time_preference to filter: 'morning', 'afternoon', or 'all'.
    """
    cache = get_scheduling_cache()

    # Check if we have cached data
    cached = cache._availability_cache is not None and not cache._availability_cache.is_expired()
    cache_age = cache._availability_cache.age_seconds() if cache._availability_cache else None

    slots = cache.get_availability(time_preference=time_preference)

    return AvailabilityResponse(
        slots=slots,
        cached=cached,
        cache_age_seconds=cache_age,
    )


class BookingSearchRequest(BaseModel):
    """Request model for booking search."""

    email: EmailStr = Field(..., description="Patient's email address")


class BookingSearchResponse(BaseModel):
    """Response model for booking search."""

    email: str
    bookings: list[dict[str, Any]]
    count: int


@app.post("/bookings/search", response_model=BookingSearchResponse)
async def search_bookings(request: BookingSearchRequest):
    """Search for bookings by email.

    Returns all upcoming appointments for the given email address.
    """
    cache = get_scheduling_cache()
    bookings = cache.get_bookings(request.email)

    return BookingSearchResponse(
        email=request.email,
        bookings=bookings,
        count=len(bookings),
    )


# Run with: uvicorn src.api:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
