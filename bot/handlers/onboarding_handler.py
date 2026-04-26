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
from bot.koda import onboarding_parser

logger = logging.getLogger(__name__)

ONBOARDING = 0

# Each value is a list of strings — each string is sent as a separate Telegram message.
# Step 0 is the cold open, sent directly from start(). Steps 1-11 are sent after parsing the previous response.
STEP_QUESTIONS = {
    0: [
        "yo. i'm Koda.",
        "i'm not your therapist and i'm not a motivational poster.",
        "i'm the thing that's gonna make sure you actually get that placement.",
        "before we start — what do i call you?",
    ],
    1: ["which uni are you at, and what year are you in?"],
    2: [
        "placement year, summer internship, or grad job — what are you going for?",
        "and when do apps open for you?",
    ],
    3: [
        "are you an international student?",
        "affects some of the advice i'll give you around sponsorship and timelines.",
    ],
    4: [
        "who are you actually trying to get into?",
        "be specific — faang, finance (goldman, jane street etc), startups, consultancy, or you genuinely don't know yet?",
    ],
    5: [
        "which industry do you want your projects to reflect?",
        "finance, big tech, startup, consultancy, or not sure yet?",
        "this matters — i'm gonna make sure your portfolio speaks the language of wherever you're applying.",
    ],
    6: [
        "real talk — where are you technically right now?",
        "complete beginner, know the basics but haven't shipped anything, shipped some stuff locally, or got something live in prod?",
    ],
    7: ["do you have a github? if yes, drop the link — if no, just say no."],
    8: ["leetcode — are you grinding, just started, or haven't touched it yet?"],
    9: [
        "what do you know is weak right now?",
        "dsa, system design, behavioural interviews, building projects, networking — be honest.",
    ],
    10: [
        "how hard do you want me to be on you?",
        "default (i push you but i'm human about it), no mercy (i call you out every single time), or light touch (gentle nudges).",
    ],
    11: [
        "last one — what time do you want your daily check-in?",
        "i'll message you every day at that time if you've gone quiet. give me a time like 8pm or 20:00.",
    ],
}

STEP_PARSERS = {
    0: onboarding_parser.parse_name,
    1: onboarding_parser.parse_university_year,
    2: onboarding_parser.parse_target_type_deadline,
    3: onboarding_parser.parse_international,
    4: onboarding_parser.parse_target_companies,
    5: onboarding_parser.parse_target_industry,
    6: onboarding_parser.parse_experience_level,
    7: onboarding_parser.parse_github,
    8: onboarding_parser.parse_leetcode_status,
    9: onboarding_parser.parse_weak_areas,
    10: onboarding_parser.parse_accountability_style,
    11: onboarding_parser.parse_nudge_time,
}

# Plain-English description of what each step is asking — passed to Claude for intent-aware responses.
STEP_CONTEXT = {
    0: "what name they want Koda to call them",
    1: "which university they attend and what year of study they're in",
    2: "whether they're targeting a placement year, summer internship, or graduate job — and when applications typically open for them",
    3: "whether they are an international student, which affects visa sponsorship advice and application timelines",
    4: "which specific companies or types of companies they're actually trying to get into",
    5: "which industry they want their technical projects to reflect — finance, big tech, startup, or consultancy",
    6: "their current technical experience level — whether they're a complete beginner, know the basics, have shipped projects locally, or have something live in production with real users",
    7: "whether they have a GitHub account and if so what the URL is",
    8: "where they're at with LeetCode — whether they're grinding it regularly, have just started, or haven't touched it yet",
    9: "which areas of their technical or job-search preparation they know are currently weak",
    10: "how hard they want Koda to push them — default, no mercy, or light touch",
    11: "what time each day they want Koda to send a check-in nudge if they've gone quiet",
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


async def _send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    messages: list[str],
    delay: float = 0.7,
) -> None:
    for msg in messages:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await asyncio.sleep(delay)
        await update.message.reply_text(msg)


def _get_ack(step: int, parsed: dict, user: dict) -> list[str] | None:
    """Return a brief acknowledgement message after parsing each step, or None to skip."""
    name = parsed.get("name") or user.get("name") or ""

    if step == 0:
        return [f"nice, {name}."] if name else None
    if step == 1:
        uni = parsed.get("university") or ""
        return [f"{uni}. noted."] if uni else None
    if step == 2:
        target = parsed.get("target_type") or ""
        label = {"placement": "placement year", "internship": "summer internship", "grad": "grad job"}.get(target, target)
        return [f"{label}. got it."] if label else None
    if step == 3:
        if parsed.get("is_international"):
            return ["got it — i'll factor in visa and sponsorship stuff where it's relevant."]
        return ["cool, no sponsorship constraints to worry about then."]
    if step == 4:
        companies = parsed.get("target_companies") or []
        if companies:
            preview = ", ".join(companies[:2])
            suffix = "..." if len(companies) > 2 else ""
            return [f"{preview}{suffix}. ambitious. let's make sure your projects back that up."]
        return None
    if step == 5:
        industry = parsed.get("target_industry") or ""
        label = {"finance": "finance", "bigtech": "big tech", "startup": "startups", "consultancy": "consultancy", "unknown": "keeping it open"}.get(industry, industry)
        return [f"{label}. that shapes everything about your project strategy."] if label else None
    if step == 6:
        level = parsed.get("experience_level") or ""
        lines = {
            "beginner": "everyone starts somewhere. we'll build from the ground up.",
            "basics": "you've got the foundation. now you need to actually ship something.",
            "shipped_locally": "you can build. you just need to get it deployed and in front of people.",
            "live_in_prod": "you've got something live — that's the starting point we need.",
        }
        return [lines[level]] if level in lines else None
    if step == 7:
        if parsed.get("has_github"):
            return ["good. we'll make sure it looks the part."]
        return ["we need to fix that. no github in 2025 is a red flag to most recruiters."]
    if step == 8:
        status = parsed.get("leetcode_status") or ""
        lines = {
            "grinding": "good. don't stop.",
            "started": "started is better than nothing. let's build the daily habit.",
            "not_started": "we'll fix that. one problem a day. that's it to start.",
        }
        return [lines[status]] if status in lines else None
    if step == 9:
        areas = parsed.get("weak_areas") or []
        if areas:
            preview = ", ".join(areas[:2])
            return [f"noted. {preview} — we'll work on those."]
        return None
    if step == 10:
        style = parsed.get("accountability_style") or ""
        lines = {
            "default": "default it is. firm but fair.",
            "no_mercy": "no mercy. you asked for it.",
            "light_touch": "light touch. i'll still call you out, just with more grace.",
        }
        return [lines[style]] if style in lines else None
    return None


async def _complete_onboarding(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: int,
) -> None:
    user = get_user(telegram_id)
    if not user:
        await _send(update, context, ["something went wrong loading your profile. send /start to try again."])
        return

    name = user.get("name") or user.get("full_name") or "mate"
    target_industry = user.get("target_industry") or "unknown"

    await _send(update, context, ["give me a sec."], delay=0.5)
    await asyncio.sleep(0.8)

    # Generate personalised summary via Claude
    summary_text = await asyncio.to_thread(onboarding_parser.generate_summary, user)
    summary_lines = [line.strip() for line in summary_text.split("\n") if line.strip()]
    await _send(update, context, summary_lines, delay=0.8)

    await asyncio.sleep(0.6)

    # Project guidance based on target_industry
    guidance = _PROJECT_GUIDANCE.get(target_industry, _PROJECT_GUIDANCE["unknown"])
    industry_label = {
        "finance": "finance",
        "bigtech": "big tech",
        "startup": "startups",
        "consultancy": "consultancy",
        "unknown": "where you want to go",
    }.get(target_industry, target_industry)

    project_messages = [
        "alright — let's talk about the one thing that'll move the needle most. your anchor project.",
        f"for {industry_label}: {guidance['frame']}",
        f"what to build: {guidance['recommend']}.",
        "the goal is to make you T-shaped — one deep industry-relevant project you can talk about for 20 minutes, plus 1-2 others that show range.",
        "the anchor project is your vertical. everything else is your horizontal. we'll work on both.",
        f"so {name} — what do you have going right now? anything in progress, or starting from scratch?",
    ]
    await _send(update, context, project_messages, delay=0.9)


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

    # Already onboarded — send personalised Koda greeting and exit
    if user.get("onboarding_complete"):
        name = user.get("name") or user.get("full_name") or "mate"
        streak = get_streak(telegram_id)
        lc_streak = streak.get("leetcode_streak", 0) if streak else 0
        streak_line = (
            f"{lc_streak}-day leetcode streak 🔥 keep it going."
            if lc_streak > 0
            else "no active streak right now. fix that today."
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
        greeting = f"welcome back{', ' + name if name else ''}. let's pick up where we left off."
        await _send(update, context, [greeting], delay=0.6)
        await asyncio.sleep(0.4)
        await _send(update, context, STEP_QUESTIONS[current_step])
        return ONBOARDING

    # Fresh start — cold open
    await _send(update, context, STEP_QUESTIONS[0])
    update_user(telegram_id, onboarding_step=0)
    return ONBOARDING


def _lines(text: str) -> list[str]:
    """Split Claude-generated text into sendable lines, filtering blanks."""
    return [l.strip() for l in text.split("\n") if l.strip()]


async def handle_onboarding_response(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    telegram_id = update.effective_user.id
    user_message = update.message.text.strip()

    user = get_user(telegram_id)
    if not user:
        await update.message.reply_text("something went wrong. send /start to try again.")
        return ConversationHandler.END

    current_step = user.get("onboarding_step") or 0
    step_context = STEP_CONTEXT.get(current_step, "what you're asking")

    # Classify intent before attempting to parse
    intent = await asyncio.to_thread(
        onboarding_parser.classify_intent, user_message, step_context
    )
    logger.info(f"onboarding step={current_step} intent={intent!r} user={telegram_id}")

    if intent == "clarification_request":
        response = await asyncio.to_thread(
            onboarding_parser.generate_clarification_response, user_message, step_context
        )
        await _send(update, context, _lines(response))
        return ONBOARDING

    if intent == "out_of_scope":
        response = await asyncio.to_thread(
            onboarding_parser.generate_out_of_scope_response, user_message, step_context
        )
        await _send(update, context, _lines(response))
        return ONBOARDING

    if intent == "confused":
        response = await asyncio.to_thread(
            onboarding_parser.generate_confused_response, user_message, step_context
        )
        await _send(update, context, _lines(response))
        return ONBOARDING

    # intent == "answer" — attempt structured parse
    parser = STEP_PARSERS.get(current_step)
    if parser is None:
        logger.error(f"No parser for onboarding step {current_step} — user {telegram_id}")
        return ConversationHandler.END

    parsed = await asyncio.to_thread(parser, user_message)

    if parsed is None:
        # Classified as an answer but structured parse still failed —
        # treat as confused so Koda re-explains without a generic error message
        response = await asyncio.to_thread(
            onboarding_parser.generate_confused_response, user_message, step_context
        )
        await _send(update, context, _lines(response))
        return ONBOARDING

    # Save parsed fields — skip None values so we don't overwrite prior valid data
    db_updates = {k: v for k, v in parsed.items() if v is not None}
    next_step = current_step + 1
    db_updates["onboarding_step"] = next_step

    if next_step >= 12:
        db_updates["onboarding_complete"] = True

    update_user(telegram_id, **db_updates)

    if next_step >= 12:
        ack = _get_ack(current_step, parsed, user)
        if ack:
            await _send(update, context, ack, delay=0.6)
        await asyncio.sleep(0.4)
        await _complete_onboarding(update, context, telegram_id)
        return ConversationHandler.END

    ack = _get_ack(current_step, parsed, user)
    if ack:
        await _send(update, context, ack, delay=0.6)
        await asyncio.sleep(0.3)

    await _send(update, context, STEP_QUESTIONS[next_step])
    return ONBOARDING


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "no worries. send /start whenever you're ready to set up."
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
