import logging
from db.queries import supabase

logger = logging.getLogger(__name__)


def get_user(telegram_id: int) -> dict | None:
    try:
        response = (
            supabase.table("users")
            .select("*")
            .eq("telegram_id", telegram_id)
            .maybe_single()
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
                "onboarding_complete": False,
                "onboarding_step": 0,
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


def get_all_active_users() -> list[dict]:
    try:
        response = (
            supabase.table("users")
            .select("*")
            .eq("is_active", True)
            .eq("onboarding_complete", True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"get_all_active_users failed: {e}")
        return []


def append_leetcode_progress(telegram_id: int, topics: list[str]) -> bool:
    """Merge new topics into the user's leetcode_progress JSON array, deduplicating."""
    try:
        response = (
            supabase.table("users")
            .select("leetcode_progress")
            .eq("telegram_id", telegram_id)
            .maybe_single()
            .execute()
        )
        current = response.data.get("leetcode_progress") or [] if response.data else []
        existing = {t.lower() for t in current}
        merged = current + [t for t in topics if t.lower() not in existing]
        supabase.table("users").update({"leetcode_progress": merged}).eq("telegram_id", telegram_id).execute()
        return True
    except Exception as e:
        logger.error(f"append_leetcode_progress failed for {telegram_id}: {e}")
        return False


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
