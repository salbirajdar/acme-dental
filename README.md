# Acme Dental AI Agent

An AI-powered receptionist for booking dental appointments through natural language conversation.

## Features

- Book Appointments - Check availability and create bookings via Calendly
- Reschedule/Cancel - Manage existing appointments by email lookup
- Answer Questions - FAQ knowledge base for clinic information
- Real-time Chat - React frontend with responsive UI

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed architectural decisions.

Stack:
- Frontend: React + TypeScript + Vite
- Backend: FastAPI + LangGraph + Claude Sonnet 4
- Scheduling: Calendly API with caching layer

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- uv package manager (https://github.com/astral-sh/uv)

### 1. Set up environment variables

Create `.env` in the `backend/` directory:

```
ANTHROPIC_API_KEY=your_key_here
CALENDLY_API_TOKEN=your_token_here
```

### 2. Start the backend

```
cd backend
uv sync
uv run uvicorn src.api:app --reload
```

Backend runs at http://localhost:8000

### 3. Start the frontend

```
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:5173

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| /chat | POST | Send a message, get AI response |
| /health | GET | Health check with cache stats |
| /availability | GET | Get available appointment slots |
| /bookings/search | POST | Search bookings by email |
| /webhooks/calendly | POST | Calendly webhook receiver |

## Agent Tools

The AI agent has access to these tools:

| Tool | Purpose |
|------|---------|
| check_availability | Show available appointment slots |
| get_booking_link | Generate booking URL for selected slot |
| find_booking | Look up appointments by email |
| cancel_booking | Cancel an existing appointment |
| get_reschedule_options | Show slots for rescheduling |
| answer_faq | Answer questions from knowledge base |

## Development

### Backend

```
cd backend
uv run ruff check .          # Lint
uv run ruff format .         # Format
uv run pytest                # Run tests
```

### Frontend

```
cd frontend
npm run lint                 # Lint
npm run build               # Production build
```

## Deployment

Configured for Railway deployment:

- Backend: Runs with 4 uvicorn workers
- Frontend: Set VITE_API_URL to backend URL

```
# Backend Procfile
web: uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WORKERS:-4}
```

## Project Structure

```
├── backend/
│   ├── src/
│   │   ├── api.py           # FastAPI endpoints
│   │   ├── agent.py         # LangGraph agent + tools
│   │   ├── calendly.py      # Calendly API client
│   │   ├── cache.py         # Scheduling cache
│   │   ├── knowledge_base.py # FAQ search
│   │   └── webhooks.py      # Webhook handlers
│   └── tests/
├── frontend/
│   └── src/
│       ├── App.tsx          # Main chat interface
│       ├── components/      # UI components
│       └── services/api.ts  # Backend API client
└── ARCHITECTURE.md          # Architectural decisions
```
