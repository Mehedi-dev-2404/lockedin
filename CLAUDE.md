# CLAUDE.md — Koda

> AI accountability agent for CS students grinding for internships and placements.
> Lives on Telegram. Tracks streaks, applications, and project momentum.
> Roasts you when you go quiet. Built by Mehedi.

---

## Project Overview

**Koda** is a personality-driven AI accountability agent deployed as a Telegram bot.
It checks in daily, tracks LeetCode streaks and placement application progress, and
motivates users through direct, humour-led feedback — not generic encouragement.

The core retention mechanic is personality: Koda behaves like a senior dev who
genuinely wants you to succeed but won't accept excuses or silence.

Monetisation is Stripe-powered: users pay via a landing page, and bot access
activates on payment confirmation via webhook.

---

## Stack

| Layer           | Technology                                       |
|-----------------|--------------------------------------------------|
| Bot             | Python, python-telegram-bot                      |
| AI Brain        | Anthropic Claude API (claude-haiku-4-5-20251001) |
| Backend         | FastAPI                                          |
| Database        | Supabase (PostgreSQL)                            |
| Auth            | Supabase Auth (web dashboard layer)              |
| Payments        | Stripe (Checkout + Webhooks)                     |
| Hosting         | Railway                                          |
| Frontend        | Landing page (HTML/CSS)                          |
| Version Control | GitHub                                           |

---

## Repo Structure

```
lockedin/
├── bot/
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── message_handler.py
│   │   ├── command_handler.py
│   │   └── onboarding_handler.py
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── daily_checkin.py
│   └── koda/
│       ├── __init__.py
│       ├── personality.py
│       ├── memory.py
│       └── claude_client.py
├── db/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── streak.py
│   │   └── checkin.py
│   └── queries/
│       ├── __init__.py
│       ├── user_queries.py
│       ├── streak_queries.py
│       └── checkin_queries.py
├── web/
│   ├── index.html
│   ├── styles.css
│   └── stripe_checkout.js
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── constants.py
├── tests/
│   ├── __init__.py
│   ├── test_handlers.py
│   ├── test_koda.py
│   └── test_db.py
├── .env.example
├── .gitignore
├── requirements.txt
├── railway.toml
├── CLAUDE.md
└── main.py
```

---

## Database Schema (Supabase)

```sql
-- Users table
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    full_name TEXT,
    year_of_study INT,
    university TEXT,
    target_companies TEXT[],
    weak_areas TEXT[],
    goals TEXT,
    preferred_checkin_time TEXT DEFAULT '09:00',
    is_active BOOLEAN DEFAULT TRUE,
    is_premium BOOLEAN DEFAULT FALSE,
    stripe_customer_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Streaks table
CREATE TABLE streaks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    leetcode_streak INT DEFAULT 0,
    applications_streak INT DEFAULT 0,
    project_streak INT DEFAULT 0,
    last_leetcode_date DATE,
    last_application_date DATE,
    last_project_date DATE,
    longest_leetcode INT DEFAULT 0,
    longest_applications INT DEFAULT 0,
    longest_project INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Daily check-ins
CREATE TABLE checkins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    date DATE DEFAULT CURRENT_DATE,
    leetcode_done BOOLEAN DEFAULT FALSE,
    applications_sent INT DEFAULT 0,
    project_worked BOOLEAN DEFAULT FALSE,
    notes TEXT,
    mood INT CHECK (mood BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Placement application log
CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT CHECK (status IN ('applied', 'oa', 'interview', 'offer', 'rejected')),
    applied_at DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conversation history for multi-turn Claude context
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    role TEXT CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Claude Integration

### Model
Use `claude-haiku-4-5-20251001` for all completions. Fast, cheap, perfect
for conversational back-and-forth. Route to Sonnet only for premium features
like CV review or deep leetcode analysis.

### Personality System Prompt

```
You are Koda — an AI accountability agent for CS students grinding for
internships and placements. You are their hype man, their mirror, and
their critic all at once.

Your tone: direct, dry, occasionally sharp. Think senior dev who's seen
too many students give up in October. You care, but you don't coddle.

Rules:
- Never give generic motivational quotes. Ever.
- If the user missed their streak, call it out. Don't soften it.
- If they're making excuses, name it. Don't validate it.
- If they're doing well, acknowledge it briefly — then push harder.
- Keep responses concise. No walls of text.
- Use light humour where it lands naturally. Don't force it.
- Remember context from previous messages. Reference it.

You have access to the user's current streak, recent check-in history,
application count, target companies, weak areas and goals. Use this data.
Do not pretend you don't know it.
```

### Context Injection Pattern

Always inject user state into the system prompt at request time:

```python
def build_system_prompt(user_context: dict) -> str:
    return f"""
{BASE_PERSONALITY_PROMPT}

Current user data:
- Name: {user_context['full_name']}
- Year of study: {user_context['year_of_study']}
- University: {user_context['university']}
- Target companies: {', '.join(user_context['target_companies'] or [])}
- Weak areas: {', '.join(user_context['weak_areas'] or [])}
- Goals: {user_context['goals']}
- LeetCode streak: {user_context['leetcode_streak']} days
- Applications streak: {user_context['applications_streak']} days
- Last check-in: {user_context['last_checkin']}
"""
```

### Multi-turn Conversation

Persist message history in the `messages` table. On each interaction fetch
the last 20 messages for that user and pass them as the messages array.
Cap context at 20 messages to control token usage.

```python
async def get_koda_response(telegram_id: int, new_message: str) -> str:
    history = await fetch_recent_messages(telegram_id, limit=20)
    user_context = await fetch_user_context(telegram_id)

    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=build_system_prompt(user_context),
        messages=history + [{"role": "user", "content": new_message}]
    )

    content = response.content[0].text
    await save_message(telegram_id, "user", new_message)
    await save_message(telegram_id, "assistant", content)
    return content
```

---

## Stripe Webhook Flow

```
User pays on landing page
        ↓
Stripe fires checkout.session.completed event
        ↓
/api/webhook receives POST
        ↓
Verify Stripe signature
        ↓
Extract telegram_id from metadata
        ↓
Set users.is_premium = TRUE in Supabase
        ↓
Bot sends activation message to user
```

**Always verify the Stripe webhook signature. Never skip this.**

```python
@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        telegram_id = session["metadata"]["telegram_id"]
        await activate_user(telegram_id)

    return {"status": "ok"}
```

---

## Environment Variables

```env
TELEGRAM_BOT_TOKEN=
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=
ENVIRONMENT=development
APP_URL=
```

---

## Build Layers

### Layer 1 — Core Bot (Ship First)
- [ ] Telegram bot running locally
- [ ] `/start` command with conversational onboarding
- [ ] User profile saved to Supabase on onboarding
- [ ] Claude API responding with Koda personality
- [ ] Message history persisted and passed as context
- [ ] Freeform message handling via message_handler
- [ ] Deployed on Railway, connected to Supabase

### Layer 2 — Data Tracking
- [ ] LeetCode streak logging via check-in prompt
- [ ] Application tracker (`/addapp`, `/apps` commands)
- [ ] `/status` command showing streak + app summary
- [ ] Daily check-in cron job via APScheduler
- [ ] Streak logic — increment, reset, longest streak

### Layer 3 — Monetisation
- [ ] Landing page with Stripe Checkout
- [ ] Stripe webhook activating premium access
- [ ] Gate premium features behind `is_premium` check
- [ ] Confirmation message sent to user on activation

### Layer 4 — Web Dashboard (Stretch)
- [ ] Supabase Auth login
- [ ] Dashboard showing streak, applications, check-in history
- [ ] Accessible via link sent by bot

---

## Commands

| Command       | Description                            |
|---------------|----------------------------------------|
| `/start`      | Register user and begin onboarding     |
| `/checkin`    | Trigger manual check-in                |
| `/streak`     | Show current streak detail             |
| `/profile`    | Show user profile and goals            |
| `/addapp`     | Log a new placement application        |
| `/apps`       | List all logged applications           |
| `/updateapp`  | Update status of an application        |
| `/help`       | List available commands                |

---

## Key Constraints & Decisions

- **No LeetCode API scraping in v1.** User self-reports. Validate later with
  LeetCode GraphQL API if there's time.
- **Telegram handles identity.** `telegram_id` is the primary user identifier
  throughout. No separate login needed for the bot layer.
- **Keep Claude responses short.** Max 500 tokens. Koda is punchy, not verbose.
- **Haiku for all standard conversations.** Route to Sonnet only for premium
  features requiring deeper reasoning.
- **Stripe metadata.** Pass `telegram_id` in Stripe Checkout session metadata
  so the webhook can activate the correct user.
- **Railway for everything.** Bot and API run as separate services on Railway.
  Use Railway's environment variable management — no secrets in code.
- **messages table for memory.** Last 20 messages passed as context on every
  Claude call so Koda remembers the conversation.

---

## Timeline

| Date         | Milestone                                        |
|--------------|--------------------------------------------------|
| End of April | Layer 1 live on Railway                          |
| Mid May      | Layer 2 complete, bot usable by real users       |
| End of May   | Layer 3 complete, Stripe flow working end-to-end |
| June–August  | Polish, real users, portfolio write-up           |
| September    | Portfolio-ready, placement apps open             |

*From June 12, part-time job hours increase — prioritise Layer 1 and 2 before then.*

---

## Portfolio Talking Points

- Shipped a live product used by real people (not localhost)
- Multi-turn conversational AI with persistent context and user state injection
- Stripe webhook integration with signature verification
- Supabase relational schema design with row-level security
- Railway deployment with environment separation
- Personality-driven prompt engineering producing consistent, non-generic AI behaviour