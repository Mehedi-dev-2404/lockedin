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
    logger.info(f"_process_intent: {telegram_id} intent={intent}")
    milestone_msg = None
    name = user.get("full_name") or user.get("username") or "mate"

    if intent.get("leetcode"):
        logger.info(f"_process_intent: saving leetcode_done for {telegram_id}")
        checkin_result = await asyncio.to_thread(upsert_todays_checkin, telegram_id, {"leetcode_done": True})
        logger.info(f"_process_intent: upsert_todays_checkin(leetcode_done) returned {checkin_result}")
        new_streak, is_milestone = await asyncio.to_thread(update_leetcode_streak, telegram_id)
        logger.info(f"_process_intent: update_leetcode_streak returned streak={new_streak} milestone={is_milestone}")
        if is_milestone:
            milestone_msg = f"{new_streak}-day leetcode streak \U0001f525 that's actually hard to do. keep it up {name}."

    if intent.get("applied"):
        company = intent.get("company") or "Unknown"
        role = intent.get("role") or ""
        logger.info(f"_process_intent: saving application for {telegram_id} company={company!r} role={role!r}")
        count_before = await asyncio.to_thread(get_application_count, telegram_id)
        app_result = await asyncio.to_thread(create_application, telegram_id, company, role)
        logger.info(f"_process_intent: create_application returned {app_result}")

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
        logger.info(f"_process_intent: saving project_worked for {telegram_id}")
        checkin_result = await asyncio.to_thread(upsert_todays_checkin, telegram_id, {"project_worked": True})
        logger.info(f"_process_intent: upsert_todays_checkin(project_worked) returned {checkin_result}")
        await asyncio.to_thread(update_project_streak, telegram_id)

    if not any([intent.get("leetcode"), intent.get("applied"), intent.get("project_work")]):
        logger.info(f"_process_intent: no trackable activity detected for {telegram_id}")

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

    if not user.get("onboarding_complete"):
        await update.message.reply_text(
            "you're not set up yet. send /start to get going."
        )
        return

    streak = get_streak(telegram_id) or {}
    user_context = {
        "name": user.get("name"),
        "full_name": user.get("full_name"),
        "username": user.get("username"),
        "year_of_study": user.get("year_of_study"),
        "university": user.get("university"),
        "target_companies": user.get("target_companies"),
        "weak_areas": user.get("weak_areas"),
        "target_type": user.get("target_type"),
        "target_industry": user.get("target_industry"),
        "experience_level": user.get("experience_level"),
        "leetcode_status": user.get("leetcode_status"),
        "accountability_style": user.get("accountability_style"),
        "is_international": user.get("is_international"),
        "github_url": user.get("github_url"),
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

    # Free message limit reached
    if koda_response is None:
        upgrade_messages = [
            "you've used up your free messages.",
            "to keep grinding with Koda, upgrade at lockedin.vercel.app",
            "it's £9/month. less than a Pret coffee per week.",
        ]
        for msg in upgrade_messages:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
            await asyncio.sleep(0.8)
            await update.message.reply_text(msg)
        return

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
