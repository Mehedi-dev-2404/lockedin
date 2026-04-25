import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from db.queries.user_queries import get_user, create_user, update_user, user_exists
from db.queries.streak_queries import get_streak, create_streak

logger = logging.getLogger(__name__)

NAME, YEAR, UNIVERSITY, TARGET_COMPANIES, WEAK_AREAS, MAIN_GOAL = range(6)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    tg_user = update.effective_user

    if user_exists(telegram_id):
        user = get_user(telegram_id)
        if user and user.get("is_onboarded"):
            name = user.get("full_name") or user.get("username") or "there"
            streak = get_streak(telegram_id)
            current = streak.get("leetcode_streak", 0) if streak else 0
            streak_note = f"You're on a {current}-day streak." if current > 0 else "No active streak — fix that today."
            await update.message.reply_text(
                f"Hey {name}, welcome back.\n\n"
                f"{streak_note}\n\n"
                "What are you working on today?"
            )
            return ConversationHandler.END
        # User exists but onboarding incomplete — fall through to re-prompt
    else:
        result = create_user(
            telegram_id=telegram_id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        if not result:
            logger.error(f"create_user returned None for telegram_id={telegram_id}")
            await update.message.reply_text(
                "Something went wrong setting up your account. Please try /start again."
            )
            return ConversationHandler.END
        if not get_streak(telegram_id):
            create_streak(telegram_id)

    await update.message.reply_text(
        "Hey, I'm Koda — your accountability agent for the internship grind.\n\n"
        "I'm going to ask you a few quick questions to set things up. Takes about a minute.\n\n"
        "What's your name?"
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["full_name"] = update.message.text.strip()
    await update.message.reply_text(
        f"Got it, {context.user_data['full_name']}.\n\n"
        "What year are you in? (e.g. 2nd year, Junior, final year)"
    )
    return YEAR


async def get_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["year_of_study"] = update.message.text.strip()
    await update.message.reply_text("What university are you at?")
    return UNIVERSITY


async def get_university(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["university"] = update.message.text.strip()
    await update.message.reply_text(
        "Which companies are you targeting? List them separated by commas.\n"
        "(e.g. Google, Meta, Stripe, any SWE internship)"
    )
    return TARGET_COMPANIES


async def get_target_companies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["target_companies"] = update.message.text.strip()
    await update.message.reply_text(
        "What are your weak areas right now? List them separated by commas.\n"
        "(e.g. dynamic programming, system design, behavioral interviews)"
    )
    return WEAK_AREAS


async def get_weak_areas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["weak_areas"] = update.message.text.strip()
    await update.message.reply_text(
        "Last one — what's your main goal for the next few months?\n"
        "(e.g. land a summer internship at a top tech company by March)"
    )
    return MAIN_GOAL


async def get_goals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    context.user_data["goals"] = update.message.text.strip()

    result = update_user(
        telegram_id,
        full_name=context.user_data.get("full_name"),
        year_of_study=context.user_data.get("year_of_study"),
        university=context.user_data.get("university"),
        target_companies=context.user_data.get("target_companies"),
        weak_areas=context.user_data.get("weak_areas"),
        goals=context.user_data.get("goals"),
        is_onboarded=True,
    )

    if not result:
        logger.error(f"update_user returned None for telegram_id={telegram_id} during onboarding")
        await update.message.reply_text(
            "Something went wrong saving your profile. Please send /start to try again."
        )
        return ConversationHandler.END

    name = context.user_data.get("full_name", "")
    companies_str = context.user_data.get("target_companies") or "your target companies"
    weak_str = context.user_data.get("weak_areas") or "your weak areas"

    await update.message.reply_text(
        f"Alright {name}, you're all set.\n\n"
        f"I've got your targets ({companies_str}) and I know {weak_str} "
        f"is something you need to work on.\n\n"
        f"Here's how this works: check in with me daily. Tell me what you did, "
        f"what you're stuck on, or just send a message if you need to think something through. "
        f"I'll keep your streak going and call you out if you go quiet.\n\n"
        f"What did you work on today? (If nothing yet, that's fine — what's the plan?)"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Setup cancelled. Send /start whenever you're ready."
    )
    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_year)],
            UNIVERSITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_university)],
            TARGET_COMPANIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target_companies)],
            WEAK_AREAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weak_areas)],
            MAIN_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_goals)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
