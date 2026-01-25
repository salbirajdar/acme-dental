Architectural Decisions

1. LangGraph ReAct Agent

Using LangGraph's `create_react_agent` for the AI brain. It follows a "think, act, observe" loop - the agent decides what to do, calls a tool, looks at the result, and repeats until done. This handles multi-step tasks like booking appointments naturally. Conversation memory is built-in via `MemorySaver`.

2. Claude Sonnet 4

Claude Sonnet powers the agent. It's fast enough for real-time chat and smart enough to handle booking conversations without getting confused.

3. Tool-Based Design

The agent has six tools, each doing one specific job:
- `check_availability` - shows open appointment slots
- `get_booking_link` - creates a booking URL for a specific slot
- `find_booking` - looks up a patient's existing appointments
- `cancel_booking` - cancels an appointment
- `get_reschedule_options` - shows available slots for rescheduling
- `answer_faq` - answers common questions from the knowledge base

4. Async Request Handling

LLM calls can take 2-5 seconds. Without async, one slow request blocks everyone else. We wrap the blocking LLM call in `asyncio.to_thread()` so other requests can be processed while waiting.

A 30-second timeout prevents requests from hanging forever if something goes wrong.

5. Multiple Workers

Running 4 uvicorn workers means 4 requests can be processed in true parallel (not just async). Each worker handles its own requests independently. This scales linearly with CPU cores.

6. HTTP Connection Pooling

The Calendly client keeps connections open and reuses them instead of creating a new connection for every API call. This saves the overhead of TCP handshakes and TLS negotiation. Set to 10 keep-alive connections with a max of 20.

7. In-Memory Cache with Background Sync

A caching layer sits between the agent and Calendly API. A background thread refreshes data every 2 minutes. Cache hits return in ~10ms vs 200-500ms for direct API calls.

Trade-off: Data can be up to 2 minutes stale. Fine for a small clinic with low booking volume.

8. Webhook-Based Cache Invalidation

Calendly sends webhooks when appointments are booked or cancelled. These trigger immediate cache invalidation so availability stays accurate.

9. Keyword-Based FAQ Search

Simple keyword matching for the knowledge base. With ~20 FAQ entries, this works fine without needing a vector database or embeddings.

10. Retry Logic for External APIs

Calendly API calls automatically retry up to 3 times with exponential backoff (1s, 2s, 4s delays). Handles transient network issues without bothering users.

11. Separate Frontend/Backend

Two independent services:
- Backend: FastAPI (Python) - AI agent, Calendly integration, webhooks
- Frontend: React/Vite (TypeScript) - chat interface

They connect via `VITE_API_URL`. Can be deployed and scaled independently.

12. Thread-Based Conversations

Each browser session gets a unique `thread_id`. The agent remembers the conversation history for that thread, so users can have natural back-and-forth conversations.
