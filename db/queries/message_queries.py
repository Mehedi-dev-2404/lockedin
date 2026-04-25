import logging
from db.queries import supabase

logger = logging.getLogger(__name__)


def save_message(telegram_id: int, role: str, content: str) -> None:
    try:
        supabase.table("messages").insert({
            "telegram_id": telegram_id,
            "role": role,
            "content": content,
        }).execute()
    except Exception as e:
        logger.error(f"save_message failed for {telegram_id}: {e}")


def get_recent_messages(telegram_id: int, limit: int = 20) -> list[dict]:
    try:
        response = (
            supabase.table("messages")
            .select("role, content")
            .eq("telegram_id", telegram_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(reversed(response.data or []))
    except Exception as e:
        logger.error(f"get_recent_messages failed for {telegram_id}: {e}")
        return []
