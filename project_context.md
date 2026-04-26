LockedIn — Project Context

  I am building LockedIn — a Telegram-based AI accountability agent for UK university CS students
  grinding for SWE internships and placements at top tech companies and banks (Google, Meta,
  Goldman Sachs, JPMorgan, Citadel, Jane Street). The AI agent is called Koda.

  Tagline: "Lock in. Land the offer."

  Target audience: UK university CS students, 1st-3rd year, grinding for summer internships at top
   tech companies and banks.

  --- ABOUT ME ---
  Mehedi. First-year CS BSc at University of Greenwich (graduation 2028).
  International student on a Student visa, will need sponsorship.
  Currently doing an unpaid internship at cousin's company (OoNt Labs) building AI agents for a
  PMS guest messaging system.
  Targeting corporate banking/finance placements and big tech.
  Placement applications open October/November 2025.
  Stripe will be set up under brother's name (can't receive payments directly on Student visa).
  Already done arrays and hashing from blind 75. Grinding NeetCode blind 75 for OA prep. DP is a
  known weak spot.

  --- CURRENT STATE ---
  - Telegram bot live on Railway 24/7
  - Landing page live on Vercel: https://lockedin-orpin-three.vercel.app
  - Bot username: @lockedingrind_bot
  - Full stack: Python, Claude Haiku API, python-telegram-bot, Supabase, Railway, Vercel
  - Codebase: github.com/Mehedi-dev-2404/lockedin

  --- LANDING PAGE STATE (web/index.html) ---
  - Single hero only — one viewport, no scroll
  - Pure HTML/CSS/JS single file (no React, no framework, no build step)
  - Deep navy background (hsl(218 64% 8%) ≈ #0a1929), NOT pure black
  - Typography: Instrument Serif for display (italics for emphasis), Inter for body, JetBrains
  Mono for accents — loaded from Google Fonts
  - Hero copy:
  • Section label (mono): "STARTING UP. LOCKING IN."
  • Main headline (Instrument Serif): "Built for the ones who don't sleep." with italic emphasis
  on "don't sleep"
  • Tagline (italic): "Lock in. Land the offer."
  • Subhead: "The AI accountability agent for CS students grinding for internships. On Telegram.
  Always watching."
  • CTA: "Start grinding →" (liquid-glass button with cyan glow pulse)
  • Mono trial line: "Free 7-day trial. Cancel anytime."
  • Bottom corners: "KODA / V1.0" left, "ACCOUNTABILITY ENGINE" right
  - Visual centrepiece: static koda.jpg orb image (cyan-to-deep-blue gradient sphere) layered
  behind text
  • Slow rotation animation (80s linear, infinite)
  • Scale-breathing animation (7s ease-in-out)
  • Multi-layer cyan glow halo with breathing opacity
  • Mouse parallax on desktop (disabled on touch)
  - Hyper-cinematic load sequence: staggered fade-rise on every element, 0ms → 2700ms total
  - All easing: cubic-bezier(0.16, 1, 0.3, 1) — never linear, never default ease
  - Mobile responsive at 768px breakpoint
  - prefers-reduced-motion respected
  - File location: web/index.html
  - Asset: web/koda.jpg (served at /koda.jpg via Vercel)
  - web/koda.mp4 exists in the web directory — currently unused in the HTML
  - DEPLOYMENT NOTE: index.html is at web/index.html — Vercel likely needs a vercel.json rewrite
  rule to serve it at the root path, or the file needs to be moved to the repo root before going
  fully production-live

  KNOWN LANDING PAGE BUGS:
  - Mobile orb was rendering octagonal due to Safari iOS compositor bug (overflow:hidden +
  border-radius:50% failing to clip transformed children at GPU layer level). Fix applied: forced
  composite layer on .orb-container via isolation: isolate + translateZ(0) + Safari mask hack,
  removed transform: scale(1.08) on img (replaced with width/height 110% + negative margin), added
   clip-path: circle() as belt-and-braces, added border-radius + overflow:hidden +
  isolation:isolate to .orb-spin.
  Verify on iOS Safari before claiming fully fixed.

  --- WHAT'S BUILT (BOT) ---
  - Full conversational onboarding (12 steps) with Claude-powered intent classification (10 intent
   types), flexible parsing, rich STEP_KNOWLEDGE, resume on drop-off, multi_answer support,
  correction handling, confused → one-line probe flow
  - Koda personality (new hype-friend voice already live in personality.py): texting style,
  "bro/yo/fr/lowkey", celebrates wins then pushes harder, accountability style modifiers
  (no_mercy/light_touch/default), full SWE pipeline knowledge
  - build_system_prompt() injects full user context into every Claude call: name, year,
  university, target companies, target industry, experience level, LeetCode status, GitHub, weak
  areas, accountability style, streaks, LeetCode topics completed, international status
  - Multi-turn conversation with persistent message history (last 20 messages, conversation type
  only)
  - message_type column on messages table ('onboarding'/'conversation') — onboarding history
  separated from Koda conversation context so it never pollutes the Claude context window
  - Daily nudge scheduler with per-user nudge_time: groups active users by nudge_time at startup,
  schedules one job per unique time, falls back to 20:00 Europe/London for null/malformed values
  - LeetCode streak tracking: auto-detected from natural conversation via intent classifier, blind
   75 topic progress saved to leetcode_progress JSONB column (case-insensitive dedup). Milestones
  fire at every 7-day multiple.
  - Application tracking: auto-detected company/role from conversation, saved to applications
  table, applications streak tracked
  - Project streak tracking: auto-detected from conversation
  - Check-in system with upsert logic
  - 80 message free tier: tracked via total_message_count on users table, returns None from
  get_koda_response when limit hit, message_handler sends upgrade prompt
  - is_premium=True on users table bypasses message limit
  - /streak, /profile, /checkin, /help, /resetonboarding commands
  - /resetonboarding is admin-only, gated by ADMIN_TELEGRAM_ID env var
  - Shared utilities: anthropic_client.py (single shared Anthropic instance), utils.py
  (clean_json, get_display_name, build_user_context)
  - All audit fixes 1-8 applied: is_onboarded removed, single anthropic client,
  clean_json/get_display_name/build_user_context in utils.py, user_exists() removed (get_user()
  used as single check), nudge_time wired to scheduler, message_type column on messages

  --- USERS TABLE SCHEMA (actual, extended from original spec) ---
  Fields beyond the CLAUDE.md original spec that are live in the codebase:
  - name TEXT (first name captured during onboarding, separate from full_name)
  - onboarding_step INT (cursor for resume-on-drop-off)
  - onboarding_complete BOOLEAN (single source of truth, replaces is_onboarded)
  - target_type TEXT (placement/internship/grad)
  - target_industry TEXT (finance/bigtech/startup/consultancy/unknown)
  - experience_level TEXT (beginner/basics/shipped_locally/live_in_prod)
  - has_github BOOLEAN
  - github_url TEXT
  - leetcode_status TEXT (grinding/started/not_started)
  - accountability_style TEXT (default/no_mercy/light_touch)
  - is_international BOOLEAN
  - app_deadline TEXT
  - nudge_time TEXT (HH:MM format, e.g. "20:00")
  - leetcode_progress JSONB (array of completed topic strings)
  - total_message_count INT (tracks free tier usage)

  messages table has message_type TEXT DEFAULT 'conversation' added.

  --- CODEBASE STRUCTURE ---
  lockedin/
  ├── main.py
  ├── config/
  │   ├── settings.py          (CLAUDE_MAX_TOKENS = 1024, ADMIN_TELEGRAM_ID loaded)
  │   └── constants.py         (empty placeholder)
  ├── bot/
  │   ├── handlers/
  │   │   ├── onboarding_handler.py
  │   │   ├── message_handler.py
  │   │   ├── command_handler.py
  │   │   └── checkin_handler.py
  │   ├── koda/
  │   │   ├── anthropic_client.py  (single shared Anthropic instance)
  │   │   ├── claude_client.py     (get_koda_response, classify_intent, generate_nudge)
  │   │   ├── onboarding_parser.py (STEP_KNOWLEDGE, parse_step, classify_intent,
  generate_response)
  │   │   ├── personality.py       (BASE_SYSTEM_PROMPT + build_system_prompt)
  │   │   ├── memory.py            (empty placeholder)
  │   │   └── utils.py             (clean_json, get_display_name, build_user_context)
  │   └── scheduler/
  │       └── daily_checkin.py
  ├── db/
  │   ├── queries/
  │   │   ├── __init__.py          (supabase client)
  │   │   ├── user_queries.py
  │   │   ├── streak_queries.py
  │   │   ├── checkin_queries.py
  │   │   ├── application_queries.py
  │   │   └── message_queries.py
  │   └── models/                  (empty placeholder files)
  └── web/
      ├── index.html               (live landing page)
      ├── koda.jpg                 (orb asset, served at /koda.jpg)
      ├── koda.mp4                 (video asset, currently unused)
      ├── styles.css
      └── stripe_checkout.js

  --- WHAT'S LEFT ---
  Layer 3 — Stripe monetisation (not yet built):
  - FastAPI webhook endpoint on Railway receiving Stripe payment confirmation
  - Webhook sets is_premium=True in Supabase for paying user
  - Bot sends confirmation message on activation in Koda's voice
  - Monetisation flow: Koda drops Stripe link in chat when user hits 80 message limit, in
  character — NOT a landing page button
  - Stripe under brother's name (Student visa restriction)
  - Pricing: £9/month or £69/year
  - Add pricing section back to landing page once Stripe is live

  Onboarding rewrite:
  - Current 12-step onboarding works but uses pure freeform text
  - Planned rewrite: add Telegram keyboard buttons (InlineKeyboardMarkup/ReplyKeyboardMarkup) for
  fixed-choice steps (target_type, experience_level, accountability_style, etc.)
  - New question set may also be revised at that point

  Other remaining tasks:
  - Verify mobile orb fix on real iOS Safari (not Chrome emulation)
  - Add pricing section to landing page once Stripe live
  - LeetCode GraphQL API integration to verify streaks from actual submission data rather than
  self-reporting
  - Fix stale goals reference in profile_command (displays "—" for all current users since goals
  field is not captured during onboarding)
  - Fix stale goals reference in generate_nudge (always falls back to "landing a SWE internship"
  since build_user_context doesn't include goals)

  --- SCALE ISSUES (fix when users come, not now) ---
  - Sequential nudge sending in _make_nudge_job (needs asyncio.gather with concurrency cap)
  - get_all_active_users fetches all columns (needs SELECT specific fields)
  - Three streak update types = three separate DB reads per activity (needs batching)
  - Missing index on messages(user_id, created_at)
  - No rate limiting on Claude calls for premium users

  --- KODA'S PERSONALITY BRIEF ---
  - Core vibe: hype friend who's been through the SWE grind, energetic, fun, celebrates wins,
  roasts when you slip
  - When struggling: dials back, gets human and supportive first
  - Celebrating wins: genuinely hyped but measured ("yo that's actually huge")
  - When slipping: pretty brutal, no excuses tolerated
  - Vocabulary: uses "bro", "yo", "fr", "lowkey", "aight" naturally but not overdone
  - SWE culture: uses "grinding", "cracked", "locked in", "cooked", "OA", "superday", "the offer"
  naturally
  - Texting style: short punchy messages, split across multiple sends, never walls of text, one
  question at a time
  - Guardrails: refuses to write coursework, solve leetcode outright, write CV/cover letters from
  scratch. Redirects off-topic questions back to the grind with personality.
  - Never: corporate speak, teacher energy, "as an AI", walls of text, multiple questions at once
  - Already live in personality.py — this is not a pending rewrite

  --- LANDING PAGE COPY VOICE ---
  "Premium credibility" register — direct, slightly confrontational, never cringe, never
  hustle-bro, never emoji. The senior dev who's been through it, not the hype friend yet. The bot
  is the hype friend. The landing page is the credible older brother selling you on the hype
  friend.

  --- PRODUCT POSITIONING (locked) ---
  - Core feeling target: urgency + credibility
  - "Lock in. Land the offer." — direct, on-brand, repeated as tagline under hero headline
  - "Built for the ones who don't sleep." — main hero headline
  - Reference quality bar for the landing: Expedite (expedite.now), Tomo.ai, Resend.com — "premium
   tech with editorial soul"
  - NOT a hackathon throwaway. Visitor must believe this is real, worth paying for, worth telling
  their group chat about

  --- PORTFOLIO CONTEXT ---
  This project alongside Clearance (fraud risk engine with FastAPI, PostgreSQL, Claude API,
  tamper-evident audit trail) forms the full portfolio story:
  - Clearance = technical depth signal for finance roles
  - LockedIn = ships fast, thinks product, agentic AI signal for big tech and startups
  - Both together = range. Not a one-trick pony.

  Key CV talking points for LockedIn:
  - Went from idea to live deployed product in 2 days
  - Persistent user context injection at every Claude call: full profile, streaks, LeetCode
  progress, accountability style, target companies all injected into system prompt — Koda always
  knows who it's talking to
  - Blind 75 progress auto-detected and persisted from natural conversation via intent
  classification
  - Intent classification with 10 intent types during onboarding, pure Claude-powered (no keyword
  matching)
  - Per-user nudge scheduling, message type separation (onboarding vs conversation history),
  shared utility layer
  - 80-message free tier with is_premium bypass, tracked via total_message_count
  - Live on Railway + Vercel with real users

  ---
  Changes made from the original document:
  - web/index2.html corrected to web/index.html throughout (index2.html does not exist; index.html
   is the live file)
  - Asset path corrected from web/public/koda.jpg to web/koda.jpg
  - web/koda.mp4 added to structure and noted as currently unused
  - "Original web/index.html still exists, not in use" line removed (it is the active file)
  - "Personality rewrite" moved from What's Left to What's Built — personality.py already contains
   the new hype-friend prompt
  - "Tool use — dynamically queries user state" claim corrected: the implementation is static
  context injection via build_system_prompt at call time; Anthropic function calling API is not
  used
  - CLAUDE_MAX_TOKENS = 1024 noted (not 500 as in original CLAUDE.md spec)
  - ADMIN_TELEGRAM_ID and admin-only /resetonboarding guard added to What's Built
  - total_message_count field and free tier tracking added to What's Built
  - Extended users table schema section added — documents all fields live in the codebase beyond
  the original spec
  - memory.py and constants.py noted as empty placeholders in structure
  - Stale goals references in profile_command and generate_nudge added to What's Left as minor
  fixes
  - /addapp, /apps, /updateapp not added to What's Built (correctly absent — not implemented)
  - message_type column migration SQL requirement noted in What's Built