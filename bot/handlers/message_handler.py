import asyncio
import logging
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from db.queries.user_queries import get_user, user_exists
from db.queries.streak_queries import (
    get_streak,
    update_leetcode_streak,
    update_applications_streak,
    update_project_streak,
)
from db.queries.checkin_queries import get_todays_checkin, upsert_todays_checkin
from db.queries.application_queries import create_application, get_application_count
from bot.koda.claude_client import get_koda_response, classify_intent

logger = logging.getLogger(__name__)


async def _process_intent(telegram_id: int, intent: dict, user: dict) -> str | None:
    """
    Silently update DB based on detected intent.
    Returns a milestone message string if something significant happened, else None.
    """
    milestone_msg = None
    name = user.get("full_name") or user.get("username") or "mate"

    if intent.get("leetcode"):
        await asyncio.to_thread(upsert_todays_checkin, telegram_id, {"leetcode_done": True})
        new_streak, is_milestone = await asyncio.to_thread(update_leetcode_streak, telegram_id)
        if is_milestone:
            milestone_msg = f"{new_streak}-day leetcode streak \U0001f525 that's actually hard to do. keep it up {name}."

    if intent.get("applied"):
        company = intent.get("company") or "Unknown"
        role = intent.get("role") or ""
        count_before = await asyncio.to_thread(get_application_count, telegram_id)
        await asyncio.to_thread(create_application, telegram_id, company, role)

        # Increment applications_sent in today's checkin
        checkin = await asyncio.to_thread(get_todays_checkin, telegram_id) or {}
        current_count = checkin.get("applications_sent", 0)
        await asyncio.to_thread(
            upsert_todays_checkin, telegram_id, {"applications_sent": current_count + 1}
        )

        await asyncio.to_thread(update_applications_streak, telegram_id)

        if count_before == 0 and milestone_msg is None:
            milestone_msg = f"first app sent. that's the hardest one. now let's do 10 more."

    if intent.get("project_work"):
        await asyncio.to_thread(upsert_todays_checkin, telegram_id, {"project_worked": True})
        await asyncio.to_thread(update_project_streak, telegram_id)

    return milestone_msg


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
        "goals": user.get("goals"),
        "current_streak": streak.get("current_streak", 0),
        "longest_streak": streak.get("longest_streak", 0),
        "leetcode_streak": streak.get("leetcode_streak", 0),
        "applications_streak": streak.get("applications_streak", 0),
        "project_streak": streak.get("project_streak", 0),
        "longest_leetcode": streak.get("longest_leetcode", 0),
    }

    # Run Koda response and intent classification in parallel
    koda_response, intent = await asyncio.gather(
        asyncio.to_thread(get_koda_response, telegram_id, user_message, user_context),
        asyncio.to_thread(classify_intent, user_message),
    )

    # Send Koda's response
    chunks = [line for line in koda_response.split("\n") if line.strip()]
    for chunk in chunks:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await asyncio.sleep(0.8)
        await update.message.reply_text(chunk)

    # Process intent and send milestone message if triggered
    milestone_msg = await _process_intent(telegram_id, intent, user)
    if milestone_msg:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await asyncio.sleep(0.8)
        await update.message.reply_text(milestone_msg)
