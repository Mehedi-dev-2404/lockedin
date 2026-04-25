import logging
from db.queries import supabase

logger = logging.getLogger(__name__)


def get_user(telegram_id: int) -> dict | None:
    try:
        response = (
            supabase.table("users")
            .select("*")
            .eq("telegram_id", telegram_id)
            .single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"get_user failed for {telegram_id}: {e}")
        return None


def create_user(telegram_id: int, username: str | None, full_name: str | None) -> dict | None:
    try:
        response = (
            supabase.table("users")
            .insert({
                "id": telegram_id,
                "telegram_id": telegram_id,
                "username": username,
                "full_name": full_name,
                "is_onboarded": False,
            })
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"create_user failed for {telegram_id}: {e}")
        return None


def update_user(telegram_id: int, **kwargs) -> bool | None:
    try:
        supabase.table("users").update(kwargs).eq("telegram_id", telegram_id).execute()
        return True
    except Exception as e:
        logger.error(f"update_user failed for {telegram_id}: {e}")
        return None


def user_exists(telegram_id: int) -> bool:
    try:
        response = (
            supabase.table("users")
            .select("telegram_id")
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"user_exists check failed for {telegram_id}: {e}")
        return False
