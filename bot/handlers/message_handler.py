import asyncio
import logging
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from db.queries.user_queries import get_user, user_exists
from db.queries.streak_queries import get_streak
from bot.koda.claude_client import get_koda_response

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    user_message = update.message.text.strip()

    if not user_exists(telegram_id):
        await update.message.reply_text(
            "You're not set up yet. Send /start to get started."
        )
        return

    user = get_user(telegram_id)
    if not user:
        await update.message.reply_text(
            "Something went wrong loading your profile. Try again."
        )
        return

    if not user.get("is_onboarded"):
        await update.message.reply_text(
            "Finish setting up your profile first. Send /start to continue."
        )
        return

    streak = get_streak(telegram_id) or {}
    user_context = {
        "full_name": user.get("full_name"),
        "username": user.get("username"),
        "year_of_study": user.get("year_of_study"),
        "university": user.get("university"),
        "target_companies": user.get("target_companies"),
        "weak_areas": user.get("weak_areas"),
        "main_goal": user.get("main_goal"),
        "current_streak": streak.get("current_streak", 0),
        "longest_streak": streak.get("longest_streak", 0),
    }

    response = get_koda_response(telegram_id, user_message, user_context)
    chunks = [line for line in response.split("\n") if line.strip()]

    for chunk in chunks:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await asyncio.sleep(0.8)
        await update.message.reply_text(chunk)
