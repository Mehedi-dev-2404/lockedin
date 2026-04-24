import logging
from db.queries import supabase

logger = logging.getLogger(__name__)


def get_streak(telegram_id: int) -> dict | None:
    try:
        response = (
            supabase.table("streaks")
            .select("*")
            .eq("telegram_id", telegram_id)
            .single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"get_streak failed for {telegram_id}: {e}")
        return None


def create_streak(telegram_id: int) -> dict | None:
    try:
        response = (
            supabase.table("streaks")
            .insert({
                "telegram_id": telegram_id,
                "current_streak": 0,
                "longest_streak": 0,
                "last_checkin_date": None,
            })
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"create_streak failed for {telegram_id}: {e}")
        return None


def update_streak(telegram_id: int, **kwargs) -> dict | None:
    try:
        response = (
            supabase.table("streaks")
            .update(kwargs)
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"update_streak failed for {telegram_id}: {e}")
        return None
