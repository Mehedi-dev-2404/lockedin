import asyncio
import logging
from datetime import time as dt_time
import pytz
from telegram.ext import Application, ContextTypes
from db.queries.user_queries import get_all_active_users
from db.queries.checkin_queries import get_todays_checkin
from db.queries.streak_queries import get_streak
from bot.koda.claude_client import generate_nudge

logger = logging.getLogger(__name__)

_LONDON_TZ = pytz.timezone("Europe/London")
_NUDGE_TIME = dt_time(hour=20, minute=0, second=0, tzinfo=_LONDON_TZ)


async def send_daily_nudges(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cron job: send an evening nudge to every active user who hasn't checked in today."""
    users = await asyncio.to_thread(get_all_active_users)

    for user in users:
        telegram_id = user.get("telegram_id")
        if not telegram_id:
            continue

        checkin = await asyncio.to_thread(get_todays_checkin, telegram_id)
        if checkin:
            continue  # Already checked in today, no nudge needed

        streak = await asyncio.to_thread(get_streak, telegram_id) or {}
        user_context = {
            "telegram_id": telegram_id,
            "full_name": user.get("full_name"),
            "username": user.get("username"),
            "goals": user.get("goals"),
            "target_companies": user.get("target_companies"),
            "weak_areas": user.get("weak_areas"),
            "leetcode_streak": streak.get("leetcode_streak", 0),
            "applications_streak": streak.get("applications_streak", 0),
            "project_streak": streak.get("project_streak", 0),
            "longest_leetcode": streak.get("longest_leetcode", 0),
        }

        nudge = await asyncio.to_thread(generate_nudge, user_context)

        try:
            await context.bot.send_message(chat_id=telegram_id, text=nudge)
        except Exception as e:
            logger.error(f"Failed to send nudge to {telegram_id}: {e}")


def schedule_daily_nudge(app: Application) -> None:
    """Register the daily nudge job on the application's job queue."""
    app.job_queue.run_daily(
        send_daily_nudges,
        time=_NUDGE_TIME,
        name="daily_nudge",
    )
    logger.info(f"Daily nudge scheduled at {_NUDGE_TIME} Europe/London")
