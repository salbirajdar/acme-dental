# Acme Dental AI Agent - Backend

FastAPI backend for the AI-powered dental receptionist.

## Endpoints

- `POST /chat` - Chat with the AI agent
- `GET /health` - Health check with cache stats
- `POST /webhooks/calendly` - Calendly webhook handler
- `GET /availability` - Get available appointment slots
- `POST /bookings/search` - Search bookings by email

## Setup

```bash
uv sync
cp .env.example .env  # Configure your environment variables
```

## Run

```bash
uvicorn src.api:app --reload
```

## Test

```bash
uv run pytest
```
