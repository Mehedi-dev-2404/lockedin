import logging
from telegram import Update
from telegram.ext import ContextTypes
from db.queries.user_queries import get_user, update_user
from db.queries.streak_queries import get_streak
from config.settings import ADMIN_TELEGRAM_ID
from bot.koda.utils import get_display_name

logger = logging.getLogger(__name__)


async def streak_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    user = get_user(telegram_id)

    if not user:
        await update.message.reply_text(
            "You're not registered yet. Send /start to get going."
        )
        return

    streak = get_streak(telegram_id)
    if not streak:
        await update.message.reply_text(
            "No streak data found. Start checking in to build one."
        )
        return

    current = streak.get("leetcode_streak", 0)
    longest = streak.get("longest_leetcode", 0)
    last_date = streak.get("last_leetcode_date")

    if current == 0:
        streak_line = "Your streak is at 0. Check in today to get it started."
    elif current == 1:
        streak_line = "You're at 1 day. Keep it going tomorrow."
    else:
        streak_line = f"You're on a {current}-day streak. Don't break it."

    last_line = f"Last check-in: {last_date}" if last_date else "You haven't checked in yet."

    await update.message.reply_text(
        f"🔥 Streak\n\n"
        f"Current: {current} day(s)\n"
        f"Longest: {longest} day(s)\n"
        f"{last_line}\n\n"
        f"{streak_line}"
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    user = get_user(telegram_id)

    if not user:
        await update.message.reply_text(
            "You're not registered yet. Send /start to set up your profile."
        )
        return

    if not user.get("onboarding_complete"):
        await update.message.reply_text(
            "You haven't finished onboarding yet. Send /start to complete it."
        )
        return

    name = get_display_name(user)
    year = user.get("year_of_study", "—")
    university = user.get("university", "—")
    targets_str = user.get("target_companies") or "—"
    weak_str = user.get("weak_areas") or "—"
    goal = user.get("goals") or "—"

    await update.message.reply_text(
        f"👤 Profile\n\n"
        f"Name: {name}\n"
        f"Year: {year}\n"
        f"University: {university}\n"
        f"Target companies: {targets_str}\n"
        f"Weak areas: {weak_str}\n"
        f"Goal: {goal}"
    )


async def reset_onboarding_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id

    if telegram_id != ADMIN_TELEGRAM_ID:
        return

    update_user(telegram_id, onboarding_complete=False, onboarding_step=0)
    await update.message.reply_text("Onboarding reset. Send /start to go again.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n\n"
        "/start — set up your profile (or restart onboarding)\n"
        "/streak — check your current check-in streak\n"
        "/profile — view your profile and goals\n"
        "/help — show this list\n\n"
        "Or just send me a message — I'm here to keep you on track."
    )
