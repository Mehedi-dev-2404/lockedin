import asyncio
import logging
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from db.queries.user_queries import get_user, create_user, update_user, user_exists
from db.queries.streak_queries import get_streak, create_streak
from db.queries.message_queries import save_message, get_recent_messages
from bot.koda import onboarding_parser
from bot.koda.onboarding_parser import STEP_KNOWLEDGE, STEP_REQUIRED_FIELDS, SKIPPABLE_STEPS

logger = logging.getLogger(__name__)

ONBOARDING = 0

# Initial questions for each step — short and conversational.
# These are what Koda asks on first approach. Re-asks after clarification/confusion
# are generated dynamically by generate_response, so they're never identical.
STEP_QUESTIONS = {
    0: [
        "yo. i'm Koda.",
        "i'm not your therapist and i'm not a motivational poster.",
        "i'm the thing that's gonna make sure you actually get that placement.",
        "before we start — what do i call you?",
    ],
    1: ["which uni are you at, and what year?"],
    2: [
        "placement year, summer internship, or grad job — what are you going for?",
        "and when do apps typically open for you?",
    ],
    3: ["are you an international student? affects the advice i give around sponsorship."],
    4: ["who are you actually trying to get into? be specific if you can."],
    5: [
        "which industry do you want your projects to reflect?",
        "finance, big tech, startup, or consultancy?",
    ],
    6: [
        "real talk — where are you technically right now?",
        "complete beginner, know the basics, shipped stuff locally, or got something live in prod?",
    ],
    7: ["github — got one? drop the link if yes, just say no if not."],
    8: ["leetcode — grinding, just started, or haven't touched it?"],
    9: ["what do you know is weak right now? be honest."],
    10: [
        "how hard do you want me to be on you?",
        "default, no mercy, or light touch.",
    ],
    11: ["last one — what time do you want your daily check-in? give me a time like 8pm or 20:00."],
}

# Plain-English descriptions for resume messages and context passing.
STEP_CONTEXT = {
    0: "your name",
    1: "your university and year",
    2: "your target role type and application timeline",
    3: "whether you're an international student",
    4: "your target companies",
    5: "which industry to frame your projects around",
    6: "your current technical experience level",
    7: "your GitHub",
    8: "your LeetCode status",
    9: "your weak areas",
    10: "how hard you want to be pushed",
    11: "your daily check-in time",
}

_PROJECT_GUIDANCE = {
    "finance": {
        "recommend": "a risk engine, fraud detection system, portfolio tracker with real market data, or an audit trail system",
        "frame": "finance interviewers want to see you understand data integrity, risk, and systems that don't fail. build something with real financial logic in it.",
    },
    "bigtech": {
        "recommend": "a developer tool, an API with clean architecture, a system with scale considerations, or an AI agent with tool use",
        "frame": "big tech wants to see you think about scale and clean abstractions. build something you can talk about architecturally.",
    },
    "startup": {
        "recommend": "a full stack shipped product with real users — something monetised or attempted to monetise",
        "frame": "startups want evidence you ship. build something live with real users, even 10 people.",
    },
    "consultancy": {
        "recommend": "a tool that solves a clear business problem with a measurable outcome — dashboard, automation tool, anything with explainable ROI",
        "frame": "consultancies want to see you understood the problem before writing a line of code. frame everything around the business outcome.",
    },
    "unknown": {
        "recommend": "a project that crosses two industries — like a compliance tool or a financial data dashboard",
        "frame": "since you're keeping doors open, build something that speaks to at least two industries at once.",
    },
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

async def _send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    messages: list[str],
    delay: float = 0.7,
) -> None:
    """Send a list of strings as individual Telegram messages with typing indicator."""
    for msg in messages:
        if not msg.strip():
            continue
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await asyncio.sleep(delay)
        await update.message.reply_text(msg)


def _lines(text: str) -> list[str]:
    return [l.strip() for l in text.split("\n") if l.strip()]


def _check_already_answered(step: int, user: dict) -> bool:
    """Return True if the step's required fields are already saved in the user record."""
    required = STEP_REQUIRED_FIELDS.get(step, [])
    return bool(required) and all(user.get(f) is not None for f in required)


def _find_next_step(user: dict) -> int:
    """
    Scan steps 0-11 and return the first step whose required fields are missing
    from the user record. Returns 12 if all steps are answered.
    """
    for step in range(12):
        if not _check_already_answered(step, user):
            return step
    return 12


def _get_ack(step: int, parsed: dict, user: dict) -> list[str] | None:
    """
    Return a one-line acknowledgement after a successful parse, or None to skip.
    Skipped when it would feel mechanical — e.g. restating the obvious.
    """
    if step == 0:
        name = parsed.get("name") or ""
        return [f"nice, {name}."] if name else None
    if step == 1:
        uni = parsed.get("university") or ""
        return [f"{uni}. got it."] if uni else None
    if step == 2:
        t = parsed.get("target_type") or ""
        label = {"placement": "placement year", "internship": "summer internship", "grad": "grad job"}.get(t, t)
        return [f"{label}. got it."] if label else None
    if step == 3:
        if parsed.get("is_international"):
            return ["noted — i'll flag sponsorship stuff where it matters."]
        return ["cool, no sponsorship constraints then."]
    if step == 4:
        companies = parsed.get("target_companies") or []
        if companies:
            preview = ", ".join(str(c) for c in companies[:2])
            suffix = "..." if len(companies) > 2 else ""
            return [f"{preview}{suffix}. let's make sure your projects back that up."]
        return None
    if step == 5:
        industry = parsed.get("target_industry") or ""
        label = {
            "finance": "finance", "bigtech": "big tech", "startup": "startups",
            "consultancy": "consultancy", "unknown": "keeping it open",
        }.get(industry, industry)
        return [f"{label}. that shapes everything."] if label else None
    if step == 6:
        level = parsed.get("experience_level") or ""
        msgs = {
            "beginner": "everyone starts somewhere. we'll build from the ground up.",
            "basics": "foundation's there. now you need to ship.",
            "shipped_locally": "you can build. just need to get it deployed.",
            "live_in_prod": "something live already. good starting point.",
        }
        return [msgs[level]] if level in msgs else None
    if step == 7:
        if parsed.get("has_github"):
            return ["good. we'll make sure it looks the part."]
        return ["we'll fix that. no github in 2025 is a red flag."]
    if step == 8:
        status = parsed.get("leetcode_status") or ""
        msgs = {
            "grinding": "good. don't stop.",
            "started": "started is better than nothing. let's build the habit.",
            "not_started": "we'll fix that. one problem a day to start.",
        }
        return [msgs[status]] if status in msgs else None
    if step == 9:
        areas = parsed.get("weak_areas") or []
        if areas:
            preview = ", ".join(str(a) for a in areas[:2])
            return [f"noted. {preview} — we'll work on those."]
        return None
    if step == 10:
        style = parsed.get("accountability_style") or ""
        msgs = {
            "default": "default it is. firm but fair.",
            "no_mercy": "no mercy. you asked for it.",
            "light_touch": "light touch. i'll still call you out, just with more grace.",
        }
        return [msgs[style]] if style in msgs else None
    return None


def _specific_action_today(user: dict) -> str:
    """Return one concrete action for the user to take today based on their profile."""
    level = user.get("experience_level") or "basics"
    weak = user.get("weak_areas") or []
    leetcode = user.get("leetcode_status") or "not_started"

    if level == "beginner":
        return "today: write something that actually runs. not a tutorial — your own script. anything."
    if level == "basics":
        if "DSA" in weak or leetcode == "not_started":
            return "today: open leetcode and do one easy problem. just one."
        return "today: pick one project idea, make a repo, and write the first file. not the readme — actual code."
    if level == "shipped_locally":
        return "today: deploy something. doesn't have to be perfect. just get it live somewhere."
    if level == "live_in_prod":
        if "DSA" in weak or leetcode in ("not_started", "started"):
            return "today: 3 leetcode mediums. you can ship — now fix the interview prep gap."
        return "today: add one real feature to your live project. commit it before you sleep."
    return "today: open your laptop and actually start. that's the whole action."


# ---------------------------------------------------------------------------
# Onboarding completion
# ---------------------------------------------------------------------------

async def _completion_sequence(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: int,
) -> None:
    user = get_user(telegram_id)
    if not user:
        await _send(update, context, ["something went wrong. send /start to try again."])
        return

    name = user.get("name") or user.get("full_name") or "mate"
    target_industry = user.get("target_industry") or "unknown"

    await _send(update, context, ["give me a sec."], delay=0.5)
    await asyncio.sleep(0.8)

    # Personalised profile summary
    summary_text = await asyncio.to_thread(onboarding_parser.generate_summary, user)
    summary_lines = _lines(summary_text)
    await _send(update, context, summary_lines, delay=0.8)

    await asyncio.sleep(0.5)

    # Project guidance
    guidance = _PROJECT_GUIDANCE.get(target_industry, _PROJECT_GUIDANCE["unknown"])
    industry_label = {
        "finance": "finance", "bigtech": "big tech", "startup": "startups",
        "consultancy": "consultancy", "unknown": "where you want to go",
    }.get(target_industry, target_industry)

    project_messages = [
        "alright — your anchor project.",
        f"for {industry_label}: {guidance['frame']}",
        f"what to build: {guidance['recommend']}.",
        "the goal is to make you T-shaped — one deep industry-relevant project you can talk about for 20 minutes, plus 1-2 others that show range.",
        "anchor project is your vertical. everything else is horizontal. we'll work on both.",
        _specific_action_today(user),
        f"what do you have going right now, {name}?",
    ]
    await _send(update, context, project_messages, delay=0.9)

    # Save Koda's completion messages to history
    completion_text = " | ".join(project_messages)
    save_message(telegram_id, "assistant", completion_text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    tg_user = update.effective_user

    if not user_exists(telegram_id):
        result = create_user(
            telegram_id=telegram_id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        if not result:
            logger.error(f"create_user returned None for telegram_id={telegram_id}")
            await update.message.reply_text(
                "something went wrong setting up your account. please try /start again."
            )
            return ConversationHandler.END
        if not get_streak(telegram_id):
            create_streak(telegram_id)

    user = get_user(telegram_id)
    if not user:
        await update.message.reply_text(
            "something went wrong loading your profile. please try /start again."
        )
        return ConversationHandler.END

    # Already onboarded — personalised greeting
    if user.get("onboarding_complete"):
        name = user.get("name") or user.get("full_name") or "mate"
        streak = get_streak(telegram_id)
        lc_streak = streak.get("leetcode_streak", 0) if streak else 0
        streak_line = (
            f"{lc_streak}-day leetcode streak. keep it going."
            if lc_streak > 0
            else "no active streak. fix that today."
        )
        await _send(update, context, [
            f"hey {name}, welcome back.",
            streak_line,
            "what are you working on today?",
        ])
        return ConversationHandler.END

    current_step = user.get("onboarding_step") or 0

    # Resuming mid-onboarding
    if current_step > 0:
        name = user.get("name") or ""
        step_description = STEP_CONTEXT.get(current_step, "where we left off")
        resume_lines = [
            f"welcome back{', ' + name if name else ''}.",
            f"we left off at {step_description}.",
        ] + STEP_QUESTIONS[current_step]
        await _send(update, context, resume_lines, delay=0.6)
        return ONBOARDING

    # Fresh start — cold open
    await _send(update, context, STEP_QUESTIONS[0])
    update_user(telegram_id, onboarding_step=0)
    return ONBOARDING


# ---------------------------------------------------------------------------
# Main response handler
# ---------------------------------------------------------------------------

async def handle_onboarding_response(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    telegram_id = update.effective_user.id
    user_message = update.message.text.strip()

    # Silently ignore empty messages
    if not user_message:
        return ONBOARDING

    user = get_user(telegram_id)
    if not user:
        await update.message.reply_text("something went wrong. send /start to try again.")
        return ConversationHandler.END

    current_step = user.get("onboarding_step") or 0

    # Fetch conversation history for context
    history = await asyncio.to_thread(get_recent_messages, telegram_id, 15)

    # Save the user's message to history
    await asyncio.to_thread(save_message, telegram_id, "user", user_message)

    # Duplicate message detection
    last_user_msg = next(
        (m["content"] for m in reversed(history) if m.get("role") == "user"), None
    )
    if last_user_msg and last_user_msg.strip() == user_message:
        dupe_response = ["you already sent that.", STEP_QUESTIONS[current_step][-1]]
        await _send(update, context, dupe_response)
        return ONBOARDING

    # Classify intent — pure Claude, no keyword matching
    intent = await asyncio.to_thread(
        onboarding_parser.classify_intent, user_message, current_step, history
    )
    logger.info(f"onboarding step={current_step} intent={intent!r} user={telegram_id}")

    # -------------------------------------------------------------------
    # non_text
    # -------------------------------------------------------------------
    if intent == "non_text":
        await _send(update, context, ["can't read that. just type it out."])
        await asyncio.sleep(0.4)
        await _send(update, context, [STEP_QUESTIONS[current_step][-1]])
        return ONBOARDING

    # -------------------------------------------------------------------
    # abuse
    # -------------------------------------------------------------------
    if intent == "abuse":
        response = await asyncio.to_thread(
            onboarding_parser.generate_response, "abuse", current_step, user_message, history, user
        )
        await _send(update, context, response)
        return ONBOARDING

    # -------------------------------------------------------------------
    # test
    # -------------------------------------------------------------------
    if intent == "test":
        response = await asyncio.to_thread(
            onboarding_parser.generate_response, "test", current_step, user_message, history, user
        )
        await _send(update, context, response)
        return ONBOARDING

    # -------------------------------------------------------------------
    # off_topic
    # -------------------------------------------------------------------
    if intent == "off_topic":
        response = await asyncio.to_thread(
            onboarding_parser.generate_response, "off_topic", current_step, user_message, history, user
        )
        await _send(update, context, response)
        return ONBOARDING

    # -------------------------------------------------------------------
    # clarification
    # -------------------------------------------------------------------
    if intent == "clarification":
        response = await asyncio.to_thread(
            onboarding_parser.generate_response, "clarification", current_step, user_message, history, user
        )
        koda_text = " | ".join(response)
        await asyncio.to_thread(save_message, telegram_id, "assistant", koda_text)
        await _send(update, context, response)
        return ONBOARDING

    # -------------------------------------------------------------------
    # confused — ask what specifically is confusing them first.
    # Their follow-up will come back as a clarification and get a proper
    # explanation. Do not re-explain the whole step here.
    # -------------------------------------------------------------------
    if intent == "confused":
        response = await asyncio.to_thread(
            onboarding_parser.generate_response, "confused", current_step, user_message, history, user
        )
        koda_text = " | ".join(response)
        await asyncio.to_thread(save_message, telegram_id, "assistant", koda_text)
        await _send(update, context, response)
        return ONBOARDING

    # -------------------------------------------------------------------
    # skip
    # -------------------------------------------------------------------
    if intent == "skip":
        if current_step in SKIPPABLE_STEPS:
            # Save nulls for skippable fields and advance
            skip_updates: dict = {"onboarding_step": current_step + 1}
            if current_step == 7:
                skip_updates["has_github"] = False
                skip_updates["github_url"] = None
            update_user(telegram_id, **skip_updates)
            refreshed = get_user(telegram_id) or user
            next_step = _find_next_step(refreshed)
            if next_step >= 12:
                update_user(telegram_id, onboarding_complete=True)
                await _completion_sequence(update, context, telegram_id)
                return ConversationHandler.END
            await _send(update, context, ["no problem."] + STEP_QUESTIONS[next_step])
            return ONBOARDING
        else:
            response = await asyncio.to_thread(
                onboarding_parser.generate_response, "skip", current_step, user_message, history, user
            )
            await _send(update, context, response)
            return ONBOARDING

    # -------------------------------------------------------------------
    # correction — user is changing a previously given answer
    # -------------------------------------------------------------------
    if intent == "correction":
        corrected = await asyncio.to_thread(
            onboarding_parser.parse_correction, user_message, history, user
        )
        if corrected:
            update_user(telegram_id, **corrected)
            # Build a readable confirmation
            field_labels = {
                "name": "name", "university": "university", "year_of_study": "year",
                "target_type": "target type", "target_companies": "target companies",
                "target_industry": "industry", "experience_level": "experience level",
                "has_github": "github", "github_url": "github url",
                "leetcode_status": "leetcode status", "weak_areas": "weak areas",
                "accountability_style": "accountability style", "nudge_time": "nudge time",
                "is_international": "international status",
            }
            parts = []
            for field, val in corrected.items():
                label = field_labels.get(field, field.replace("_", " "))
                parts.append(f"{label} → {val}")
            ack = "got it. updated: " + ", ".join(parts) + "."
            await _send(update, context, [ack], delay=0.5)
            await asyncio.sleep(0.3)
        # Re-ask current step
        await _send(update, context, [STEP_QUESTIONS[current_step][-1]])
        return ONBOARDING

    # -------------------------------------------------------------------
    # answer / multi_answer — attempt structured parse
    # -------------------------------------------------------------------
    parsed = await asyncio.to_thread(
        onboarding_parser.parse_step, current_step, user_message, history
    )

    if parsed is None:
        # Classified as answer but parse still failed — treat as confused
        response = await asyncio.to_thread(
            onboarding_parser.generate_response, "confused", current_step, user_message, history, user
        )
        koda_text = " | ".join(response)
        await asyncio.to_thread(save_message, telegram_id, "assistant", koda_text)
        await _send(update, context, response)
        return ONBOARDING

    # Save all parsed fields to DB
    db_updates = {k: v for k, v in parsed.items() if v is not None}
    update_user(telegram_id, **db_updates)

    # Reload user and find first unanswered step (handles multi_answer correctly)
    refreshed = get_user(telegram_id) or {**user, **db_updates}
    next_step = _find_next_step(refreshed)

    # If multi_answer skipped some steps, note it
    skipped_steps = [s for s in range(current_step + 1, next_step) if _check_already_answered(s, refreshed)]
    if skipped_steps:
        logger.info(f"multi_answer: skipped steps {skipped_steps} for user {telegram_id}")

    # Update the cursor in DB
    update_user(telegram_id, onboarding_step=next_step)

    if next_step >= 12:
        update_user(telegram_id, onboarding_complete=True)
        ack = _get_ack(current_step, parsed, user)
        if ack:
            await _send(update, context, ack, delay=0.6)
        await asyncio.sleep(0.4)
        await _completion_sequence(update, context, telegram_id)
        return ConversationHandler.END

    # Send brief ack for the step we just parsed
    ack = _get_ack(current_step, parsed, user)
    if ack:
        await _send(update, context, ack, delay=0.6)
        await asyncio.sleep(0.3)

    # Check if next step was already answered (multi_answer) — skip silently
    while next_step < 12 and _check_already_answered(next_step, refreshed):
        next_step += 1

    if next_step >= 12:
        update_user(telegram_id, onboarding_complete=True)
        await _completion_sequence(update, context, telegram_id)
        return ConversationHandler.END

    # Save Koda's ack to history
    if ack:
        await asyncio.to_thread(save_message, telegram_id, "assistant", " ".join(ack))

    await _send(update, context, STEP_QUESTIONS[next_step])
    return ONBOARDING


# ---------------------------------------------------------------------------
# Fallback and builder
# ---------------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "no worries. send /start whenever you're ready."
    )
    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ONBOARDING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_onboarding_response)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
