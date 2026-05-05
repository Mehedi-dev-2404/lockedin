# LockedIn

Telegram AI accountability agent for CS students grinding for SWE internships and placements.

**Bot:** [@lockedin_koda_bot](https://t.me/lockedin_koda_bot) | **Landing page:** [lockedin.vercel.app](https://lockedin.vercel.app)

---

## Overview

LockedIn is a production Telegram bot that acts as a daily accountability partner for computer science students. The AI agent — called Koda — tracks LeetCode streaks, application progress, and project momentum, then nudges users when they go quiet and pushes back when they make excuses.

The retention mechanism is behavioural, not motivational. Koda adjusts its tone based on how many days a user has been inactive, calls out vague updates, and only acknowledges progress when it is specific and verifiable. Generic motivational responses are explicitly excluded from the system prompt.

Monetisation is Stripe-powered. Users complete a free onboarding flow, receive a unique activation code, pay via Stripe Checkout, and the bot activates automatically on webhook confirmation.

---

## Architecture

```
                         User (Telegram)
                               |
                    python-telegram-bot
                    (polling, async)
                               |
                    +----------+----------+
                    |                     |
              ConversationHandler    MessageHandler
              (onboarding flow)     (active users)
                    |                     |
                    +----------+----------+
                               |
                         asyncio event loop
                               |
                    +----------+----------+
                    |                     |
             Koda response           Intent classifier
           (Claude API call)        (parallel Claude call)
                    |                     |
                    +----------+----------+
                               |
                          Supabase
                    (users, streaks, checkins,
                     applications, messages)
                               |
                    +----------+----------+
                    |                     |
            APScheduler              FastAPI + uvicorn
          (per-user nudge         (runs in same event loop)
             cron jobs)                   |
                                   POST /api/webhook
                                   (Stripe events)
                                          |
                                   Stripe Checkout
                                   (payment + activation)
```

The Telegram bot and FastAPI webhook server share a single asyncio event loop. `uvicorn.Server` runs as a coroutine inside the bot's async context manager, so there is no subprocess or threading boundary between them.

---

## Stack

| Component        | Technology                                       |
|------------------|--------------------------------------------------|
| Language         | Python 3.12                                      |
| Bot framework    | python-telegram-bot 21.5 (async)                 |
| AI               | Anthropic Claude API (claude-haiku-4-5-20251001) |
| Database         | Supabase (PostgreSQL) via supabase-py v2         |
| API server       | FastAPI + uvicorn                                |
| Scheduler        | APScheduler                                      |
| Payments         | Stripe Checkout + Webhooks                       |
| Bot hosting      | Railway (24/7)                                   |
| Landing page     | Vercel                                           |

---

## Key Engineering Decisions

### LLM-driven conversational onboarding

Onboarding does not use a state machine. Claude drives the entire conversation, asking about year of study, target companies, weak areas, and preferred nudge time in a natural flow. The handler passes the full conversation history on each turn.

When Claude has gathered all required fields, it outputs a sentinel marker `##ONBOARDING_COMPLETE##` followed by a JSON payload on the next line. The handler splits on the marker, sends the visible text to the user, parses the JSON, and writes the structured data to Supabase in a single `update_user` call.

A force-completion fallback triggers after 16 history entries. The handler injects a system instruction to output the marker immediately with whatever data has been collected, using `"not specified"` for missing fields. This prevents infinite onboarding loops.

### Parallel async architecture

The main entry point runs the bot poller and the uvicorn server concurrently in one asyncio event loop. Supabase calls (synchronous supabase-py) are offloaded to a thread pool via `asyncio.to_thread` to avoid blocking the loop. There is no multiprocessing or threading boundary for the two servers.

### Intent classification pipeline

Every message from an active user triggers two concurrent Claude API calls via `asyncio.gather`:

1. The main Koda response, with full conversation history and user context injected into the system prompt.
2. A lightweight intent classifier that returns structured JSON identifying whether the message mentions LeetCode activity, a job application (with company and role), or project work.

The classifier result silently updates streaks and check-ins in Supabase without any confirmation prompt to the user. Milestone events (first application submitted, N-day streak reached) surface as a follow-up message after Koda's response.

### Behavioural mode system

Before each Claude call, the handler computes a mode from days since last check-in and keywords in the current message:

| Mode        | Trigger condition                                    |
|-------------|------------------------------------------------------|
| HYPE        | User checked in today                                |
| FOCUS       | Default / neutral state                              |
| PRESSURE    | 1 missed day                                         |
| ENFORCEMENT | 2+ missed days                                       |
| RECOVERY    | Message contains keywords like "struggling", "cooked", "overwhelmed" |

The mode injects a corresponding instruction block into the system prompt, adjusting tone for that specific call. The mode is also persisted to the `users` table.

### Per-user nudge scheduling

At startup, `schedule_daily_nudges` reads all active users, extracts unique `nudge_time` values, and creates one APScheduler `run_daily` job per unique time slot. Each job checks which users match that nudge time and have not checked in today, generates a personalised nudge via Claude, and sends it.

Nudge tone escalates with `missed_days`: friendly on day 1, pressure on day 2, enforcement from day 3 onwards. `missed_days` increments on each unseen nudge and resets to zero when the user sends any message.

### Stripe activation via unique code

Each user is assigned a unique activation code at onboarding completion. When a Stripe `checkout.session.completed` event arrives, the webhook extracts the code from Stripe's `custom_fields`, looks up the corresponding user in Supabase, sets `is_premium = true`, and sends a confirmation message via the Telegram Bot API.

If the code is missing or unrecognised, an admin alert fires via Telegram with full session details for manual activation. Stripe webhook signature verification runs on every request before any event processing occurs.

### Conversation memory

The last 20 messages are fetched from the `messages` table and passed as the messages array on every Claude call. The table stores a `message_type` column distinguishing `conversation` from `onboarding` messages. Standard conversations only fetch `conversation`-typed messages, keeping onboarding history isolated.

### Streak tracking

Streak updates use idempotent upserts keyed on `(user_id, date)`. If a streak update is called twice on the same day, the second call is a no-op. Consecutive day detection compares `last_<activity>_date` against today and yesterday. The longest streak record updates in the same transaction if the current streak exceeds it.

---

## Project Structure

```
lockedin/
├── api/
│   ├── main.py                   # FastAPI app, mounts router
│   └── routes/
│       └── webhook.py            # POST /api/webhook (Stripe)
├── bot/
│   ├── handlers/
│   │   ├── command_handler.py    # /streak, /profile, /help, /support
│   │   ├── checkin_handler.py    # /checkin command
│   │   ├── message_handler.py    # Freeform message handling, intent pipeline
│   │   └── onboarding_handler.py # ConversationHandler, LLM-driven onboarding
│   ├── koda/
│   │   ├── anthropic_client.py   # Anthropic client singleton
│   │   ├── claude_client.py      # get_koda_response, classify_intent, generate_nudge
│   │   ├── memory.py             # Message history helpers
│   │   ├── personality.py        # System prompt builder, mode blocks, context injection
│   │   └── utils.py              # Shared helpers (build_user_context, is_vague_input)
│   └── scheduler/
│       └── daily_checkin.py      # APScheduler setup, per-user nudge job factory
├── config/
│   ├── constants.py
│   └── settings.py               # Env var loading
├── db/
│   ├── models/
│   │   ├── checkin.py
│   │   ├── streak.py
│   │   └── user.py
│   └── queries/
│       ├── application_queries.py
│       ├── checkin_queries.py
│       ├── message_queries.py
│       ├── streak_queries.py
│       └── user_queries.py
├── tests/
│   ├── test_db.py
│   ├── test_handlers.py
│   └── test_koda.py
├── web/
│   ├── index.html
│   ├── stripe_checkout.js
│   └── styles.css
├── main.py                       # Entry point, event loop setup
├── requirements.txt
├── railway.toml
└── .env.example
```

---

## Local Development

### Prerequisites

- Python 3.12
- A Supabase project with the schema below applied
- Anthropic API key
- Stripe account with a Checkout product and webhook endpoint configured
- A Telegram bot token from BotFather

### Setup

```bash
git clone https://github.com/mehedimostafa/lockedin.git
cd lockedin
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in .env with your credentials
python main.py
```

The bot starts polling and the FastAPI server listens on port 8000 (overridden by the `PORT` env var, which Railway sets automatically).

For local Stripe webhook testing, use the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/api/webhook
```

---

## Environment Variables

| Variable                | Description                                                  |
|-------------------------|--------------------------------------------------------------|
| `TELEGRAM_BOT_TOKEN`    | Bot token from BotFather                                     |
| `ANTHROPIC_API_KEY`     | Anthropic API key                                            |
| `SUPABASE_URL`          | Supabase project URL                                         |
| `SUPABASE_KEY`          | Supabase service role key                                    |
| `STRIPE_SECRET_KEY`     | Stripe secret key                                            |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret                                |
| `ADMIN_TELEGRAM_ID`     | Telegram ID to receive alerts on payment activation failures |
| `ENVIRONMENT`           | `development` or `production`                                |
| `PORT`                  | HTTP port for uvicorn (default: 8000, set by Railway)        |

---

## Database Schema

**users**

| Column               | Type       | Notes                                               |
|----------------------|------------|-----------------------------------------------------|
| telegram_id          | BIGINT PK  | Primary identifier throughout                       |
| username             | TEXT       |                                                     |
| full_name            | TEXT       | Set during onboarding                               |
| year_of_study        | TEXT       |                                                     |
| university           | TEXT       |                                                     |
| target_companies     | TEXT[]     |                                                     |
| weak_areas           | TEXT[]     |                                                     |
| goals                | TEXT       |                                                     |
| nudge_time           | TEXT       | HH:MM 24-hour, Europe/London                        |
| is_active            | BOOLEAN    |                                                     |
| is_premium           | BOOLEAN    | Set to true on Stripe webhook activation            |
| is_international     | BOOLEAN    |                                                     |
| experience_level     | TEXT       |                                                     |
| tech_stack           | TEXT       |                                                     |
| payment_code         | TEXT       | Unique activation code for Stripe checkout          |
| missed_days          | INT        | Increments per unseen nudge, resets on any message  |
| mode                 | TEXT       | HYPE / FOCUS / PRESSURE / ENFORCEMENT / RECOVERY    |
| total_message_count  | INT        | Used for free tier message limit enforcement        |
| onboarding_complete  | BOOLEAN    |                                                     |
| last_active_date     | DATE       |                                                     |

**streaks**

| Column                | Type       | Notes                              |
|-----------------------|------------|------------------------------------|
| user_id               | BIGINT FK  |                                    |
| leetcode_streak       | INT        | Current consecutive days           |
| applications_streak   | INT        |                                    |
| project_streak        | INT        |                                    |
| last_leetcode_date    | DATE       | Used for same-day idempotency      |
| last_application_date | DATE       |                                    |
| last_project_date     | DATE       |                                    |
| longest_leetcode      | INT        |                                    |
| longest_applications  | INT        |                                    |
| longest_project       | INT        |                                    |

**checkins**

| Column            | Type      | Notes                               |
|-------------------|-----------|-------------------------------------|
| user_id           | BIGINT FK |                                     |
| date              | DATE      | Unique per user per day (upsert)    |
| leetcode_done     | BOOLEAN   |                                     |
| applications_sent | INT       |                                     |
| project_worked    | BOOLEAN   |                                     |
| notes             | TEXT      |                                     |
| mood              | INT       | 1-5                                 |

**applications**

| Column     | Type      | Notes                                                 |
|------------|-----------|-------------------------------------------------------|
| user_id    | BIGINT FK |                                                       |
| company    | TEXT      |                                                       |
| role       | TEXT      |                                                       |
| status     | TEXT      | applied / oa / interview / offer / rejected           |
| applied_at | DATE      |                                                       |
| notes      | TEXT      |                                                       |

**messages**

| Column       | Type      | Notes                                    |
|--------------|-----------|------------------------------------------|
| user_id      | BIGINT FK |                                          |
| role         | TEXT      | user / assistant                         |
| content      | TEXT      |                                          |
| message_type | TEXT      | conversation / onboarding                |

---

## API Endpoints

| Method | Path           | Description                                                                                                     |
|--------|----------------|-----------------------------------------------------------------------------------------------------------------|
| GET    | `/health`      | Returns `{"status": "ok"}`. Used by Railway for uptime checks.                                                  |
| POST   | `/api/webhook` | Receives Stripe events. Verifies signature, handles `checkout.session.completed`, activates user via Supabase. |

---

## Bot Commands

| Command            | Description                                                  |
|--------------------|--------------------------------------------------------------|
| `/start`           | Register and begin onboarding, or welcome back existing user |
| `/checkin`         | Manually trigger a check-in prompt                           |
| `/streak`          | Show current streak counts                                   |
| `/profile`         | Show stored profile and goals                                |
| `/help`            | List available commands                                      |
| `/support`         | Contact and support information                              |
| `/resetonboarding` | Reset onboarding state (admin use)                           |

---

## Deployment

### Railway (bot + API)

The bot and FastAPI server run as a single Railway service. `main.py` is the entry point. Set all environment variables in the Railway dashboard. Railway injects `PORT` automatically.

```toml
# railway.toml
[deploy]
startCommand = "python main.py"
```

### Vercel (landing page)

The `web/` directory contains a static landing page deployed to Vercel. The Stripe Checkout link and activation code instructions are embedded in the HTML.

### Stripe webhook

Register the webhook endpoint in the Stripe dashboard:

```
https://<your-railway-domain>/api/webhook
```

Select the `checkout.session.completed` event. Copy the signing secret into the `STRIPE_WEBHOOK_SECRET` environment variable on Railway.

---

## License

MIT
