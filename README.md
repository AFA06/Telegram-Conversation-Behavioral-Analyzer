# Telegram Conversation Behavioral Analyzer

A local-first application that analyzes a Telegram conversation export between
two people: when each person tends to message, how quickly the other person
has historically responded, recurring activity windows, conversation
sessions, and how communication patterns have changed over time.

**Everything runs on your machine.** No message content is ever sent to
OpenAI, Anthropic, Google, or any other external service. See
[Privacy](#privacy) below.

## What this is (and isn't)

This tool reports **observed communication patterns** — message timing,
response delays, activity windows. It deliberately avoids claiming to know
whether someone is free, interested, or intentionally not replying. You'll
see language like *"historically active"*, *"historically responsive"*, and
*"longest observed response delay"* throughout — never *"she was ignoring
you"* or *"she is free at this time"*. The system cannot know intent, and
doesn't pretend to.

## Architecture

```
Telegram Export (JSON)
      ↓
Python Importer (backend/app/services/telegram_parser.py)
      ↓
Normalized SQLite Database
      ↓
Analysis Engine (activity / response-time / session analyzers)
      ↓
FastAPI REST API
      ↓
React + Vite Dashboard
      ↓
Optional Telegram Bot (reads only computed statistics)
```

## Project structure

```
telegram chat analizer/
├── backend/
│   ├── app/
│   │   ├── main.py          FastAPI app
│   │   ├── config.py        Settings (env-driven, all local)
│   │   ├── database.py      SQLAlchemy engine/session
│   │   ├── models.py        ORM models
│   │   ├── schemas.py       Pydantic request models
│   │   ├── routes/          One module per API area
│   │   ├── services/        Parsing + analysis logic (pure, unit-tested)
│   │   └── utils/           Time & formatting helpers
│   ├── analyzer/            `python -m analyzer ...` CLI
│   ├── bot/                 Optional Telegram bot (Phase 7)
│   └── tests/                Pytest suite (synthetic data only)
├── frontend/                 React + Vite dashboard
├── data/                     Your imported export & SQLite DB (gitignored)
└── scripts/
```

> Note on the spec's suggested filenames: `routes/import.py` isn't valid
> Python (`import` is a reserved keyword), so that route lives in
> `routes/imports.py` instead. Functionally identical.

## Privacy

- Your Telegram export and the SQLite database live under `data/`, which is
  gitignored and never leaves your machine.
- No analytics, no telemetry, no cloud database, no automatic upload.
- The `/ask` bot command answers questions with **keyword matching against
  already-computed statistics** — not an LLM call, and never sees the raw
  conversation. If you later want to send an external LLM anything, it
  should only ever be the aggregated numbers, and only if you explicitly
  wire that up yourself.
- The public GitHub repo never contains anyone's Telegram user ID, name, or
  message content. You configure your own participants locally (Settings
  page or CLI), and that configuration stays in your local database.

## Requirements

- Python 3.11+
- Node.js 18+
- A Telegram Desktop export (Settings → Advanced → Export chat history → JSON)

## Setup

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # optional, defaults already work
```

Run the API:

```bash
python -m analyzer server --reload
```

The API is now at `http://127.0.0.1:8000` (docs at `/docs`).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The dev server proxies `/api` to the backend.

### 3. Import your conversation

Either through the **Settings** page in the dashboard (recommended — lets
you pick participants visually), or via the CLI:

```bash
cd backend
source .venv/bin/activate
python -m analyzer import /path/to/result.json \
  --me-id YOUR_TELEGRAM_USER_ID --me-name "Me" \
  --other-id THEIR_TELEGRAM_USER_ID --other-name "Their name" \
  --timezone Asia/Tashkent
python -m analyzer analyze
python -m analyzer stats
```

Re-run `python -m analyzer analyze` (or the "Re-run analysis" button in
Settings) any time you change participants, timezone, the message-burst
grouping window, or the session-gap threshold.

### 4. Optional: Telegram bot

```bash
cd backend
source .venv/bin/activate
pip install -r bot/requirements.txt
echo "TELEGRAM_BOT_TOKEN=<token from @BotFather>" >> .env
python -m bot.main
```

The bot only talks to your local backend's REST API (`BOT_BACKEND_URL`,
default `http://127.0.0.1:8000`) — it never touches the database or the
export file directly. Commands: `/overview`, `/activity`, `/response`,
`/fastest`, `/slowest`, `/longest`, `/sessions`, `/windows`, `/trends`,
`/ask <question>`.

## CLI reference

```bash
python -m analyzer import <file.json> [--me-id ID --me-name NAME --other-id ID --other-name NAME --timezone TZ]
python -m analyzer configure [--grouping-window N --session-gap N --min-sample N ...]
python -m analyzer analyze
python -m analyzer stats
python -m analyzer server [--host --port --reload]
```

## Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

The suite covers Telegram JSON parsing (including nested rich-text
entities), timezone conversion, message-burst grouping, response-time
calculation, session detection, weekday/hourly statistics, insufficient
sample-size handling, and a full API integration pass — all against
synthetic fixtures, never real conversation data.

```bash
cd frontend
npx eslint src
npm run build
```

## Methodology notes

- **Message-burst grouping**: consecutive messages from the same person
  within a configurable window (default 5 minutes) count as one "burst"
  before response time is computed, so a 3-message stream followed by one
  reply is one response event, not three.
- **Sessions**: a new conversation session starts after a configurable
  inactivity gap (default 6 hours).
- **Confidence labels**: any ranked window (best response time, most active
  slot, etc.) is gated by a minimum sample size (default 10 observations).
  Below that, the UI shows "Insufficient data" rather than a misleadingly
  precise number.
- **"Historically Responsive Windows"** combines message volume and
  response speed into one ranking, always framed as a historical pattern,
  never as a guarantee of availability.

## Development phases

1. Telegram parser + database
2. Activity analysis (hour/weekday/heatmap/top windows)
3. Response-time analysis (bursts, percentiles, distribution, no-response)
4. Conversation sessions
5. FastAPI
6. React + Vite dashboard
7. Telegram bot
8. Tests + polish

All phases are implemented and tested.
