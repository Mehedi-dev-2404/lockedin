import asyncio
import logging
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from db.queries.user_queries import get_user
from db.queries.checkin_queries import get_todays_checkin
from db.queries.streak_queries import get_streak
from bot.koda.utils import get_display_name

logger = logging.getLogger(__name__)


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    user = get_user(telegram_id)

    if not user or not user.get("onboarding_complete"):
        await update.message.reply_text("Set up your profile first. Send /start.")
        return

    name = get_display_name(user)
    checkin = get_todays_checkin(telegram_id) or {}
    streak = get_streak(telegram_id) or {}

    leetcode_done = checkin.get("leetcode_done", False)
    apps_sent = checkin.get("applications_sent", 0)
    project_worked = checkin.get("project_worked", False)
    leetcode_streak = streak.get("leetcode_streak", 0)

    if apps_sent > 0:
        apps_line = f"applications: \u2705 ({apps_sent} sent)"
    else:
        apps_line = "applications: \u274c"

    streak_suffix = " \U0001f525" if leetcode_streak >= 3 else ""
    day_word = "day" if leetcode_streak == 1 else "days"
    streak_line = f"leetcode streak: {leetcode_streak} {day_word}{streak_suffix}"

    lines = [
        f"aight here's your day {name}",
        f"leetcode: {'\u2705' if leetcode_done else '\u274c'}",
        apps_line,
        f"projects: {'\u2705' if project_worked else '\u274c'}",
        streak_line,
    ]

    for line in lines:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await asyncio.sleep(0.8)
        await update.message.reply_text(line)
