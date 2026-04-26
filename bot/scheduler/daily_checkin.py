import asyncio
import logging
from datetime import time as dt_time
import pytz
from telegram.ext import Application, ContextTypes
from db.queries.user_queries import get_all_active_users
from db.queries.checkin_queries import get_todays_checkin
from db.queries.streak_queries import get_streak
from bot.koda.claude_client import generate_nudge
from bot.koda.utils import build_user_context

logger = logging.getLogger(__name__)

_LONDON_TZ = pytz.timezone("Europe/London")
_DEFAULT_NUDGE_TIME = "20:00"


def _parse_nudge_time(raw: str | None) -> str:
    """Normalise a nudge_time string to HH:MM. Falls back to default on null or bad input."""
    if not raw:
        return _DEFAULT_NUDGE_TIME
    try:
        parts = raw.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        return f"{hour:02d}:{minute:02d}"
    except (ValueError, IndexError):
        logger.warning(f"Malformed nudge_time {raw!r}, falling back to {_DEFAULT_NUDGE_TIME}")
        return _DEFAULT_NUDGE_TIME


def _to_dt_time(time_str: str) -> dt_time:
    """Convert HH:MM string to a timezone-aware datetime.time in Europe/London."""
    hour, minute = map(int, time_str.split(":"))
    return dt_time(hour=hour, minute=minute, second=0, tzinfo=_LONDON_TZ)


def _make_nudge_job(nudge_time_str: str):
    """Return a job function that sends nudges to users whose nudge_time matches."""
    async def send_nudges(context: ContextTypes.DEFAULT_TYPE) -> None:
        users = await asyncio.to_thread(get_all_active_users)
        for user in users:
            if _parse_nudge_time(user.get("nudge_time")) != nudge_time_str:
                continue

            telegram_id = user.get("telegram_id")
            if not telegram_id:
                continue

            checkin = await asyncio.to_thread(get_todays_checkin, telegram_id)
            if checkin:
                continue

            streak = await asyncio.to_thread(get_streak, telegram_id) or {}
            user_context = build_user_context(user, streak)
            nudge = await asyncio.to_thread(generate_nudge, user_context)

            try:
                await context.bot.send_message(chat_id=telegram_id, text=nudge)
            except Exception as e:
                logger.error(f"Failed to send nudge to {telegram_id}: {e}")

    return send_nudges


def schedule_daily_nudges(app: Application) -> None:
    """Group active users by nudge_time and schedule one job per unique time."""
    users = get_all_active_users()
    unique_times = {_parse_nudge_time(u.get("nudge_time")) for u in users}
    if not unique_times:
        unique_times = {_DEFAULT_NUDGE_TIME}

    for time_str in unique_times:
        app.job_queue.run_daily(
            _make_nudge_job(time_str),
            time=_to_dt_time(time_str),
            name=f"daily_nudge_{time_str.replace(':', '')}",
        )
        logger.info(f"Nudge job scheduled at {time_str} Europe/London")
