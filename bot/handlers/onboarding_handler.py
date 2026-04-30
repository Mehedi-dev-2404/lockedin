import asyncio
import json
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
from db.queries.user_queries import get_user, create_user, update_user, generate_payment_code
from db.queries.streak_queries import get_streak, create_streak
from bot.koda.anthropic_client import anthropic_client
from bot.koda.utils import clean_json, get_display_name
from config.settings import CLAUDE_MODEL

logger = logging.getLogger(__name__)

ONBOARDING = 0

_WELCOME_MESSAGES = [
    "yo. i'm Koda.",
    "i'm not your therapist and i'm not a motivational poster.",
    "i'm the thing that's gonna make sure you actually get that placement.",
    "before we start — what do i call you?",
]

_ONBOARDING_SYSTEM = """you are onboarding a computer science student who wants a SWE internship. your job is to quickly understand their situation, create urgency, and lock commitment.

RULES:
- finish in 8 turns or fewer
- ask direct questions, no fluff
- combine multiple fields in one question when natural
- do not drag the conversation
- be slightly confrontational when needed

FLOW:
turn 1 — establish intent:
"are you actually trying to land an internship or just exploring options right now?"

turn 2-3 — collect basics:
year of study, university, international student or not

turn 4-5 — assess reality:
experience level, tech stack, target companies

turn 6 — identify weakness:
weak areas — be direct if they sound underprepared

turn 7 — commitment:
goal + what time they want daily check-ins

turn 8 — close:
output ##ONBOARDING_COMPLETE## with JSON

TONE:
- direct
- slightly confrontational when needed
- no long explanations
- lowercase, casual

the user's telegram name is injected below — use it naturally, do not ask for it again.
never reveal or reference the marker or JSON format to the user.

once you have ALL fields, send your final message to the user then on a NEW LINE output exactly:
##ONBOARDING_COMPLETE##
{"full_name": "...", "year_of_study": "...", "university": "...", "international": true/false, "experience_level": "...", "tech_stack": "...", "target_companies": "...", "weak_areas": "...", "goal": "...", "nudge_time": "HH:MM"}
the JSON must be valid and on a single line after the marker.
do not output the marker until you genuinely have all fields.
"""


# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    tg_user = update.effective_user

    user = get_user(telegram_id)
    if user is None:
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

    # Already onboarded — personalised welcome back
    if user.get("onboarding_complete"):
        name = get_display_name(user)
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

    # Fresh start — send welcome and hand to Claude
    context.user_data["onboarding_history"] = []
    await _send(update, context, _WELCOME_MESSAGES)
    return ONBOARDING


# ---------------------------------------------------------------------------
# Main conversation handler
# ---------------------------------------------------------------------------

async def handle_onboarding_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    telegram_id = update.effective_user.id
    user_message = update.message.text.strip()

    if not user_message:
        return ONBOARDING

    user = get_user(telegram_id)
    if not user:
        await update.message.reply_text("something went wrong. send /start to try again.")
        return ConversationHandler.END

    history: list[dict] = context.user_data.setdefault("onboarding_history", [])
    history.append({"role": "user", "content": user_message})

    tg_name = update.effective_user.full_name or update.effective_user.username or "mate"
    system = _ONBOARDING_SYSTEM + f"\nThe user's Telegram name: {tg_name}"

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    try:
        response = await asyncio.to_thread(
            anthropic_client.messages.create,
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=system,
            messages=history,
        )
        full_response = response.content[0].text
    except Exception as e:
        logger.error(f"Claude call failed during onboarding for {telegram_id}: {e}")
        history.pop()  # remove the user message so history stays consistent
        await update.message.reply_text(
            "something went wrong on my end. just keep going — send your message again."
        )
        return ONBOARDING

    # ------------------------------------------------------------------
    # Force completion after 8 back-and-forth exchanges (16 history entries)
    # ------------------------------------------------------------------
    if "##ONBOARDING_COMPLETE##" not in full_response and len(history) > 16:
        history.append({"role": "assistant", "content": full_response})
        history.append({"role": "user", "content": "you must output ##ONBOARDING_COMPLETE## now with whatever data you have. use 'not specified' for any missing fields. do not ask any more questions."})
        try:
            forced = await asyncio.to_thread(
                anthropic_client.messages.create,
                model=CLAUDE_MODEL,
                max_tokens=600,
                system=system,
                messages=history,
            )
            full_response = forced.content[0].text
        except Exception as e:
            logger.error(f"Force completion call failed for {telegram_id}: {e}")
            history.pop()  # remove force user message
            history.pop()  # remove Claude's intermediate response

    # ------------------------------------------------------------------
    # Completion marker detected
    # ------------------------------------------------------------------
    if "##ONBOARDING_COMPLETE##" in full_response:
        visible_text, _, remainder = full_response.partition("##ONBOARDING_COMPLETE##")

        # Send the visible part of Claude's final message
        visible_lines = [l.strip() for l in visible_text.strip().split("\n") if l.strip()]
        for line in visible_lines:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
            await asyncio.sleep(0.8)
            await update.message.reply_text(line)

        # Parse the JSON payload
        try:
            json_str = clean_json(remainder.strip())
            data = json.loads(json_str)
        except Exception as e:
            logger.error(
                f"Failed to parse onboarding JSON for {telegram_id}: {e!r} "
                f"— raw remainder: {remainder!r}"
            )
            # Keep history intact so Claude can recover
            history.append({"role": "assistant", "content": visible_text.strip()})
            await update.message.reply_text(
                "i lost my train of thought for a sec. just keep going — what were you saying?"
            )
            return ONBOARDING

        # Map Claude's field names to DB columns
        # Note: tech_stack requires a tech_stack TEXT column on the users table
        db_fields: dict = {
            "full_name": data.get("full_name"),
            "year_of_study": data.get("year_of_study"),
            "university": data.get("university"),
            "is_international": data.get("international"),
            "experience_level": data.get("experience_level"),
            "tech_stack": data.get("tech_stack"),
            "target_companies": data.get("target_companies"),
            "weak_areas": data.get("weak_areas"),
            "goals": data.get("goal"),
            "nudge_time": data.get("nudge_time"),
            "onboarding_complete": True,
        }
        db_fields = {k: v for k, v in db_fields.items() if v is not None}

        await asyncio.to_thread(update_user, telegram_id, **db_fields)

        streak = await asyncio.to_thread(get_streak, telegram_id)
        if not streak:
            await asyncio.to_thread(create_streak, telegram_id)

        logger.info(f"Onboarding complete for {telegram_id}, saved: {list(db_fields.keys())}")

        first_name = (data.get("full_name") or "mate").split()[0]
        await update.message.reply_text(
            f"aight {first_name}, you're all set. i'll check in on you daily — now go get to work."
        )

        code = await asyncio.to_thread(generate_payment_code, telegram_id)
        payment_messages = [
            "one last thing — to unlock Koda fully, it's £7/month.",
            f"your unique activation code is: {code}\ncopy it — you'll need it at checkout.",
            "lock in here: https://buy.stripe.com/28E14pbpL4zWf1A5SYcfK00",
            "once you've paid, come back and say hi.",
        ]
        for msg in payment_messages:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
            await asyncio.sleep(0.8)
            await update.message.reply_text(msg)

        return ConversationHandler.END

    # ------------------------------------------------------------------
    # Normal conversational turn
    # ------------------------------------------------------------------
    history.append({"role": "assistant", "content": full_response})

    lines = [l.strip() for l in full_response.split("\n") if l.strip()]
    for line in lines:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await asyncio.sleep(0.8)
        await update.message.reply_text(line)

    return ONBOARDING


# ---------------------------------------------------------------------------
# Fallback and builder
# ---------------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("no worries. send /start whenever you're ready.")
    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ONBOARDING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_onboarding_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
