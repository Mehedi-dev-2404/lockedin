import logging
from datetime import date, datetime, timezone
from db.queries import supabase

logger = logging.getLogger(__name__)


def create_checkin(telegram_id: int, data: dict) -> dict | None:
    try:
        payload = {"telegram_id": telegram_id, "date": date.today().isoformat(), **data}
        response = supabase.table("checkins").insert(payload).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"create_checkin failed for {telegram_id}: {e}")
        return None


def get_todays_checkin(telegram_id: int) -> dict | None:
    today = date.today().isoformat()
    try:
        response = (
            supabase.table("checkins")
            .select("*")
            .eq("telegram_id", telegram_id)
            .eq("date", today)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"get_todays_checkin failed for {telegram_id}: {e}")
        return None


def get_recent_checkins(telegram_id: int, limit: int = 7) -> list[dict]:
    try:
        response = (
            supabase.table("checkins")
            .select("*")
            .eq("telegram_id", telegram_id)
            .order("date", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"get_recent_checkins failed for {telegram_id}: {e}")
        return []


def upsert_todays_checkin(telegram_id: int, data: dict) -> dict | None:
    """Update today's checkin row if it exists, create it if not."""
    today = date.today().isoformat()
    existing = get_todays_checkin(telegram_id)
    logger.info(f"upsert_todays_checkin: {telegram_id} data={data} existing={'yes' if existing else 'no'}")
    try:
        if existing:
            response = (
                supabase.table("checkins")
                .update(data)
                .eq("telegram_id", telegram_id)
                .eq("date", today)
                .execute()
            )
            result = response.data[0] if response.data else None
            logger.info(f"upsert_todays_checkin updated: {telegram_id} result={result}")
            return result
        else:
            payload = {"telegram_id": telegram_id, "date": today, **data}
            response = supabase.table("checkins").insert(payload).execute()
            result = response.data[0] if response.data else None
            logger.info(f"upsert_todays_checkin inserted: {telegram_id} result={result}")
            return result
    except Exception as e:
        logger.error(f"upsert_todays_checkin failed for {telegram_id}: {e}")
        return None
